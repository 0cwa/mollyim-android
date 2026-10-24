# P2 local-only Android instrumentation probe

This is a standalone instrumentation APK built outside the candidate checkout. It targets the already-built `org.thoughtcrime.securesms.benchmark` package, uses reflection so it does not compile against app sources, and has no Gradle dependency. It is signed with the Android Debug keystore whose certificate SHA-256 matches the benchmark APK.

Checks implemented:

- `NotificationDeliveryMethod` serialize/deserialize for FCM, WebSocket, UnifiedPush.
- `SettingsValues.getPreferredNotificationMethod()` with the explicit preference key removed and the FCM flag toggled false/true, restoring both values in `finally`.
- `UnifiedPushValues.getKeysToIncludeInBackup()` is empty.
- Candidate `UnifiedPushSettingsViewModel.copyParamsToClipboard` and `copyAciToClipboard` using synthetic device/endpoint values (restored afterward); it launches the target app’s real launcher activity, waits up to 20 seconds for window focus before clipboard reads, and verifies the actual 60-second clipboard-clear alarm on API 30. Android 13+ sensitive clipboard metadata is not covered on this API 30 runtime.
- Installs a local fake distributor (`org.example.upfake`, no `INTERNET` permission), then calls the target app's actual `UnifiedPush.saveDistributor` and `registerApp` APIs. It waits for the fake `REGISTER` / target `NEW_ENDPOINT` round trip with a loopback-only URL.
- The driver launches the fake distributor's exported no-op `BootstrapActivity` once after installation. This clears Android's fresh-install stopped-package state before testing the real connector broadcast flow; it does not bypass the target API or inject endpoint state.
- Sends the fixture's `MESSAGE` callback containing only `{"test":true}`, then verifies candidate `lastReceivedTime` and test notification id 51216. After `am force-stop`, it verifies the synthetic endpoint and connector registration persist and repeats the message callback.
- Requests the fake distributor's synthetic unsolicited `UNREGISTERED` callback while the connector token is still mapped. It verifies the candidate receiver removes the saved distributor, token mapping, and endpoint, then calls the actual `unregisterApp` API to check idempotent local cleanup. This does not claim an UNREGISTER request/ack round trip because the connector removes its token mapping before dispatching that request.
- Runs the actual `UnifiedPushRefreshJob.onRun()` against an explicitly injected synthetic state (registered benchmark fixture, preferred UnifiedPush, enabled, registration status REGISTERED, no device/VAPID, FCM disabled). The job must transition status to PENDING and `AccountValues.isPushAvailable` to false; the missing VAPID key returns before any distributor/MollySocket request. Original preference, account FCM flag, and UnifiedPush fields are restored in `finally`, then the benchmark fake network is reset/restarted.
- Restores the captured connector SharedPreferences snapshot, original endpoint/timestamp, and notification state afterward.

The fake package exercises the local UnifiedPush broadcast protocol only. The refresh-job check exercises the missing-VAPID early-return/push-availability fallback, not MollySocket registration. These checks do not prove interoperability with a real distributor, remote endpoint provisioning, live push delivery, or FCM behavior. Neither runner nor fake distributor declares `INTERNET`; the driver also disables airplane-mode radios before testing. The `run-probe.sh` driver requires the caller to name and confirm a disposable emulator serial. It uninstalls the synthetic fake-distributor package on exit. Do not run on a user's primary device. The benchmark's local `message-send` fixture should already be seeded; the runner checks for a registered, unlocked benchmark fixture and does not provision accounts itself.

Build with `./build.sh [debug-keystore-path]`; by default it uses `/home/agent/.android/debug.keystore`. Set `ANDROID_SDK_ROOT`, `GRADLE_USER_HOME`, and `FAKE_DISTRIBUTOR_APK` to override the local tool paths when needed. The build script compiles only this standalone runner; it does not build or modify the candidate app. `./test-result-parser.sh` checks that the driver accepts `INSTRUMENTATION_RESULT` PASS output and rejects FAIL/wrong-phase output.

Run with:

```sh
./build.sh
```

Run only after the disposable API30 emulator is ready and the benchmark local fixture has been seeded:

```sh
ADB_SERIAL=emulator-5554 ./run-probe.sh emulator-5554
```

Instrument output and install logs are written under `./results`. The token value is never emitted. The completed API 30 run and evidence are recorded in [`receipt.md`](receipt.md) and `results/run-20261024T050903Z/`.
