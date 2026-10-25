#!/usr/bin/env bash
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
BUILD_ROOT=${QUICKSTART_EXPORT_BUILD_DIR:-$(mktemp -d "${TMPDIR:-/tmp}/molly827-quickstart-export.XXXXXX")}
mkdir -p "$BUILD_ROOT"
if [[ -n "$(find "$BUILD_ROOT" -mindepth 1 -print -quit)" ]]; then
  printf 'Build output directory must be empty: %s\n' "$BUILD_ROOT" >&2
  exit 2
fi
SDK=${ANDROID_SDK_ROOT:?Set ANDROID_SDK_ROOT}
GRADLE_HOME=${GRADLE_USER_HOME:-/home/x/.gradle}
TARGET_APK=${TARGET_BENCHMARK_APK:?Set TARGET_BENCHMARK_APK}
KEYSTORE=${P2_TEST_KEYSTORE:-/home/x/.android/debug.keystore}
COMPILER=$(find "$GRADLE_HOME/caches/modules-2/files-2.1/org.jetbrains.kotlin/kotlin-compiler-embeddable/2.2.20" -name '*.jar' -print -quit)
STDLIB=$(find "$GRADLE_HOME/caches/modules-2/files-2.1/org.jetbrains.kotlin/kotlin-stdlib/2.2.20" -name 'kotlin-stdlib-2.2.20.jar' -print -quit)
SCRIPT=$(find "$GRADLE_HOME/caches/modules-2/files-2.1/org.jetbrains.kotlin/kotlin-script-runtime/2.2.20" -name '*.jar' -print -quit)
REFLECT=$(find "$GRADLE_HOME/caches/modules-2/files-2.1/org.jetbrains.kotlin/kotlin-reflect/2.2.20" -name '*.jar' -print -quit)
TROVE=$(find "$GRADLE_HOME/caches/modules-2/files-2.1/org.jetbrains.intellij.deps/trove4j/1.0.20200330" -name '*.jar' -print -quit)
ANNOTATIONS=$(find "$GRADLE_HOME/caches/modules-2/files-2.1/org.jetbrains/annotations/23.0.0" -name '*.jar' -print -quit)
COROUTINES=$(find "$GRADLE_HOME/caches/modules-2/files-2.1/org.jetbrains.kotlinx/kotlinx-coroutines-core-jvm/1.10.2" -name '*.jar' -print -quit)
STDLIB7=$(find "$GRADLE_HOME/caches/modules-2/files-2.1/org.jetbrains.kotlin/kotlin-stdlib-jdk7/2.2.20" -name '*.jar' -print -quit)
STDLIB8=$(find "$GRADLE_HOME/caches/modules-2/files-2.1/org.jetbrains.kotlin/kotlin-stdlib-jdk8/2.2.20" -name '*.jar' -print -quit)
TOOLS="$SDK/build-tools/36.0.0"
for f in "$COMPILER" "$STDLIB" "$SCRIPT" "$REFLECT" "$TROVE" "$ANNOTATIONS" "$COROUTINES" "$STDLIB7" "$STDLIB8" "$TARGET_APK" "$KEYSTORE"; do test -f "$f"; done
TARGET_CERT=$("$TOOLS/apksigner" verify --print-certs "$TARGET_APK" | awk -F': ' '/Signer #1 certificate SHA-256 digest:/ {print $2; exit}' | tr -d ':[:space:]' | tr 'A-F' 'a-f')
mkdir -p "$BUILD_ROOT/classes" "$BUILD_ROOT/dex-out"
COMPILER_CP="$COMPILER:$STDLIB:$SCRIPT:$REFLECT:$TROVE:$ANNOTATIONS:$COROUTINES"
"$JAVA_HOME/bin/java" -Xmx512m -cp "$COMPILER_CP" org.jetbrains.kotlin.cli.jvm.K2JVMCompiler \
  -no-stdlib -no-reflect -jvm-target 1.8 \
  -classpath "$STDLIB:$SDK/platforms/android-36.1/android.jar" \
  -d "$BUILD_ROOT/classes" "$HERE/QuickstartExportInstrumentation.kt"
(cd "$BUILD_ROOT/classes" && zip -qr "$BUILD_ROOT/program.jar" org)
"$TOOLS/d8" --min-api 23 --lib "$SDK/platforms/android-36.1/android.jar" --output "$BUILD_ROOT/dex-out" \
  "$BUILD_ROOT/program.jar" "$STDLIB" "$STDLIB7" "$STDLIB8"
"$TOOLS/aapt2" link -I "$SDK/platforms/android-36.1/android.jar" --manifest "$HERE/AndroidManifest.xml" \
  --min-sdk-version 23 --target-sdk-version 30 -o "$BUILD_ROOT/unsigned.apk"
(cd "$BUILD_ROOT" && zip -q -j unsigned.apk dex-out/classes.dex)
"$TOOLS/zipalign" -f -p 4 "$BUILD_ROOT/unsigned.apk" "$BUILD_ROOT/aligned.apk"
"$TOOLS/apksigner" sign --ks "$KEYSTORE" --ks-key-alias androiddebugkey --ks-pass pass:android --key-pass pass:android \
  --out "$BUILD_ROOT/quickstart-exporter.apk" "$BUILD_ROOT/aligned.apk"
ACTUAL_CERT=$("$TOOLS/apksigner" verify --print-certs "$BUILD_ROOT/quickstart-exporter.apk" | awk -F': ' '/Signer #1 certificate SHA-256 digest:/ {print $2; exit}' | tr -d ':[:space:]' | tr 'A-F' 'a-f')
[[ "$ACTUAL_CERT" == "$TARGET_CERT" ]]
sha256sum "$BUILD_ROOT/quickstart-exporter.apk" > "$BUILD_ROOT/apk.sha256"
chmod 600 "$BUILD_ROOT/quickstart-exporter.apk" "$BUILD_ROOT/apk.sha256"
printf 'temporary instrumentation APK built and matching local debug certificate verified\n'
printf 'QUICKSTART_EXPORTER_APK=%s\n' "$BUILD_ROOT/quickstart-exporter.apk"
