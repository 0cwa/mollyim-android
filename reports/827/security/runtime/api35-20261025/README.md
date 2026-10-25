# API 35 synthetic runtime probe — 2026-10-25

## Result

The current-source benchmark APK passed the local synthetic API 35 seed and process-restart probe on a disposable x86_64 Android emulator. The probe verified Android 13+ sensitive clipboard metadata on both copied values (MollySocket parameters and account ID), in addition to the named synthetic UnifiedPush and callback checks in `logs/seed.txt` and `logs/restart.txt`.

This is an emulator-only behavior result. It does not test cryptographic lock timing, a real Signal account, real MollySocket provisioning/delivery, or remote device registration/removal. The callback tests invoke local synthetic APIs and an isolated fake distributor. No Signal or MollySocket endpoint was used.

## Inputs and identity

- Source provenance: Signal base pin `c47a74ba0961903eeaeda6d22347a990056c3e83`, Molly expected pin `0e202dda90785771ff8c87526eaaf30c655f54f3`, expected application commit `d99876269eb6556e37bb2d584ba08e8334e8e5db`, and projected source tree `e783cf54487a5b5d78c3241ec977fd8c8cd23f1d`. The APK build worktree commit was `f71536f6dee918dffa74d52270205d4d744aff5d`; its Git tree equals the expected projected source tree.
- APK: `Signal-Android-play-prod-x86_64-benchmark-8.19.2.apk`, package `org.thoughtcrime.securesms.benchmark`, version `8.19.2`, target SDK 35, x86_64.
- APK SHA-256: `2cd6047804e5aca640357bc73dc10010de9c0087e880efa8f474615332c91b1b` (109,315,082 bytes).
- APK signer certificate SHA-256: `35c6bddc3e55030d930bc852106b613cee39ba30ef65089d4fa079cdfed9b260` (local Android debug certificate). The runner was signed by the same local debug keystore; certificate equality was checked by `build.sh`.
- Probe APK SHA-256: `e7f716265b0283c8e027a7d31606fd6a055bf6a5f9900daca5c328845c406415`.
- Fake distributor APK SHA-256: `a59831815c47f0dcb0bc48e468bcce72dfac4b6a6ee3fda32907c56b56839a08`; it declares no permissions, including no `INTERNET` permission.
- Android: API 35 (Android 15), AVD `molly827-api35`, emulator serial `emulator-5554`, x86_64 Google APIs image. Exact OS properties are in `android-*.txt`.

## Isolation and steps

1. Started the fresh disposable AVD with `-wipe-data`; no prior AVD identity or app data was reused.
2. Installed the candidate APK, cleared its package data, and granted `POST_NOTIFICATIONS` on the disposable emulator.
3. Set airplane mode, disabled Wi-Fi and mobile data, then as emulator root set IPv4 and IPv6 OUTPUT policies to DROP with only loopback allowed. The captured rules in `logs/ipv4-output-rules.txt` and `logs/ipv6-output-rules.txt` show exactly these two rules per family; the runner fails closed if they differ.
4. Installed the permission-free fake distributor and test instrumentation runner. The app's synthetic benchmark setup creates a local-only benchmark identity. Instrumentation and fake distributor use no live account, credentials, server, or network.
5. Ran seed phase and process-restart phase with `am instrument`; both reported `probe_result=PASS` and exit code 0. The runner restored the connector test state and uninstalled the fake distributor on exit.
6. Shut down the emulator after capturing results. The guest build properties, radio settings, firewall rules, install results, and phase output are retained in `logs/`.

The reproducible text-only harness inputs are copied under `harness/`; exact passing and failed phase logs are retained under `logs/` and `attempts/`. APK binaries, keystores, generated classes, emulator startup output, and the generated public boot key are omitted.

## Attempt history and limits

The first run reached the synthetic account and fake callback checks, then failed before clipboard assertions because the harness resolved the benchmark variant's absent launcher activity to a restore/setup flow that never acquired focus. A direct check confirmed that the benchmark variant has no `MAIN`/`LAUNCHER` activity and that explicit `MainActivity` starts and receives focus. The temporary instrumentation was changed to start `org.thoughtcrime.securesms.MainActivity`; the app source was not changed. The second run passed all seed and restart checks.

The preliminary attempts were denied when the shell sent the explicit `ACTION_AIRPLANE_MODE` broadcast; those failures are preserved in `attempts/`. The final passing run recorded `Broadcast completed: result=0` in `logs/airplane-mode.txt`. The script now treats only this redundant broadcast as best-effort. Airplane mode was enabled, Wi-Fi and mobile data were disabled, the fake distributor declared no permissions, and both guest firewall rules were mandatory and verified.

The API 35 clipboard assertions establish that Android's `ClipDescription.EXTRA_IS_SENSITIVE` metadata was present for both copied payloads during this synthetic run. They do not establish when Android clears clipboard contents, prove cryptographic data lock behavior, or verify what another real app can observe. The API 30 expiry check remains in the original API 30 harness and was not rerun here.

## Reproducibility files

The final adapted Kotlin probe, manifest, build/run/verification scripts, fake distributor sources, API30 baseline source, and complete source diff are included under `harness/`. [Reproduction notes](harness/README.md) list prerequisites and commands. [Toolchain/source receipt](toolchain-receipt.json) records official JDK and Android package archive checksums, the Signal/Molly source pins, the expected projected tree, and the APK receipt path. It contains no credentials or key material.

The first run that reached instrumentation failed only at the synthetic clipboard activity focus check; its exact failed phase output is retained in `attempts/first-complete-run-seed-failure.txt`. The Android 15 airplane broadcast denial is preserved in `attempts/first-run-airplane-broadcast-denial.txt`; the passing run's successful broadcast result is in `logs/airplane-mode.txt`. SHA-256 values for both passing phases and the retained failure are in the toolchain/source receipt.
