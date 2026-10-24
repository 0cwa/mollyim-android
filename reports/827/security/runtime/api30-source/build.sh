#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")" && pwd)
SDK=${ANDROID_SDK_ROOT:-/workspace/android-sdk}
GRADLE_HOME=${GRADLE_USER_HOME:-/workspace/gradle-home}
COMPILER=$(find "$GRADLE_HOME/caches/modules-2/files-2.1/org.jetbrains.kotlin/kotlin-compiler-embeddable/2.2.20" -name '*.jar' -print -quit)
STDLIB=$(find "$GRADLE_HOME/caches/modules-2/files-2.1/org.jetbrains.kotlin/kotlin-stdlib/2.2.20" -name 'kotlin-stdlib-2.2.20.jar' -print -quit)
SCRIPT=$(find "$GRADLE_HOME/caches/modules-2/files-2.1/org.jetbrains.kotlin/kotlin-script-runtime/2.2.20" -name '*.jar' -print -quit)
REFLECT=$(find "$GRADLE_HOME/caches/modules-2/files-2.1/org.jetbrains.kotlin/kotlin-reflect/2.2.20" -name '*.jar' -print -quit)
TROVE=$(find "$GRADLE_HOME/caches/modules-2/files-2.1/org.jetbrains.intellij.deps/trove4j/1.0.20200330" -name '*.jar' -print -quit)
ANNOTATIONS=$(find "$GRADLE_HOME/caches/modules-2/files-2.1/org.jetbrains/annotations/23.0.0" -name '*.jar' -print -quit)
COROUTINES=$(find "$GRADLE_HOME/caches/modules-2/files-2.1/org.jetbrains.kotlinx/kotlinx-coroutines-core-jvm/1.10.2" -name '*.jar' -print -quit)
STDLIB7=$(find "$GRADLE_HOME/caches/modules-2/files-2.1/org.jetbrains.kotlin/kotlin-stdlib-jdk7/2.2.20" -name '*.jar' -print -quit)
STDLIB8=$(find "$GRADLE_HOME/caches/modules-2/files-2.1/org.jetbrains.kotlin/kotlin-stdlib-jdk8/2.2.20" -name '*.jar' -print -quit)
KEYSTORE=${1:-${P2_TEST_KEYSTORE:-/home/agent/.android/debug.keystore}}

for tool in "$COMPILER" "$STDLIB" "$SCRIPT" "$REFLECT" "$TROVE" "$ANNOTATIONS" "$COROUTINES" "$STDLIB7" "$STDLIB8"; do
  test -f "$tool"
done

test -f "$KEYSTORE"
rm -rf "$ROOT/build/classes" "$ROOT/build/program.jar" "$ROOT/build/dex-out" "$ROOT/build/probe-unsigned.apk" "$ROOT/p2-probe-aligned.apk" "$ROOT/p2-probe.apk"
mkdir -p "$ROOT/build/classes" "$ROOT/build/dex-out"

COMPILER_CP="$COMPILER:$STDLIB:$SCRIPT:$REFLECT:$TROVE:$ANNOTATIONS:$COROUTINES"
java -Xmx512m -cp "$COMPILER_CP" org.jetbrains.kotlin.cli.jvm.K2JVMCompiler \
  -no-stdlib -no-reflect -jvm-target 1.8 \
  -classpath "$STDLIB:$SDK/platforms/android-36/android.jar" \
  -d "$ROOT/build/classes" "$ROOT/src/ProbeInstrumentation.kt"

(cd "$ROOT/build/classes" && zip -qr "$ROOT/build/program.jar" org)
"$SDK/build-tools/36.0.0/d8" --min-api 23 \
  --lib "$SDK/platforms/android-36/android.jar" \
  --output "$ROOT/build/dex-out" \
  "$ROOT/build/program.jar" "$STDLIB" "$STDLIB7" "$STDLIB8"

"$SDK/build-tools/36.0.0/aapt2" link \
  -I "$SDK/platforms/android-36/android.jar" \
  --manifest "$ROOT/AndroidManifest.xml" \
  --min-sdk-version 23 --target-sdk-version 30 \
  -o "$ROOT/build/probe-unsigned.apk"
(cd "$ROOT/build" && zip -q -j probe-unsigned.apk dex-out/classes.dex)
"$SDK/build-tools/36.0.0/zipalign" -f -p 4 \
  "$ROOT/build/probe-unsigned.apk" "$ROOT/p2-probe-aligned.apk"
"$SDK/build-tools/36.0.0/apksigner" sign \
  --ks "$KEYSTORE" --ks-key-alias androiddebugkey \
  --ks-pass pass:android --key-pass pass:android \
  --out "$ROOT/p2-probe.apk" "$ROOT/p2-probe-aligned.apk"

"$SDK/build-tools/36.0.0/apksigner" verify --verbose --print-certs "$ROOT/p2-probe.apk" \
  > "$ROOT/build/signature.txt"
if ! rg -q 'bcc92af314f8d8c0187e3d7d30bcb2ce07fae17a6cebaec604b5aa19a88241ea' "$ROOT/build/signature.txt"; then
  echo "runner APK certificate does not match the benchmark app debug certificate" >&2
  exit 1
fi
sha256sum "$ROOT/p2-probe.apk" > "$ROOT/build/apk.sha256"
echo "Built $ROOT/p2-probe.apk"
cat "$ROOT/build/apk.sha256"
