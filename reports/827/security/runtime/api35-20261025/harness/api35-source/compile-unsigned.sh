#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")" && pwd)
SDK=${ANDROID_SDK_ROOT:?Set ANDROID_SDK_ROOT to the isolated SDK}
GRADLE_HOME=${GRADLE_USER_HOME:-/home/x/.gradle}
CACHE="$GRADLE_HOME/caches/modules-2/files-2.1"
COMPILER=$(find "$CACHE/org.jetbrains.kotlin/kotlin-compiler-embeddable/2.2.20" -name '*.jar' -print -quit)
STDLIB=$(find "$CACHE/org.jetbrains.kotlin/kotlin-stdlib/2.2.20" -name 'kotlin-stdlib-2.2.20.jar' -print -quit)
SCRIPT=$(find "$CACHE/org.jetbrains.kotlin/kotlin-script-runtime/2.2.20" -name '*.jar' -print -quit)
REFLECT=$(find "$CACHE/org.jetbrains.kotlin/kotlin-reflect/2.2.20" -name '*.jar' -print -quit)
TROVE=$(find "$CACHE/org.jetbrains.intellij.deps/trove4j/1.0.20200330" -name '*.jar' -print -quit)
ANNOTATIONS=$(find "$CACHE/org.jetbrains/annotations/23.0.0" -name '*.jar' -print -quit)
COROUTINES=$(find "$CACHE/org.jetbrains.kotlinx/kotlinx-coroutines-core-jvm/1.10.2" -name '*.jar' -print -quit)
STDLIB7=$(find "$CACHE/org.jetbrains.kotlin/kotlin-stdlib-jdk7/2.2.20" -name '*.jar' -print -quit)
STDLIB8=$(find "$CACHE/org.jetbrains.kotlin/kotlin-stdlib-jdk8/2.2.20" -name '*.jar' -print -quit)
for jar in "$COMPILER" "$STDLIB" "$SCRIPT" "$REFLECT" "$TROVE" "$ANNOTATIONS" "$COROUTINES" "$STDLIB7" "$STDLIB8"; do test -f "$jar"; done
rm -rf "$ROOT/build/classes" "$ROOT/build/dex-out" "$ROOT/build/program.jar"
mkdir -p "$ROOT/build/classes" "$ROOT/build/dex-out"
COMPILER_CP="$COMPILER:$STDLIB:$SCRIPT:$REFLECT:$TROVE:$ANNOTATIONS:$COROUTINES"
"${JAVA_HOME:?Set JAVA_HOME}/bin/java" -Xmx512m -cp "$COMPILER_CP" org.jetbrains.kotlin.cli.jvm.K2JVMCompiler \
  -no-stdlib -no-reflect -jvm-target 1.8 \
  -classpath "$STDLIB:$SDK/platforms/android-36.1/android.jar" \
  -d "$ROOT/build/classes" "$ROOT/ProbeInstrumentation.kt"
(cd "$ROOT/build/classes" && zip -qr "$ROOT/build/program.jar" org)
"$SDK/build-tools/36.0.0/d8" --min-api 23 \
  --lib "$SDK/platforms/android-36.1/android.jar" \
  --output "$ROOT/build/dex-out" "$ROOT/build/program.jar" "$STDLIB" "$STDLIB7" "$STDLIB8"
sha256sum "$ROOT/build/program.jar" "$ROOT/build/dex-out/classes.dex"
