#!/usr/bin/env bash
# Prepared command for the next authorized full build. This script does not
# omit tasks; it runs the ordinary `build` lifecycle with retention callbacks.
# Do not launch until the coordinator approves the capacity/runtime window.
set -euo pipefail
export JAVA_HOME=/workspace/jdk21
export PATH="$JAVA_HOME/bin:/workspace/android-sdk/platform-tools:/workspace/android-sdk/cmdline-tools/latest/bin:$PATH"
export ANDROID_HOME=/workspace/android-sdk
export ANDROID_SDK_ROOT=/workspace/android-sdk
export GRADLE_USER_HOME=/workspace/gradle-home
export JAVA_TOOL_OPTIONS="-Djavax.net.ssl.trustStore=/etc/ssl/certs/java/cacerts -Djavax.net.ssl.trustStoreType=JKS"
proxy_endpoint="${HTTPS_PROXY:-${https_proxy:-}}"
if [[ -n "$proxy_endpoint" ]]; then
  read -r proxy_host proxy_port < <(python3 - "$proxy_endpoint" <<'PY'
import sys,urllib.parse
u=urllib.parse.urlsplit(sys.argv[1])
if not u.hostname or not u.port: raise SystemExit('HTTPS proxy host/port unavailable')
print(u.hostname, u.port)
PY
)
  export JAVA_TOOL_OPTIONS="$JAVA_TOOL_OPTIONS -Dhttp.proxyHost=$proxy_host -Dhttp.proxyPort=$proxy_port -Dhttps.proxyHost=$proxy_host -Dhttps.proxyPort=$proxy_port -Dmaven.repo.local=/workspace/work/p2-robolectric-cache"
  export GRADLE_OPTS="-Xmx2g -XX:ActiveProcessorCount=4 -Dhttp.proxyHost=$proxy_host -Dhttp.proxyPort=$proxy_port -Dhttps.proxyHost=$proxy_host -Dhttps.proxyPort=$proxy_port -Dorg.gradle.java.installations.paths=/workspace/jdk21"
else
  export GRADLE_OPTS="-Xmx2g -XX:ActiveProcessorCount=4 -Dorg.gradle.java.installations.paths=/workspace/jdk21"
fi
cd /workspace/work/p2-integration/candidate15-replay-1
exec ./gradlew --no-daemon --max-workers=1 \
  --init-script /workspace/work/p2-baseline/test-worker-heap.init.gradle \
  --init-script /workspace/work/p2-baseline/attempt20-retry2-capacity-ordering.init.gradle \
  "-Dorg.gradle.jvmargs=-Xmx8g -Xms256m -XX:MaxMetaspaceSize=1g -Dcom.android.tools.r8.threadCount=2 -XX:+UnlockExperimentalVMOptions -XX:hashCode=3 -XX:ActiveProcessorCount=4" \
  --continue build
