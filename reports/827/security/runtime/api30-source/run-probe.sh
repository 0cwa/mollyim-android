#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: ADB_SERIAL=<disposable serial> $0 <serial>" >&2
  exit 2
fi
SERIAL=$1
if [[ "${ADB_SERIAL:-}" != "$SERIAL" ]]; then
  echo "Set ADB_SERIAL to the same disposable emulator serial to confirm the target." >&2
  exit 2
fi
ROOT=$(cd "$(dirname "$0")" && pwd)
ADB=${ANDROID_SDK_ROOT:-/workspace/android-sdk}/platform-tools/adb
TARGET=org.thoughtcrime.securesms.benchmark
RUNNER=org.thoughtcrime.securesms.probe/org.thoughtcrime.securesms.probe.ProbeInstrumentation
FAKE=org.example.upfake
FAKE_APK=${FAKE_DISTRIBUTOR_APK:-/workspace/work/p2-device-followup/fake-distributor/fake-distributor.apk}
EXPECTED_FAKE_SHA256=${FAKE_DISTRIBUTOR_SHA256:-56edc9642a3622b3c71b7941c8494853d82095d9671c0452326930474d3abd1b}
OUT="$ROOT/results/run-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$OUT"
printf 'result_dir=%s\n' "$OUT" > "$OUT/run-info.txt"

"$ADB" -s "$SERIAL" get-state >/dev/null
cleanup_fake() {
  "$ADB" -s "$SERIAL" uninstall "$FAKE" >/dev/null 2>&1 || true
}
trap cleanup_fake EXIT
if ! "$ADB" -s "$SERIAL" shell pm path "$TARGET" >/dev/null 2>&1; then
  echo "benchmark APK is not installed on $SERIAL" >&2
  exit 3
fi

# Keep Android radios off while the local-only callbacks run.
"$ADB" -s "$SERIAL" shell settings put global airplane_mode_on 1
"$ADB" -s "$SERIAL" shell am broadcast -a android.intent.action.AIRPLANE_MODE --ez state true >/dev/null
"$ADB" -s "$SERIAL" shell svc wifi disable >/dev/null 2>&1 || true
"$ADB" -s "$SERIAL" shell svc data disable >/dev/null 2>&1 || true
test -f "$FAKE_APK"
ACTUAL_FAKE_SHA256=$(sha256sum "$FAKE_APK" | cut -d ' ' -f 1)
if [[ "$ACTUAL_FAKE_SHA256" != "$EXPECTED_FAKE_SHA256" ]]; then
  echo "fake distributor SHA-256 mismatch: $ACTUAL_FAKE_SHA256" >&2
  exit 5
fi
"$ADB" -s "$SERIAL" install -r "$FAKE_APK" > "$OUT/fake-install.txt"
"$ADB" -s "$SERIAL" install -r "$ROOT/p2-probe.apk" > "$OUT/install.txt"
if ! "$ADB" -s "$SERIAL" shell pm path "$FAKE" >/dev/null 2>&1; then
  echo "local fake distributor APK did not install" >&2
  exit 4
fi
# Launch once to clear Android's freshly-installed/stopped package state. This
# is the same first-launch step a real distributor app receives before use.
"$ADB" -s "$SERIAL" shell am start -W -n "$FAKE/.BootstrapActivity" > "$OUT/fake-bootstrap.txt"

run_phase() {
  local phase=$1
  local limit_seconds=$2
  local logfile="$OUT/$phase.txt"
  set +e
  timeout -k 10s "${limit_seconds}s" "$ADB" -s "$SERIAL" shell am instrument -w -e phase "$phase" "$RUNNER" > "$logfile" 2>&1
  local rc=$?
  set -e
  cat "$logfile"
  if [[ $rc -ne 0 ]]; then
    echo "$phase instrumentation command failed or timed out (exit $rc)" >&2
    return "$rc"
  fi
  if ! "$ROOT/verify-instrumentation-result.sh" "$phase" "$logfile"; then
    return 1
  fi
}

if ! run_phase seed 300; then
  echo "seed phase failed; attempting fixture cleanup" >&2
  run_phase cleanup 120 || true
  exit 1
fi
"$ADB" -s "$SERIAL" shell am force-stop "$TARGET"
if ! run_phase restart 180; then
  echo "restart phase failed; attempting fixture cleanup" >&2
  run_phase cleanup 120 || true
  exit 1
fi
