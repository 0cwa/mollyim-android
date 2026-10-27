#!/usr/bin/env python3
"""Cross-check the #827 archaeology tables against the pinned Git trees and live series."""
import argparse
import replay
import csv
import hashlib
import json
import os
import re
import subprocess
from check_resource_parity import check_resource_parity
from collections import Counter
from pathlib import Path

SHA = re.compile(r'^[0-9a-f]{40}$')
SHA256 = re.compile(r'^[0-9a-f]{64}$')
FULL_FIELDS = {'status', 'old_path', 'path', 'category', 'confidence', 'reason_evidence', 'latest_target_path_commit_candidate'}
FEATURE_FIELDS = {'feature_id', 'path', 'hunk_ownership', 'molly_source_commit_shas', 'molly_history_candidate_shas', 'reconstruction_mailbox_commit_shas', 'provenance_note', 'target_behavior', 'dependencies', 'security_sensitivity', 'approval_status', 'exclusion_reason'}
HUNK_FIELDS = {'feature_id', 'path', 'ownership', 'coordinate_tree', 'start_line', 'end_line', 'fragment_id', 'target_sha256', 'reconstruction_mailbox_sha', 'molly_origin_candidate'}
CURRENT_FIELDS = {'path','feature_id','manifest_role','fragment_ids','present_in_pinned_target_diff','target_parity_claim','target_sha256','expected_replay_sha256','molly_source_commit_shas','reconstruction_mailbox_commit_shas','inputs_sha256'}

class CheckError(RuntimeError): pass

def read_tsv(path, required):
    with path.open(newline='') as stream:
        reader = csv.DictReader(stream, delimiter='\t')
        if not required.issubset(reader.fieldnames or []):
            raise CheckError(f'{path}: missing columns {sorted(required - set(reader.fieldnames or []))}')
        rows = list(reader)
    for i, row in enumerate(rows, 2):
        if any(value is None for value in row.values()):
            raise CheckError(f'{path}:{i}: malformed TSV row')
    return rows

def git(repo, *args, text=True):
    return subprocess.check_output(['git', '-C', str(repo), *args], text=text)

def blob(repo, rev, path):
    return git(repo, 'show', f'{rev}:{path}', text=False)

