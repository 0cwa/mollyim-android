#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")" && pwd)
SDK=${ANDROID_SDK_ROOT:?Set ANDROID_SDK_ROOT to the isolated SDK}
KEYSTORE=${1:-${P2_TEST_KEYSTORE:-/home/x/.android/debug.keystore}}
PLATFORM="$SDK/platforms/android-36.1/android.jar"
TOOLS="$SDK/build-tools/36.0.0"
test -f "$PLATFORM"
test -f "$KEYSTORE"
rm -rf "$ROOT/build" "$ROOT/fake-distributor.apk"
mkdir -p "$ROOT/build/classes" "$ROOT/build/dex"
"${JAVA_HOME:?Set JAVA_HOME}/bin/javac" -source 8 -target 8 -bootclasspath "$PLATFORM" \
  -d "$ROOT/build/classes" "$ROOT/BootstrapActivity.java" "$ROOT/DistributorReceiver.java"
"${JAVA_HOME}/bin/jar" cf "$ROOT/build/classes.jar" -C "$ROOT/build/classes" .
"$TOOLS/d8" --min-api 23 --lib "$PLATFORM" --output "$ROOT/build/dex" "$ROOT/build/classes.jar"
"$TOOLS/aapt2" link -I "$PLATFORM" --manifest "$ROOT/AndroidManifest.xml" \
  --min-sdk-version 23 --target-sdk-version 30 -o "$ROOT/build/unsigned.apk"
(cd "$ROOT/build" && zip -q -j unsigned.apk dex/classes.dex)
"$TOOLS/zipalign" -f -p 4 "$ROOT/build/unsigned.apk" "$ROOT/build/aligned.apk"
"$TOOLS/apksigner" sign --ks "$KEYSTORE" --ks-key-alias androiddebugkey \
  --ks-pass pass:android --key-pass pass:android --out "$ROOT/fake-distributor.apk" "$ROOT/build/aligned.apk"
"$TOOLS/apksigner" verify --verbose "$ROOT/fake-distributor.apk"
"$TOOLS/aapt" dump badging "$ROOT/fake-distributor.apk" | sed -n '1p'
sha256sum "$ROOT/fake-distributor.apk" > "$ROOT/fake-distributor.apk.sha256"
cat "$ROOT/fake-distributor.apk.sha256"
