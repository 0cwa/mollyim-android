#!/usr/bin/env bash
set -euo pipefail
candidate=/workspace/work/p2-integration/candidate15-replay-1
app_classes="$candidate/app/build/intermediates/built_in_kotlinc/playProdDebug/compilePlayProdDebugKotlin/classes"
util_classes="$candidate/core/util/build/intermediates/javac/release/compileReleaseJavaWithJavac/classes"
findjar() { find "$1" -path "$2" -name "$3" -print -quit; }
cache=/workspace/gradle-home/caches/modules-2/files-2.1
ann=$(findjar "$cache/com.fasterxml.jackson.core/jackson-annotations/2.12.0" '*' 'jackson-annotations-2.12.0.jar')
core=$(findjar "$cache/com.fasterxml.jackson.core/jackson-core/2.12.0" '*' 'jackson-core-2.12.0.jar')
databind=$(findjar "$cache/com.fasterxml.jackson.core/jackson-databind/2.12.0" '*' 'jackson-databind-2.12.0.jar')
module=$(findjar "$cache/com.fasterxml.jackson.module/jackson-module-kotlin/2.12.0" '*' 'jackson-module-kotlin-2.12.0.jar')
stdlib=$(findjar "$cache/org.jetbrains.kotlin/kotlin-stdlib/2.2.20" '*' 'kotlin-stdlib-2.2.20.jar')
reflect=$(findjar "$cache/org.jetbrains.kotlin/kotlin-reflect/2.2.20" '*' 'kotlin-reflect-2.2.20.jar')
annotations=$(findjar "$cache/org.jetbrains/annotations" '*' 'annotations-*.jar')
cp="$app_classes:$util_classes:$ann:$core:$databind:$module:$stdlib:$reflect:$annotations"
/workspace/jdk21/bin/javac -cp "$cp" -d /workspace/work/p2-review-followup /workspace/work/p2-review-followup/ConnectionRequestWireTest.java
/workspace/jdk21/bin/java -cp "/workspace/work/p2-review-followup:$cp" ConnectionRequestWireTest
