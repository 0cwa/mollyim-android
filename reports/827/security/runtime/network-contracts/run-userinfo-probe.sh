#!/usr/bin/env bash
set -euo pipefail
src=/workspace/work/p2-review-followup/UserInfoProbe.java
ok=/workspace/gradle-home/caches/modules-2/files-2.1/com.squareup.okhttp3/okhttp-jvm/5.3.2/f31e8de27feebe1e56d6c9d354a0986b65be0e1d/okhttp-jvm-5.3.2.jar
okio=$(find /workspace/gradle-home/caches/modules-2/files-2.1/com.squareup.okio/okio-jvm/3.17.0 -name '*.jar' -print -quit)
kotlin=$(find /workspace/gradle-home/caches/modules-2/files-2.1/org.jetbrains.kotlin/kotlin-stdlib/2.2.20 -name '*.jar' -print -quit)
cp="$ok:$okio:$kotlin"
/workspace/jdk21/bin/javac -proc:none -cp "$cp" -d /tmp/p2follow/classes "$src"
/workspace/jdk21/bin/java -cp "/tmp/p2follow/classes:$cp" UserInfoProbe
