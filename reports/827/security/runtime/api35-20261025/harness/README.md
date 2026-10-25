# Reproduce the API35 probe

This directory contains the text-only harness inputs used for the API 35 runtime run. The adapted Kotlin probe is in `api35-source/`; `original-api30/` preserves the baseline source; `ProbeInstrumentation-api30-to-api35.diff` records the source adaptation with zero context lines and ignores trailing-whitespace-only differences; the original and adapted source files are both included byte-for-byte. `fake-distributor/` contains only source, manifest, and build script. No APK, keystore, generated class, DEX, or other build output is included.

## Build prerequisites

Use the pinned local JDK 21.0.2+13 and Android SDK 36.1 rev1 plus Build Tools 36.0.0 from `toolchain-receipt.json`. The probe build uses Kotlin compiler 2.2.20 and related jars already present in Gradle's module cache. The signing script expects the same local Android debug keystore as the benchmark APK and verifies certificate equality; it does not read or copy keystore contents. The fake distributor declares no permissions.

## Build and run

Set `JAVA_HOME=/tmp/molly827-toolchain/jdk21`, `ANDROID_SDK_ROOT=/tmp/molly827-toolchain/android-sdk`, and prepend `$JAVA_HOME/bin`, `/tmp/molly827-toolchain/bin`, and `$ANDROID_SDK_ROOT/platform-tools` to `PATH`. Then set `TARGET_BENCHMARK_APK` to the candidate APK and run:

```sh
harness/api35-source/build.sh
harness/fake-distributor/build.sh
```

Install the emulator, platform-tools, and API35 Google APIs x86_64 system image if they are not already available, then create a disposable AVD in a task-specific user home:

```sh
export ANDROID_USER_HOME=/tmp/molly827-api35-user
export ANDROID_AVD_HOME="$ANDROID_USER_HOME/avd"
SDKMANAGER="$ANDROID_SDK_ROOT/cmdline-tools/latest/bin/sdkmanager"
AVDMANAGER="$ANDROID_SDK_ROOT/cmdline-tools/latest/bin/avdmanager"
"$SDKMANAGER" --sdk_root="$ANDROID_SDK_ROOT" \
  "emulator" "platform-tools" "system-images;android-35;google_apis;x86_64"
printf 'no\n' | "$AVDMANAGER" --sdk_root="$ANDROID_SDK_ROOT" create avd \
  --force --name molly827-api35 --package "system-images;android-35;google_apis;x86_64" --device pixel_2
"$ANDROID_SDK_ROOT/emulator/emulator" -avd molly827-api35 -no-window -no-audio \
  -no-boot-anim -no-snapshot -wipe-data -accel auto
```

Wait until `adb -s emulator-5554 shell getprop sys.boot_completed` returns `1`, then follow `../run-command.txt` in a second shell with `ANDROID_SDK_ROOT` set. The run script validates the AVD name and target APK hash, clears only the benchmark app package data on that emulator, requires root, sets airplane mode, requests Wi-Fi/mobile radio disablement, requires exact IPv4 and IPv6 egress-drop rules, runs seed and restart phases, verifies the phase result markers, and removes the fake distributor on exit. Do not use a real account or endpoint. The complete result from the original run is retained under `../logs/`; toolchain and image details are in `../toolchain-receipt.json`.

Preliminary attempts were denied when the Android 15 shell sent the explicit airplane-mode broadcast; those logs are in `../attempts/`. The final passing run recorded `Broadcast completed: result=0` in `../logs/airplane-mode.txt`. The runner treats only that redundant broadcast as best-effort. It sets airplane mode and requests radio disablement; the no-egress boundary is enforced by root and exact IPv4/IPv6 OUTPUT firewall checks. The permission-free fake is also used. `api35-source/ProbeInstrumentation.kt` starts `MainActivity` explicitly because the benchmark APK variant has no launcher activity.
