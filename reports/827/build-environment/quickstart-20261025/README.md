# Synthetic Quickstart packaging fixture provenance

Date: 2026-10-25. This evidence records creation of two **private build inputs** to let the existing `copyQuickstartCredentialsPlayProdQuickstart` Gradle task complete. It does not claim that a Quickstart APK was installed, launched, or accepted at runtime. The fixture files themselves are intentionally not in this repository.

## Source and artifact identity

- Original application source commit: `d99876269eb6556e37bb2d584ba08e8334e8e5db` (physical source tree `c39f3550a8ea40ccd81bf6f853eb2efe83955307`).
- Replay commit: `f71536f6dee918dffa74d52270205d4d744aff5d` (replay worktree commit, including the pinned Gradle distribution checksum verification change).
- Projected replay tree and APK source tree: `e783cf54487a5b5d78c3241ec977fd8c8cd23f1d`.
- Input benchmark APK: Play Prod Benchmark, package `org.thoughtcrime.securesms.benchmark`, version `8.19.2`, x86_64, target SDK 35; SHA-256 `2cd6047804e5aca640357bc73dc10010de9c0087e880efa8f474615332c91b1b`.
- APK signer: local Android Debug certificate SHA-256 `35c6bddc3e55030d930bc852106b613cee39ba30ef65089d4fa079cdfed9b260`. The temporary exporter instrumentation was signed with the same local, non-production debug key so Android allowed it to instrument the benchmark package.

## Result

The benchmark app's existing `BenchmarkSetupActivity` ran its `message-send` setup on a freshly wiped API 35 emulator. That benchmark setup creates synthetic local `TestUsers` data and blocks Signal network access. The temporary instrumentation then invoked the app's canonical `QuickstartCredentialExporter.export` method. The result was copied byte-for-byte into the two filenames selected by the Gradle task:

- `prod_synthetic.json`
- `staging_synthetic.json`

Both validated against the pinned `QuickstartCredentials` field names and types and had valid base64-encoded key/prekey fields. Each file was 14,114 bytes with SHA-256 `6188ab053563f86c02f1583e868aca91881025a70d53b992794644f1fe457ee1`. In the generating environment the directory was mode 700 and the two files mode 600. The validator prints filenames, sizes, hashes, and pass/fail only; it does not print credential values.

The original benchmark APK app data was cleared and the temporary instrumentation package uninstalled after export. The emulator was shut down. The final recorded airplane-mode value was `1`; IPv4 and IPv6 guest OUTPUT policies were DROP with loopback as the only accepted output. See `logs/` for sanitized command results. The first instrumentation attempt returned `java.lang.NoSuchFieldException`. The sanitized first-attempt log does not retain the missing member name. The corrected harness uses the `SignalStore.account()` accessor, and the second attempt passed; both records are retained.

## Reproduction inputs

This bundle has the instrumentation source (`QuickstartExportInstrumentation.kt`), its minimal manifest, the temporary compiler/signing script (`build.sh`), and the values-free schema validator (`validate-schema.py`). The source app itself already contains the canonical exporter; no app source was changed for this operation. The report copy of `build.sh` differs from the generation-session script only in directing intermediate files and the instrumentation APK to a private temporary output directory instead of beside the session harness. The report copy was run successfully after that adjustment; it produced a signer-matching harness APK under `/tmp` and did not add build outputs to this directory.

