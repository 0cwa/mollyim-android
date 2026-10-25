#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")" && pwd)
SDK=${ANDROID_SDK_ROOT:?Set ANDROID_SDK_ROOT to the isolated SDK}
GRADLE_HOME=${GRADLE_USER_HOME:-/home/x/.gradle}
TARGET_APK=${TARGET_BENCHMARK_APK:?Set TARGET_BENCHMARK_APK to the freshly built benchmark APK}
COMPILER=$(find "$GRADLE_HOME/caches/modules-2/files-2.1/org.jetbrains.kotlin/kotlin-compiler-embeddable/2.2.20" -name '*.jar' -print -quit)
STDLIB=$(find "$GRADLE_HOME/caches/modules-2/files-2.1/org.jetbrains.kotlin/kotlin-stdlib/2.2.20" -name 'kotlin-stdlib-2.2.20.jar' -print -quit)
SCRIPT=$(find "$GRADLE_HOME/caches/modules-2/files-2.1/org.jetbrains.kotlin/kotlin-script-runtime/2.2.20" -name '*.jar' -print -quit)
REFLECT=$(find "$GRADLE_HOME/caches/modules-2/files-2.1/org.jetbrains.kotlin/kotlin-reflect/2.2.20" -name '*.jar' -print -quit)
TROVE=$(find "$GRADLE_HOME/caches/modules-2/files-2.1/org.jetbrains.intellij.deps/trove4j/1.0.20200330" -name '*.jar' -print -quit)
ANNOTATIONS=$(find "$GRADLE_HOME/caches/modules-2/files-2.1/org.jetbrains/annotations/23.0.0" -name '*.jar' -print -quit)
COROUTINES=$(find "$GRADLE_HOME/caches/modules-2/files-2.1/org.jetbrains.kotlinx/kotlinx-coroutines-core-jvm/1.10.2" -name '*.jar' -print -quit)
STDLIB7=$(find "$GRADLE_HOME/caches/modules-2/files-2.1/org.jetbrains.kotlin/kotlin-stdlib-jdk7/2.2.20" -name '*.jar' -print -quit)
STDLIB8=$(find "$GRADLE_HOME/caches/modules-2/files-2.1/org.jetbrains.kotlin/kotlin-stdlib-jdk8/2.2.20" -name '*.jar' -print -quit)
KEYSTORE=${1:-${P2_TEST_KEYSTORE:-/home/x/.android/debug.keystore}}
APKSIGNER="$SDK/build-tools/36.0.0/apksigner"
AAPT="$SDK/build-tools/36.0.0/aapt"

for tool in "$COMPILER" "$STDLIB" "$SCRIPT" "$REFLECT" "$TROVE" "$ANNOTATIONS" "$COROUTINES" "$STDLIB7" "$STDLIB8"; do test -f "$tool"; done
test -f "$TARGET_APK"
test -f "$KEYSTORE"
package_line=$("$AAPT" dump badging "$TARGET_APK" | sed -n '1p')
[[ "$package_line" == *"org.thoughtcrime.securesms.benchmark"* ]] || { echo "Expected benchmark package, got: $package_line" >&2; exit 2; }
target_cert=$("$APKSIGNER" verify --print-certs "$TARGET_APK" | awk -F': ' '/Signer #1 certificate SHA-256 digest:/ {print $2; exit}' | tr -d ':[:space:]' | tr 'A-F' 'a-f')
test -n "$target_cert"

rm -rf "$ROOT/build" "$ROOT/p2-probe-aligned.apk" "$ROOT/p2-probe.apk"
mkdir -p "$ROOT/build/classes" "$ROOT/build/dex-out"
COMPILER_CP="$COMPILER:$STDLIB:$SCRIPT:$REFLECT:$TROVE:$ANNOTATIONS:$COROUTINES"
java -Xmx512m -cp "$COMPILER_CP" org.jetbrains.kotlin.cli.jvm.K2JVMCompiler \
  -no-stdlib -no-reflect -jvm-target 1.8 \
  -classpath "$STDLIB:$SDK/platforms/android-36.1/android.jar" \
  -d "$ROOT/build/classes" "$ROOT/ProbeInstrumentation.kt"
(cd "$ROOT/build/classes" && zip -qr "$ROOT/build/program.jar" org)
"$SDK/build-tools/36.0.0/d8" --min-api 23 \
  --lib "$SDK/platforms/android-36.1/android.jar" \
  --output "$ROOT/build/dex-out" \
  "$ROOT/build/program.jar" "$STDLIB" "$STDLIB7" "$STDLIB8"
"$SDK/build-tools/36.0.0/aapt2" link \
  -I "$SDK/platforms/android-36.1/android.jar" \
  --manifest "$ROOT/AndroidManifest.xml" \
  --min-sdk-version 23 --target-sdk-version 35 \
  -o "$ROOT/build/probe-unsigned.apk"
(cd "$ROOT/build" && zip -q -j probe-unsigned.apk dex-out/classes.dex)
"$SDK/build-tools/36.0.0/zipalign" -f -p 4 \
  "$ROOT/build/probe-unsigned.apk" "$ROOT/p2-probe-aligned.apk"
"$APKSIGNER" sign --ks "$KEYSTORE" --ks-key-alias androiddebugkey \
  --ks-pass pass:android --key-pass pass:android \
  --out "$ROOT/p2-probe.apk" "$ROOT/p2-probe-aligned.apk"
runner_cert=$("$APKSIGNER" verify --print-certs "$ROOT/p2-probe.apk" | awk -F': ' '/Signer #1 certificate SHA-256 digest:/ {print $2; exit}' | tr -d ':[:space:]' | tr 'A-F' 'a-f')
[[ "$runner_cert" == "$target_cert" ]] || { echo "runner APK signer differs from target benchmark signer" >&2; exit 3; }
"$APKSIGNER" verify --verbose "$ROOT/p2-probe.apk" > "$ROOT/build/signature.txt"
sha256sum "$TARGET_APK" > "$ROOT/build/target.apk.sha256"
sha256sum "$ROOT/p2-probe.apk" > "$ROOT/build/apk.sha256"
printf 'candidate signer SHA256: %s\n' "$target_cert"
cat "$ROOT/build/target.apk.sha256" "$ROOT/build/apk.sha256"
