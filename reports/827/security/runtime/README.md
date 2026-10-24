# Retained security evidence

This directory carries the sources and raw outputs for earlier scoped checks so reviewers can assess what actually ran. It contains no APKs, signing keys, user credentials, or account data. The generated artifacts remain private and were omitted from this handoff.

## Historical API 30 Android run

`runtime-results.json` records the benchmark APK SHA-256 `d9f862681bd0afc44cc147f49a82c7480eb899176631ec90934e4f645abca434` and source tree `24a27bf3ddf2f23593f5a11e3230b66b335bc2a3`. Both seed and process-restart phases reported PASS. Raw outputs are in `raw/seed.txt` and `raw/restart.txt`; their hashes are preserved in `SHA256SUMS.txt` and match the original run receipt. The original runner source, build script, and driver are in `api30-source/`. The fake distributor Java source and manifest are in `fake-distributor/`.

The run used a local fake distributor without the INTERNET permission, with emulator network egress blocked. It exercised synthetic REGISTER and initial NEW_ENDPOINT callbacks, MESSAGE and UNREGISTERED callbacks, process restart, notification trigger, backup exclusion, synthetic clipboard handling/expiry, and a missing-VAPID refresh-job transition to WebSocket availability. The missing-VAPID job returned before endpoint or network calls. It did not exercise endpoint rotation, physical-device behavior, a real distributor, Signal account or server registration, MollySocket, or Android 13+ clipboard metadata.

This is historical evidence for tree `24a27bf...`; it predates the F4 callback fix in this worktree. It must not be reported as runtime validation of the fix. The compact Robolectric regression suite for that fix is at [UnifiedPushReceiverAvailabilityTest.kt](../../../../app/src/test/java/org/thoughtcrime/securesms/keyvalue/UnifiedPushReceiverAvailabilityTest.kt) and awaits Gradle execution.

## Registration and transport probes

`network-contracts/` retains Java probes, their scripts and outputs, compiled connector bytecode inspection, and dated Signal-Server source snapshots. The probes used only synthetic DTO values and fake loopback transport data.

- `ConnectionRequestWireTest` verified the exact MollySocket JSON keys and status mapping against candidate compiled classes.
- `RegistrationAttributesWireTest` verified the five linked-device `DeviceAttributes` fields against the candidate compiled DTO; `verify_registration_source_contract.py` compares them with the dated server request and handler sources.
- `RemoveDeviceFlowTest` verified the repository throws on failed remote unlink and returns normally on success using a controlled fake repository.
- `check_candidate_contracts.py` inspected compiled redirect configuration and selected manifest/connector behavior.
- `UserInfoProbe` used fake URL userinfo and a fragment against exact cached OkHttp 5.3.2 on a local TLS server; no Authorization header was generated and the fragment was absent from the request target.

The scripts reference the original workspace's Gradle cache and compiled candidate classes. Their sources, input server snapshots, compiled small probe classes, connector inspection JAR, and raw outputs are retained here; a maintainer needs the pinned source build and dependency cache to rerun them. `SHA256SUMS.txt` records key raw outputs. These checks establish bounded source/wire behavior, not production server deployment or live account compatibility.

## Provenance and status

The API 30 benchmark and probe APK hashes, server-source commit metadata, raw Bundle hashes, and test limits are recorded in `runtime-results.json`, `network-contracts/REGISTRATION-CONTRACT.md`, and `network-contracts/server-source-evidence/`. APK and emulator-image binary artifacts were omitted. A pass in this evidence bundle applies only to its recorded historical candidate tree and scoped synthetic scenario.