The tested toolchain was [Eclipse Temurin JDK `21.0.2+13`](https://github.com/adoptium/temurin21-binaries/releases/tag/jdk-21.0.2%2B13) (archive SHA-256 `454bebb2c9fe48d981341461ffb6bf1017c7b7c6e15c6b0c29b959194ba3aaa5`), Android SDK Platform `android-36.1` revision 1, Build Tools `36.0.0`, and compiler artifacts from the existing Gradle cache. The script expects Kotlin compiler, stdlib, script-runtime, reflect, and stdlib-jdk7/jdk8 `2.2.20`; Trove `1.0.20200330`; JetBrains annotations `23.0.0`; and kotlinx-coroutines-core-jvm `1.10.2`. D8, aapt2, zipalign, and apksigner come from Build Tools `36.0.0`. The generator was compiled with `android-36.1/android.jar`. A compatible installed emulator and x86_64 API 35 system image are also required; the tested AVD was `molly827-api35`. The benchmark APK and a local debug keystore matching its certificate are required; neither is included here. The build script accepts `ANDROID_SDK_ROOT`, `JAVA_HOME`, `GRADLE_USER_HOME`, `TARGET_BENCHMARK_APK`, and `P2_TEST_KEYSTORE` through environment variables.

To reproduce in a disposable API 35 emulator, boot a fresh `-wipe-data -no-snapshot` AVD and confirm API level 35. Before installing anything, enable airplane mode and add guest firewall rules:

```sh
adb root
adb shell settings put global airplane_mode_on 1
adb shell iptables -P OUTPUT DROP
adb shell iptables -A OUTPUT -o lo -j ACCEPT
adb shell ip6tables -P OUTPUT DROP
adb shell ip6tables -A OUTPUT -o lo -j ACCEPT
adb shell iptables -S OUTPUT
adb shell ip6tables -S OUTPUT
```

Build the instrumentation using `build.sh` and a local benchmark APK signed by the selected debug keystore. Install the benchmark APK and the generated temporary instrumentation APK, then run:

```sh
adb shell am instrument -w \
  org.thoughtcrime.securesms.quickstartfixture/org.thoughtcrime.securesms.quickstartfixture.QuickstartExportInstrumentation
```

Require `fixture_status=PASS`, then pull the exported file from:
`/sdcard/Android/data/org.thoughtcrime.securesms.benchmark/files/quickstart-credentials.json`.
Create a private fixture directory (mode 700), place the pulled file as `prod_synthetic.json`, copy it to `staging_synthetic.json`, and set both files to mode 600. Run:

```sh
python3 validate-schema.py /path/to/private/quickstart-fixtures
sha256sum /path/to/private/quickstart-fixtures/*.json
```

For the build owner, set the ignored root `local.properties` entry to:
`quickstart.credentials.dir=/path/to/private/quickstart-fixtures`.

The generated fixture includes synthetic account secrets, so retain it outside version control and do not print its contents. After export, clear benchmark app data, uninstall the temporary instrumentation package, and shut down the emulator.

## Limits

These files are packaging inputs only. The benchmark `TestUsers` setup contains a known PNI prekey-generation concern: the PNI signed and Kyber last-resort prekeys appear to be generated using the ACI identity key. This task did not modify or correct that code. Although serialization schema and base64 shape were checked, the generated credentials were not validated through Quickstart deserialization/registration, protocol or cryptographic acceptance, or a Quickstart APK launch. No live Signal account, MollySocket service, production credential, or live network was used. These results do not establish delivery, account registration against a server, crypto correctness, or any Quickstart runtime behavior.

For the recorded SDK package revisions, `sdkmanager` metadata reported platform `platforms;android-36.1` revision 1 (`platform-36.1_r01.zip`, 66,270,841 bytes, official SHA-1 `f87dc23b7ddba6934908da6cfb58fd5b258077ce`) and Build Tools `36.0.0` (`build-tools_r36_linux.zip`, 63,737,259 bytes, official SHA-1 `b0b6376977657e8ad9b969bacf4093601da2c6fb`). The Android NDK `28.0.13004108` was part of the app build toolchain but is not needed to compile this standalone exporter instrumentation. Install the SDK packages with `sdkmanager --sdk_root="$ANDROID_SDK_ROOT" --install 'platforms;android-36.1' 'build-tools;36.0.0'`; use the existing API 35 emulator image or install a compatible API 35 x86_64 image through SDK Manager.

The pinned source paths used for this run are `app/src/main/java/org/thoughtcrime/securesms/registration/data/QuickstartCredentialExporter.kt`, `app/src/main/java/org/thoughtcrime/securesms/registration/data/QuickstartCredentials.kt`, and `app/src/benchmarkShared/java/org/signal/benchmark/setup/TestUsers.kt`. The Gradle consumer is `app/build.gradle.kts` (`CopyQuickstartCredentialsTask` and the Quickstart variant asset wiring). These references let a reviewer check the exporter, serializer schema, local setup, and filename-prefix behavior in the identified source tree.

The minimal instrumentation APK can be rebuilt with the checked-in `build.sh` after setting the documented variables, for example:

```sh
ANDROID_SDK_ROOT=/path/to/android-sdk \
JAVA_HOME=/path/to/jdk-21 \
TARGET_BENCHMARK_APK=/path/to/Signal-Android-play-prod-x86_64-benchmark.apk \
P2_TEST_KEYSTORE=/path/to/local-debug.keystore \
./build.sh
```

The build script verifies that the instrumentation APK signer matches the benchmark APK signer before installation. The keystore is an existing local debug key and is not part of this evidence bundle.

Android 15 denied the shell-issued `AIRPLANE_MODE` broadcast with `SecurityException`; the global airplane-mode setting itself was set to and read back as `1`. The IPv4 and IPv6 firewall rules were separately captured and verified before installing the benchmark APK. The `logs/airplane-broadcast-attempt.txt` record preserves the denial, while the settings and firewall logs preserve the controls that succeeded.
