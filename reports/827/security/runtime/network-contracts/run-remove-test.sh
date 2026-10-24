#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
root=/workspace/work/p2-integration/candidate15-replay-1
cp=/tmp/p2follow/classes
cp="$cp:$root/app/build/intermediates/built_in_kotlinc/playProdDebug/compilePlayProdDebugKotlin/classes"
cp="$cp:$root/app/build/intermediates/javac/playProdDebug/compilePlayProdDebugJavaWithJavac/classes"
while IFS= read -r d; do cp="$cp:$d"; done < <(find "$root" -path '*/build/classes/*' -type d)
while IFS= read -r j; do cp="$cp:$j"; done < <(find /workspace/gradle-home/caches/modules-2/files-2.1 -name '*.jar')
for j in /workspace/android-sdk/platforms/android-35/android.jar /workspace/android-sdk/platforms/android-36/android.jar; do [[ ! -f "$j" ]] || cp="$cp:$j"; done
/workspace/jdk21/bin/javac -proc:none -cp "$cp" -d /tmp/p2follow/classes fake/org/thoughtcrime/securesms/linkdevice/LinkDeviceRepository.java RemoveDeviceFlowTest.java
/workspace/jdk21/bin/java -cp "/tmp/p2follow/classes:$cp" RemoveDeviceFlowTest
