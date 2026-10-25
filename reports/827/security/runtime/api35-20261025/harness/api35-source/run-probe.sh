#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: ADB_SERIAL=<disposable API35 emulator> EXPECTED_AVD_NAME=molly827-api35 TARGET_BENCHMARK_APK=<apk> TARGET_APK_SHA256=<sha> $0 <serial>" >&2
  exit 2
fi
SERIAL=$1
[[ "${ADB_SERIAL:-}" == "$SERIAL" ]] || { echo "ADB_SERIAL must confirm this emulator serial" >&2; exit 2; }
[[ "$SERIAL" == emulator-* ]] || { echo "Refusing non-emulator target" >&2; exit 2; }
: "${EXPECTED_AVD_NAME:?Set the disposable AVD name}"
: "${TARGET_BENCHMARK_APK:?Set the current-source benchmark APK path}"
: "${TARGET_APK_SHA256:?Set the recorded current-source benchmark APK SHA-256}"
: "${FAKE_DISTRIBUTOR_APK:?Set the freshly built local fake-distributor APK}"
: "${PROBE_APK:?Set the freshly built local instrumentation APK}"
SDK=${ANDROID_SDK_ROOT:?Set ANDROID_SDK_ROOT to the isolated SDK}
ADB="$SDK/platform-tools/adb"
ROOT=$(cd "$(dirname "$0")" && pwd)
TARGET=org.thoughtcrime.securesms.benchmark
RUNNER=org.thoughtcrime.securesms.probe/org.thoughtcrime.securesms.probe.ProbeInstrumentation
FAKE=org.example.upfake
ACTUAL_TARGET_SHA=$(sha256sum "$TARGET_BENCHMARK_APK" | cut -d ' ' -f 1)
[[ "$ACTUAL_TARGET_SHA" == "$TARGET_APK_SHA256" ]] || { echo "benchmark APK SHA-256 mismatch" >&2; exit 3; }
[[ "$(sha256sum "$FAKE_DISTRIBUTOR_APK" | cut -d ' ' -f 1)" == "$(cut -d ' ' -f 1 "$FAKE_DISTRIBUTOR_APK.sha256")" ]] || { echo "fake distributor APK SHA-256 mismatch" >&2; exit 4; }
[[ "$(sha256sum "$PROBE_APK" | cut -d ' ' -f 1)" == "$(cut -d ' ' -f 1 "$(dirname "$PROBE_APK")/build/apk.sha256")" ]] || { echo "probe APK SHA-256 mismatch" >&2; exit 5; }
OUT="$ROOT/results/api35-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$OUT"
printf 'result_dir=%s\nserial=%s\navd=%s\napi=35\ntarget_apk_sha256=%s\n' "$OUT" "$SERIAL" "$EXPECTED_AVD_NAME" "$ACTUAL_TARGET_SHA" > "$OUT/run-info.txt"

"$ADB" -s "$SERIAL" get-state >/dev/null
[[ "$("$ADB" -s "$SERIAL" shell getprop ro.kernel.qemu | tr -d '\r')" == 1 ]] || { echo "Target is not an Android emulator" >&2; exit 6; }
AVD_NAME=$("$ADB" -s "$SERIAL" emu avd name 2>/dev/null | sed -n '1p' | tr -d '\r')
[[ "$AVD_NAME" == "$EXPECTED_AVD_NAME" ]] || { echo "AVD name mismatch: $AVD_NAME" >&2; exit 7; }

# This must be the disposable AVD started with -wipe-data. Clear target package data before
# seeding a local synthetic account; no existing account state is reused.
"$ADB" -s "$SERIAL" install -r "$TARGET_BENCHMARK_APK" > "$OUT/target-install.txt"
"$ADB" -s "$SERIAL" shell pm clear "$TARGET" > "$OUT/target-clear.txt"
"$ADB" -s "$SERIAL" shell pm grant "$TARGET" android.permission.POST_NOTIFICATIONS > "$OUT/notification-permission.txt"

# Match the historical local-only setup and add guest firewall egress denial for both stacks.
"$ADB" -s "$SERIAL" shell settings put global airplane_mode_on 1
"$ADB" -s "$SERIAL" shell am broadcast -a android.intent.action.AIRPLANE_MODE --ez state true > "$OUT/airplane-mode.txt" 2>&1 || true
"$ADB" -s "$SERIAL" shell svc wifi disable > "$OUT/wifi.txt" 2>&1 || true
"$ADB" -s "$SERIAL" shell svc data disable > "$OUT/mobile-data.txt" 2>&1 || true
"$ADB" -s "$SERIAL" root > "$OUT/adb-root.txt"
"$ADB" -s "$SERIAL" wait-for-device
"$ADB" -s "$SERIAL" shell id > "$OUT/emulator-shell-id.txt"
rg -q 'uid=0' "$OUT/emulator-shell-id.txt"
"$ADB" -s "$SERIAL" shell iptables -F OUTPUT
"$ADB" -s "$SERIAL" shell iptables -P OUTPUT DROP
"$ADB" -s "$SERIAL" shell iptables -A OUTPUT -o lo -j ACCEPT
"$ADB" -s "$SERIAL" shell ip6tables -F OUTPUT
"$ADB" -s "$SERIAL" shell ip6tables -P OUTPUT DROP
"$ADB" -s "$SERIAL" shell ip6tables -A OUTPUT -o lo -j ACCEPT
"$ADB" -s "$SERIAL" shell iptables -S OUTPUT > "$OUT/ipv4-output-rules.txt"
"$ADB" -s "$SERIAL" shell ip6tables -S OUTPUT > "$OUT/ipv6-output-rules.txt"
grep -Fxq -- '-P OUTPUT DROP' "$OUT/ipv4-output-rules.txt"
grep -Fxq -- '-A OUTPUT -o lo -j ACCEPT' "$OUT/ipv4-output-rules.txt"
grep -Fxq -- '-P OUTPUT DROP' "$OUT/ipv6-output-rules.txt"
grep -Fxq -- '-A OUTPUT -o lo -j ACCEPT' "$OUT/ipv6-output-rules.txt"
[[ $(wc -l < "$OUT/ipv4-output-rules.txt") -eq 2 ]]
[[ $(wc -l < "$OUT/ipv6-output-rules.txt") -eq 2 ]]

cleanup_fake() { "$ADB" -s "$SERIAL" uninstall "$FAKE" >/dev/null 2>&1 || true; }
trap cleanup_fake EXIT
"$ADB" -s "$SERIAL" install -r "$FAKE_DISTRIBUTOR_APK" > "$OUT/fake-install.txt"
"$ADB" -s "$SERIAL" install -r "$PROBE_APK" > "$OUT/probe-install.txt"
"$ADB" -s "$SERIAL" shell am start -W -n "$FAKE/.BootstrapActivity" > "$OUT/fake-bootstrap.txt"

run_phase() {
  local phase=$1 limit=$2 log="$OUT/$1.txt" rc
  set +e
  timeout -k 10s "${limit}s" "$ADB" -s "$SERIAL" shell am instrument -w -e phase "$phase" "$RUNNER" > "$log" 2>&1
  rc=$?
  set -e
  cat "$log"
  [[ $rc -eq 0 ]] || { echo "$phase instrumentation failed or timed out (exit $rc)" >&2; return "$rc"; }
  "$ROOT/verify-instrumentation-result.sh" "$phase" "$log"
}

run_phase seed 300
"$ADB" -s "$SERIAL" shell am force-stop "$TARGET"
run_phase restart 180
cleanup_fake
trap - EXIT
printf 'PASS: synthetic local-only API35 run; no Signal account or MollySocket endpoint used\n'