def has_blob(repo, rev, path):
    return subprocess.run(['git','-C',str(repo),'cat-file','-e',f'{rev}:{path}'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def target_diff_records(repo, base, target):
    raw = git(repo, 'diff', '--name-status', '-z', '--find-renames', base, target, text=False).split(b'\0')
    out=[]; i=0
    while i < len(raw)-1:
        status=os.fsdecode(raw[i]); i+=1
        if status.startswith(('R','C')):
            old=os.fsdecode(raw[i]); new=os.fsdecode(raw[i+1]); i+=2
        else:
            old=''; new=os.fsdecode(raw[i]); i+=1
        out.append((status,old,new))
    return out

def patch_paths(repo, manifest_path, manifest):
    found=set()
    for feature in manifest['features']:
        for patch in feature['patches']:
            data=(manifest_path.parent / patch['path']).read_text(errors='replace')
            found.update(re.findall(r'^diff --git a/(.*?) b/.*$',data,re.M))
    return found

def current_path_sets(manifest):
    parity=set(); integrations=set(); adaptations=set(); added=set(); overlays=set()
    for f in manifest['features']:
        parity.update(f.get('parity_paths',[]))
        integrations.update(x['path'] for x in f.get('integration_paths',[]))
        adaptations.update(x['path'] for x in f.get('adaptation_paths',[]))
        values=f.get('added_paths',[])
        for x in values: added.add(x if isinstance(x,str) else x['path'])
        for x in f.get('overlay_paths',[]): overlays.add(x if isinstance(x,str) else x['path'])
    top=manifest.get('added_paths',[])
    for x in top: added.add(x if isinstance(x,str) else x['path'])
    for x in manifest.get('overlay_paths',[]): overlays.add(x if isinstance(x,str) else x['path'])
    if (parity & integrations) or (parity & adaptations) or (integrations & adaptations):
        # Shared paths may be listed in integration and adaptation categories only when the manifest states both explicitly.
        pass
    return parity,integrations,adaptations,added,overlays

def line_ranges(repo, base, head, path):
    diff=git(repo,'diff','--unified=0',base,head,'--',path)
    out=[]
    for line in diff.splitlines():
        m=re.match(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@',line)
        if m:
            start=int(m.group(3)); count=int(m.group(4) or 1)
            out.append((start,start+max(count-1,0)))
    return out

def line_num(data, offset): return data[:offset].count(b'\n')+1

def validate(repo: Path):
    repo=repo.resolve(); manifest_path=repo/'patches/827/base'
    manifest=replay.load_inputs(manifest_path.parent, repo/'docs/827/parity-evidence.json')
    base=manifest['signal_base']; target=manifest['molly_expected']; head=git(repo,'rev-parse','HEAD').strip()
    for sha in (base,target,head):
        if not SHA.fullmatch(sha): raise CheckError(f'invalid commit id {sha}')
        git(repo,'cat-file','-e',sha+'^{commit}')
    inv_dir=repo/'reports/827/inventory'
    full=read_tsv(inv_dir/'full-tree-classification.tsv',FULL_FIELDS)
    feature=read_tsv(repo/'docs/827/feature-inventory.tsv',FEATURE_FIELDS)
    hunks=read_tsv(inv_dir/'selected-hunks.tsv',HUNK_FIELDS)
    current=read_tsv(inv_dir/'current-series-owned.tsv',CURRENT_FIELDS)
    summary=json.loads((inv_dir/'summary.json').read_text())
    actual=target_diff_records(repo,base,target)
    keys=[(r['status'],r['old_path'],r['path']) for r in full]
    actual_keys=sorted(actual); rows_keys=sorted(keys)
    if rows_keys != actual_keys:
        missing=actual_keys[:5]; extra=rows_keys[:5]
        raise CheckError(f'full-tree TSV differs from live base→target git diff (actual={len(actual_keys)}, rows={len(rows_keys)}; examples actual={missing}, rows={extra})')
    if len(set(keys)) != len(keys): raise CheckError('full-tree inventory contains duplicate status/path records')
    if any(not r['category'] or not r['reason_evidence'] for r in full): raise CheckError('every full-tree row needs category and evidence/reason')
    diff_paths={p for _,_,p in actual}
    historical=[r for r in feature if r['feature_id'] in {'branding','unifiedpush'}]
    boundary=[r for r in feature if r['feature_id'] in {'excluded','unresolved'}]
    if len(historical)!=80 or len(boundary)!=3: raise CheckError(f'historical inventory must stay 80 paths + 3 boundary records; found {len(historical)} + {len(boundary)}')
    if not {r['path'] for r in historical} <= diff_paths: raise CheckError('historical 80 includes path absent from pinned target diff')
    parity,integrations,adaptations,added,overlays=current_path_sets(manifest)
    declared=parity|integrations|adaptations|added|overlays
    current_by_path={r['path']:r for r in current}
    if len(current_by_path)!=len(current) or set(current_by_path)!=declared:
        raise CheckError('current-series-owned.tsv path set differs from live patch manifest')
    expected_roles={}
    for f in manifest['features']:
        for p in f.get('parity_paths',[]):expected_roles.setdefault(p,[]).append('full-file-parity')
        for x in f.get('integration_paths',[]):expected_roles.setdefault(x['path'],[]).append('anchored-fragment')
        for x in f.get('adaptation_paths',[]):expected_roles.setdefault(x['path'],[]).append('adaptation')
        for x in f.get('added_paths',[]):expected_roles.setdefault(x if isinstance(x,str) else x['path'],[]).append('added-target-absent')
        for x in f.get('overlay_paths',[]):expected_roles.setdefault(x if isinstance(x,str) else x['path'],[]).append('build-validation-overlay')
    for x in manifest.get('added_paths',[]):expected_roles.setdefault(x if isinstance(x,str) else x['path'],[]).append('added-target-absent')
    for x in manifest.get('overlay_paths',[]):expected_roles.setdefault(x if isinstance(x,str) else x['path'],[]).append('build-validation-overlay')
    for p,row in current_by_path.items():
        roles=set(row['manifest_role'].split(';'))
        if roles!=set(expected_roles[p]):raise CheckError(f'current-series-owned role mismatch: {p}')
        if row['present_in_pinned_target_diff'] != str(p in diff_paths).lower():raise CheckError(f'current-series-owned target membership mismatch: {p}')
        if row['inputs_sha256'] != replay.audit_digest(manifest):raise CheckError('current-series-owned forest/evidence digest is stale')
    patches=patch_paths(repo,manifest_path,manifest)
    if patches != declared:
        raise CheckError(f'manifest owned path set differs from mailbox path set (manifest-only={sorted(declared-patches)[:8]}, patch-only={sorted(patches-declared)[:8]})')
    target_present=declared & diff_paths; outside_target_diff=declared-diff_paths
    target_tree_absent={p for p in declared if not has_blob(repo,target,p)}
    if target_tree_absent != added: raise CheckError(f'only files absent from the pinned target tree belong in added_paths (absent={sorted(target_tree_absent)}, added={sorted(added)})')
    allowed_outside=added|overlays|(adaptations-diff_paths)
    if outside_target_diff != allowed_outside: raise CheckError(f'paths outside the baseline→target diff must be added, overlay, or documented adaptation paths (outside={sorted(outside_target_diff)}, allowed={sorted(allowed_outside)})')
    if not {r['path'] for r in historical} <= declared: raise CheckError('historical 80 paths are not a subset of current series ownership')
    # Whole-file parity against the actual target and current reconstructed HEAD tree.
    full_ranges=[r for r in hunks if r['ownership']=='full-path exact parity']
    manifest_full=parity
    if {r['path'] for r in full_ranges} != manifest_full: raise CheckError('full-file hunk map differs from current manifest parity_paths')
    for row in full_ranges:
        tb=blob(repo,target,row['path']); hb=blob(repo,head,row['path'])
        if tb != hb: raise CheckError(f'full-path parity differs between target and HEAD: {row["path"]}')
        if not row['start_line'].isdigit() or int(row['start_line'])!=1 or int(row['end_line'])!=max(1,tb.count(b'\n')+(not tb.endswith(b'\n'))): raise CheckError(f'bad full-file line span: {row["path"]}')
        if hashlib.sha256(tb).hexdigest()!=row['target_sha256']: raise CheckError(f'full-file SHA mismatch: {row["path"]}')
    # Anchored target fragments: verify bytes, line ranges, and candidate content independently.
    anchors=[r for r in hunks if r['ownership'].startswith('anchored fragment ')]
    frag_expected=[]
    for f in manifest['features']:
        for integration in f.get('integration_paths',[]):
            p=integration['path']; tb=blob(repo,target,p); hb=blob(repo,head,p)
            for frag in integration['fragments']:
                a=frag['start_anchor'].encode(); b=frag['end_anchor'].encode(); start=tb.find(a); end=tb.find(b,start+len(a)) if start>=0 else -1
                if start<0 or end<0: raise CheckError(f'anchors missing in target {p}:{frag["id"]}')
                expected=tb[start:end+len(b)]
                if hashlib.sha256(expected).hexdigest()!=frag['target_sha256']: raise CheckError(f'manifest fragment hash mismatch: {p}:{frag["id"]}')
                hs=hb.find(a); he=hb.find(b,hs+len(a)) if hs>=0 else -1
                if hs<0 or he<0 or hb[hs:he+len(b)]!=expected: raise CheckError(f'candidate anchored fragment differs: {p}:{frag["id"]}')
                frag_expected.append((p,frag['id'],str(line_num(tb,start)),str(line_num(tb,end+len(b)-1)),frag['target_sha256']))
    actual_anchor={(r['path'],r['fragment_id'],r['start_line'],r['end_line'],r['target_sha256']) for r in anchors}
    if actual_anchor!=set(frag_expected): raise CheckError('anchored hunk coordinates/hashes differ from pinned target')
    # Adaptations compare both recorded target and expected replay blobs; ranges are against live HEAD.
    adaptation_rows=[r for r in hunks if r['ownership'].startswith('adaptation patch hunk')]
    manifest_adapt={x['path']:x for f in manifest['features'] for x in f.get('adaptation_paths',[])}
    if {r['path'] for r in adaptation_rows} != set(manifest_adapt): raise CheckError('adaptation hunk paths differ from current manifest adaptations')
    by_path={}
    for r in adaptation_rows: by_path.setdefault(r['path'],[]).append((int(r['start_line']),int(r['end_line'])))
    for p,item in manifest_adapt.items():
        tb=blob(repo,target,p); hb=blob(repo,head,p)
        if hashlib.sha256(tb).hexdigest()!=item['target_sha256']: raise CheckError(f'adaptation target hash mismatch: {p}')
        if hashlib.sha256(hb).hexdigest()!=item['expected_replay_sha256']: raise CheckError(f'adaptation reconstructed hash mismatch: {p}')
        expected=sorted(line_ranges(repo,base,head,p))
        if sorted(by_path.get(p,[]))!=expected: raise CheckError(f'adaptation hunk coordinates differ from base→HEAD diff: {p}')
    # Added target-absent paths are explicit and have candidate-only line coordinates.
    added_rows=[r for r in hunks if r['ownership']=='added target-absent path']
    if {r['path'] for r in added_rows} != added: raise CheckError('added-path hunk map differs from manifest added_paths')
    for p in added:
        actual_ranges=sorted(line_ranges(repo,base,head,p))
        recorded=sorted((int(r['start_line']),int(r['end_line'])) for r in added_rows if r['path']==p)
        if recorded!=actual_ranges:raise CheckError(f'added-path coordinates differ from base→HEAD diff: {p}')
    # Build-validation overlays change paths that are present in the target but outside the historical target diff.
    overlay_entries=[]
    for f in manifest['features']:
        for x in f.get('overlay_paths',[]): overlay_entries.append(x if isinstance(x,dict) else {'path':x})
    for x in manifest.get('overlay_paths',[]): overlay_entries.append(x if isinstance(x,dict) else {'path':x})
    for item in overlay_entries:
        p=item['path']; tb=blob(repo,target,p); hb=blob(repo,head,p)
        if item.get('target_sha256') and hashlib.sha256(tb).hexdigest()!=item['target_sha256']: raise CheckError(f'overlay target hash mismatch: {p}')
        if item.get('expected_replay_sha256') and hashlib.sha256(hb).hexdigest()!=item['expected_replay_sha256']: raise CheckError(f'overlay replay hash mismatch: {p}')
    # Added paths are intentionally absent from the target; their expected replay hashes are explicit.
    added_entries=[]
    for f in manifest['features']:
        for x in f.get('added_paths',[]): added_entries.append(x if isinstance(x,dict) else {'path':x})
    for x in manifest.get('added_paths',[]): added_entries.append(x if isinstance(x,dict) else {'path':x})
    for item in added_entries:
        p=item['path']
        if has_blob(repo,target,p): raise CheckError(f'added_paths entry exists in pinned target: {p}')
        try: head_blob=blob(repo,head,p)
        except subprocess.CalledProcessError:
            local=repo/p
            if not local.is_file(): raise CheckError(f'added path missing from reconstructed tree and working tree: {p}')
            head_blob=local.read_bytes()
        expected=item.get('expected_replay_sha256')
        if expected and hashlib.sha256(head_blob).hexdigest()!=expected: raise CheckError(f'added path replay hash mismatch: {p}')
    ownership_counts={'full_file_parity_paths':len(parity),'integration_files':len(integrations),'anchored_fragments':sum(len(x['fragments']) for f in manifest['features'] for x in f.get('integration_paths',[])),'adaptation_paths':len(adaptations),'added_target_absent_paths':len(added),'build_validation_overlay_paths':len(overlays),'current_manifest_paths':len(declared),'current_target_diff_paths':len(target_present),'current_paths_outside_target_diff':len(outside_target_diff),'historical_target_paths':len(historical)}
    resource_parity=check_resource_parity(repo)
    if resource_parity['status']!='PASS': raise CheckError('resource element parity failed')
    resource_report_sha=digest(inv_dir/'resource-parity.json')
    resource_summary=summary.get('resource_parity',{})
    if resource_summary.get('report_sha256')!=resource_report_sha: raise CheckError('resource parity receipt digest is stale')
    for key in ('status','manifest_owned_paths','candidate_changed_elements','pinned_target_matches','raw_exact_matches','compiler_proven_runtime_equivalent_elements','unique_selected_names','baseline_resource_xml_files_checked','baseline_resource_xml_files_unchanged'):
        actual={'status':resource_parity['status'],'manifest_owned_paths':resource_parity['manifest_owned_resource_paths'],'candidate_changed_elements':resource_parity['candidate_changed_elements'],'pinned_target_matches':resource_parity['pinned_target_element_matches'],'raw_exact_matches':resource_parity['raw_exact_element_matches'],'compiler_proven_runtime_equivalent_elements':resource_parity['compiler_proven_runtime_equivalent_elements'],'unique_selected_names':resource_parity['unique_selected_resource_names'],'baseline_resource_xml_files_checked':resource_parity['unrelated_baseline_xml_files_checked'],'baseline_resource_xml_files_unchanged':resource_parity['unrelated_baseline_xml_files_unchanged']}[key]
        if resource_summary.get(key)!=actual: raise CheckError(f'resource parity summary is stale: {key}')
    class_counts=dict(Counter(r['category'] for r in full))
    if class_counts!=summary['full_diff']['class_counts']: raise CheckError('summary category counts do not match live full-tree TSV')
    return {'status':'PASS','full_diff_records':len(full),'full_diff_matches_git':True,'historical_inventory_paths':len(historical),'current_manifest':ownership_counts,'full_tree_class_counts':class_counts,
            'validated_exact_files':len(full_ranges),'validated_anchor_fragments':len(anchors),'validated_adaptation_paths':len(manifest_adapt),'adaptation_hunk_rows':len(adaptation_rows),'validated_added_paths':len(added_entries),'validated_overlay_paths':len(overlay_entries),'current_series_ledger_paths':len(current),'resource_parity':{k:resource_parity[k] for k in ('manifest_owned_resource_paths','manifest_owned_changed_resource_keys','candidate_changed_elements','pinned_target_element_matches','raw_exact_element_matches','compiler_proven_runtime_equivalent_elements','compiler_equivalence_evidence','unrelated_baseline_xml_files_checked','unrelated_baseline_xml_files_unchanged','candidate_delta_outside_target_delta','value_mismatches')},
            'sha256':{'resource_parity':resource_report_sha,'full_tree_classification':digest(inv_dir/'full-tree-classification.tsv'),'feature_inventory':digest(repo/'docs/827/feature-inventory.tsv'),'selected_hunks':digest(inv_dir/'selected-hunks.tsv')}}

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--repo',type=Path,default=Path('.'));args=parser.parse_args()
    try: result=validate(args.repo);code=0
    except Exception as exc: result={'status':'FAIL','error':str(exc)};code=1
    print(json.dumps(result,indent=2));return code

if __name__=='__main__': raise SystemExit(main())
