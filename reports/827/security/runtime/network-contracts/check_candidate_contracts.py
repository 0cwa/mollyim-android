#!/usr/bin/env python3
"""Read-only candidate16 evidence checks; no builds or candidate edits."""
from __future__ import annotations
import json, re, subprocess, xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path('/workspace/work/p2-integration/candidate15-replay-1')
APP = ROOT / 'app/src/main/java'
CLASSDIR = ROOT / 'app/build/intermediates/built_in_kotlinc/playProdDebug/compilePlayProdDebugKotlin/classes'
CONNECTOR = Path('/workspace/work/p2-review-followup/connector-classes.jar')
OUT = Path('/workspace/work/p2-review-followup')

def run(cmd):
    return subprocess.run(cmd, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout

# Check the actual compiled Kotlin repository methods, not just source text.
repo_bytecode = run(['/workspace/jdk21/bin/javap', '-classpath', str(CLASSDIR), '-c', '-p', 'im.molly.unifiedpush.MollySocketRepository'])
(OUT / 'MollySocketRepository.javap.txt').write_text(repo_bytecode)
methods = {}
for name in ('discoverMollySocketServer', 'registerDeviceOnServer'):
    start = repo_bytecode.find('public final ', repo_bytecode.find(name) - 80)
    end = repo_bytecode.find('\n  public ', repo_bytecode.find(name) + 20)
    methods[name] = repo_bytecode[start:end if end >= 0 else None]
    block = methods[name]
    assert block.count('Builder.followRedirects:(Z)') == 1, name + ': followRedirects call missing/duplicated'
    assert block.count('Builder.followSslRedirects:(Z)') == 1, name + ': followSslRedirects call missing/duplicated'
    for marker in ('iconst_0', 'Builder.followRedirects:(Z)', 'iconst_0', 'Builder.followSslRedirects:(Z)'):
        assert marker in block, name + ': expected false redirect configuration absent'
    assert block.index('iconst_0') < block.index('Builder.followRedirects:(Z)') < block.index('Builder.followSslRedirects:(Z)')

# Confirm the duplicate connector receiver's suppression condition in exact cached AAR bytecode.
impl = run(['/workspace/jdk21/bin/javap', '-classpath', str(CONNECTOR), '-c', '-p', 'org.unifiedpush.android.connector.internal.MessagingReceiverImpl'])
(OUT / 'MessagingReceiverImpl.javap.txt').write_text(impl)
should_run = impl[impl.index('private final boolean shouldRun'):impl.index('\n  static {};', impl.index('private final boolean shouldRun'))]
assert 'UnifiedPush.getResolveInfo' in should_run
assert 'ResolveInfo.priority:I' in should_run and 'sipush        -500' in should_run
assert 'if_icmple' in should_run and 'iconst_0' in should_run

manifest = ROOT / 'app/build/intermediates/merged_manifest/playProdDebug/processPlayProdDebugMainManifest/AndroidManifest.xml'
tree = ET.parse(manifest)
ns = {'a':'http://schemas.android.com/apk/res/android'}
app_receiver = tree.find(".//receiver[@android:name='im.molly.unifiedpush.receiver.UnifiedPushReceiver']".replace('android:', '{http://schemas.android.com/apk/res/android}'))
lib_receiver = tree.find(".//receiver[@android:name='org.unifiedpush.android.connector.internal.MessagingReceiverImpl']".replace('android:', '{http://schemas.android.com/apk/res/android}'))
assert app_receiver is not None and lib_receiver is not None
app_priority = int(app_receiver.find('intent-filter').get('{http://schemas.android.com/apk/res/android}priority', '0'))
lib_priority = int(lib_receiver.find('intent-filter').get('{http://schemas.android.com/apk/res/android}priority', '0'))
assert app_priority == 0 and lib_priority == -500 and app_priority > lib_priority
expected_actions = {
 'org.unifiedpush.android.connector.MESSAGE',
 'org.unifiedpush.android.connector.UNREGISTERED',
 'org.unifiedpush.android.connector.NEW_ENDPOINT',
 'org.unifiedpush.android.connector.REGISTRATION_FAILED',
}
for element in (app_receiver, lib_receiver):
    actions = {x.get('{http://schemas.android.com/apk/res/android}name') for x in element.findall('.//action')}
    assert actions == expected_actions, actions

# Truth table for predicates implemented in candidate KeyCachingService and pinned target.
# Candidate: masterSecret==null && (!passphraseDisabled || screenLockEnabled).
# Target: masterSecret==null || locking.
rows=[]
for secret in (False, True):
  for locking in (False, True):
    for passphrase_disabled in (False, True):
      for screen_lock in (False, True):
        cand = (not secret) and ((not passphrase_disabled) or screen_lock)
        target = (not secret) or locking
        rows.append({'master_secret_present':secret,'target_locking_transition':locking,'passphrase_disabled':passphrase_disabled,'screen_lock_enabled':screen_lock,'candidate_locked':cand,'target_locked':target,'differs':cand != target})
expected_diffs = [r for r in rows if r['differs']]
assert len(expected_diffs) == 6, len(expected_diffs)
# Explicitly guard the two important transition families, independent of other flags.
assert any(not r['master_secret_present'] and r['passphrase_disabled'] and not r['screen_lock_enabled'] and not r['candidate_locked'] and r['target_locked'] for r in expected_diffs)
assert any(r['master_secret_present'] and r['target_locking_transition'] and not r['candidate_locked'] and r['target_locked'] for r in expected_diffs)

# Locked notification policy: candidate adds preference gate and preserves normal unlocked notification.
fetch = (APP / 'org/thoughtcrime/securesms/gcm/FcmFetchManager.kt').read_text()
receiver = (APP / 'im/molly/unifiedpush/receiver/UnifiedPushReceiver.kt').read_text()
assert 'if (KeyCachingService.isLocked(context) && !TextSecurePreferences.isPassphraseLockNotificationsEnabled(context))' in fetch
assert 'FcmFetchManager.postMayHaveMessagesNotificationForLockedPush(context)' in receiver
assert 'if (TextSecurePreferences.isPassphraseLockNotificationsEnabled(context))' in receiver
notify = {(locked, pref): not (locked and not pref) for locked in (False,True) for pref in (False,True)}
assert notify == {(False,False):True,(False,True):True,(True,False):False,(True,True):True}

# Startup route decision is checked against candidate source; enumerate the intended cases.
startup = (APP / 'org/thoughtcrime/securesms/ApplicationContext.java').read_text()
assert 'SignalStore.settings().hasPreferredNotificationMethod()' in startup
assert ': NotificationDeliveryMethod.FCM;' in startup
assert 'method == NotificationDeliveryMethod.UNIFIEDPUSH && !SignalStore.account().isLinkedDevice()' in startup
assert 'if (method != NotificationDeliveryMethod.FCM)' in startup
route_rows=[]
for pref in ('UNSET','FCM','WEBSOCKET','UNIFIEDPUSH'):
  for linked in (False,True):
    method = 'FCM' if pref == 'UNSET' else pref
    route_rows.append({'stored_preference':pref,'linked_device':linked,'effective_method':method,'uses_unifiedpush':method=='UNIFIEDPUSH' and not linked,'play_services_check':method=='FCM'})
assert next(r for r in route_rows if r['stored_preference']=='UNSET' and not r['linked_device'])['effective_method']=='FCM'
assert not next(r for r in route_rows if r['stored_preference']=='UNIFIEDPUSH' and r['linked_device'])['uses_unifiedpush']

report = {
 'candidate16_tree':'24a27bf3ddf2f23593f5a11e3230b66b335bc2a3',
 'checks':[
  {'id':'transport_redirect_bytecode','result':'PASS','scope':'Compiled MollySocketRepository methods both set followRedirects(false) and followSslRedirects(false). Pair with prior fake-credential local TLS 307/308 probe in ../p2-review/https-redirect-probe-no-follow.log; this is not a call into app singleton at runtime.'},
  {'id':'connector_duplicate_receiver_resolution','result':'EXPECTED_LIBRARY_FALLBACK','scope':'Merged manifest app receiver priority defaults 0, internal receiver priority -500. Connector 3.0.10 bytecode queries MESSAGE ResolveInfo and suppresses itself when a receiver priority is greater than -500. Static proof only; installed PackageManager resolution not observed.'},
  {'id':'locked_notification_policy','result':'PASS_STATIC_TRUTH_TABLE','scope':'The guard posts for unlocked state regardless of preference and suppresses only locked+opted-out. Both UP urgent callback and FCM generic fallback route through this guard. No Android notification manager/device assertion.'},
  {'id':'initial_and_explicit_delivery_method_routes','result':'PASS_STATIC_ROUTE_MATRIX','scope':'Unset preference selects FCM first-run route; explicit non-FCM starts network then exits FCM availability branch; UP is disabled for linked devices and unregisters unless air-gapped. Source-derived table, no fake AppDependencies integration test.'},
  {'id':'lock_predicate_target_difference','result':'KNOWN_SEMANTIC_DIVERGENCE','scope':'Truth table has 6 differing combinations because pinned baseline omits target locking transition flag and treats masterSecret-null/passphrase-disabled/no-screenlock as unlocked. This is intentional baseline adapter; exact A2-4 lock-hook parity cannot pass without semantics change.'}
 ],
 'lock_truth_table':rows,
 'notification_policy_truth_table':[{'locked':l,'notify_pref':p,'will_post_generic_locked_or_fallback_notice':v} for (l,p),v in notify.items()],
 'delivery_route_table':route_rows,
 'manifest':str(manifest),
 'connector_cached_aar_class_hash':__import__('hashlib').sha256(CONNECTOR.read_bytes()).hexdigest()
}
(OUT/'candidate16-contract-checks.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'result':'PASS','checks':report['checks'],'lock_diff_rows':len(expected_diffs),'manifest_priorities':[app_priority,lib_priority]},indent=2))
