# UnifiedPush and MollySocket security boundaries

This document describes the selected #827 receiver, notification routing,
MollySocket HTTP calls, and linked-device credentials. Current acceptance work
and historical probe results are in
[issue #5](https://github.com/0cwa/mollyim-android/issues/5).

## Distributor and server trust

The user selects a UnifiedPush distributor and configures a MollySocket server.
The distributor receives a connector registration token and can cause wake-ups
and control callbacks. The MollySocket server receives the account UUID,
linked-device ID/password, and push endpoint in its connection request. Push
payloads are delivery triggers rather than Signal message contents.

The [exported receiver](../../app/src/main/AndroidManifest.xml) has no Android
sender permission or signature check. It subclasses the pinned connector's
`MessagingReceiver`; callback admission relies on registration-token and
instance checks rather than sender-package authentication. A selected distributor
possessing the token can send false control events and observe delivery metadata.

## Availability and locked callbacks

[`UnifiedPushReceiver`](../../app/src/main/java/im/molly/unifiedpush/receiver/UnifiedPushReceiver.kt)
uses `KeyCachingService.isLocked()`. Locked endpoint rotation, registration failure,
and distributor removal invalidate registered availability without reading the
endpoint/device/VAPID properties. When availability changes from registered, the
network restarts and a `PushServiceEvent` allows routing to respond to that change.

An unlocked changed endpoint moves `REGISTERED` to `PENDING` before refresh;
refresh failure can then mark it `UNKNOWN`. An unchanged endpoint does not enqueue
another refresh. These transitions do not establish successful live registration.

While locked, an urgent payload can produce a generic “may have messages” notice
only when the passphrase-lock notification preference allows it. Classification
uses string searches for `"urgent":true` and `"test":true`, which can misclassify
unexpected payloads. The generic notice contains no Signal message contents.

This PoC uses Signal's UI passphrase lock, with a key/value store that remains
accessible while locked. Its property-access boundaries do not establish Molly's
encrypted database/master-secret lock behavior or credential erasure.

## Provisioning and HTTP

[`MollySocketRepository`](../../app/src/main/java/im/molly/unifiedpush/MollySocketRepository.kt)
creates a secondary Signal device, then loads prekeys before returning its record.
If remote registration succeeds and prekey loading fails, the device can remain
orphaned remotely because its local recovery record has not yet been returned for
persistence. Repeated failures can consume linked-device slots. Recovery for this
inherited flow is tracked in [issue #5](https://github.com/0cwa/mollyim-android/issues/5).

MollySocket discovery and registration disable HTTP and HTTPS redirects. The
registration POST carries credentials in its JSON body.
[`MollySocket.parseLink`](../../app/src/main/java/im/molly/unifiedpush/model/MollySocket.kt)
requires HTTPS for web-server links but does not explicitly reject URL userinfo
or fragments. This input-validation limitation does not by itself demonstrate a
credential leak or compatibility with a deployed server.

`removeDevice()` throws when the underlying removal API reports failure.
End-to-end removal, retry, and recovery still require service tests.

## Credentials and copying

[`UnifiedPushValues`](../../app/src/main/java/org/thoughtcrime/securesms/keyvalue/UnifiedPushValues.kt)
stores the device password and returns an empty backup-key list.
[`MollySocketDevice.toString()`](../../app/src/main/java/im/molly/unifiedpush/model/MollySocketDevice.kt)
prints the device ID without its password. The settings
[copy methods](../../app/src/main/java/im/molly/unifiedpush/components/settings/app/notifications/UnifiedPushSettingsViewModel.kt)
intentionally export provisioning parameters using `writeSensitiveTextToClipboard`.
Sensitive metadata and intended lifetime do not establish how every Android
version or another app presents or retains the content.

## Regression coverage

[`UnifiedPushReceiverAvailabilityTest.kt`](../../app/src/test/java/org/thoughtcrime/securesms/keyvalue/UnifiedPushReceiverAvailabilityTest.kt)
uses an in-memory store, a locked-state stub, and mocked network/distributor
boundaries. It covers availability invalidation, preservation of endpoint/device
credentials on locked callbacks, changed-endpoint failure fallback, same-endpoint
idempotence, the urgent-notice preference, malformed/test payloads, and connector
rejection of missing or unknown registration tokens. The refresh failure test
injects a repository failure; it does not exercise real HTTP retry timing.
The [runbook](RUNBOOK.md#build-test-and-lint) provides the focused command.

Live linking and delivery, interrupted provisioning, physical-device behavior,
clipboard expiry/presentation, locked notification presentation, and cryptographic
lock semantics require separate evidence. Replay or synthetic callbacks cannot
establish complete security acceptance; current results belong in
[issue #5](https://github.com/0cwa/mollyim-android/issues/5).
