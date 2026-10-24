#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")" && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
cat > "$TMP/pass.txt" <<'OUT'
INSTRUMENTATION_RESULT: probe_phase=seed
INSTRUMENTATION_RESULT: probe_result=PASS
INSTRUMENTATION_RESULT: probe_checks=PASS one; PASS two
INSTRUMENTATION_CODE: -1
OUT
cat > "$TMP/fail.txt" <<'OUT'
INSTRUMENTATION_RESULT: probe_phase=seed
INSTRUMENTATION_RESULT: probe_result=FAIL
INSTRUMENTATION_RESULT: probe_failures=check failed
INSTRUMENTATION_CODE: 0
OUT
cat > "$TMP/wrong-phase.txt" <<'OUT'
INSTRUMENTATION_RESULT: probe_phase=restart
INSTRUMENTATION_RESULT: probe_result=PASS
INSTRUMENTATION_CODE: -1
OUT
"$ROOT/verify-instrumentation-result.sh" seed "$TMP/pass.txt"
if "$ROOT/verify-instrumentation-result.sh" seed "$TMP/fail.txt" >/dev/null 2>&1; then
  echo 'FAIL result must be rejected' >&2
  exit 1
fi
if "$ROOT/verify-instrumentation-result.sh" seed "$TMP/wrong-phase.txt" >/dev/null 2>&1; then
  echo 'wrong phase must be rejected' >&2
  exit 1
fi
printf 'parser accepted PASS and rejected FAIL/wrong phase\n'
