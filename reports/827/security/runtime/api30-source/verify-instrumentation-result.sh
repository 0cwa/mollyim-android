#!/usr/bin/env bash
set -euo pipefail
if [[ $# -ne 2 ]]; then
  echo "usage: $0 <phase> <logfile>" >&2
  exit 2
fi
phase=$1
logfile=$2
if ! rg -F -x "INSTRUMENTATION_RESULT: probe_phase=$phase" "$logfile" >/dev/null; then
  echo "$phase instrumentation did not report the expected result phase" >&2
  exit 1
fi
if ! rg -F -x 'INSTRUMENTATION_RESULT: probe_result=PASS' "$logfile" >/dev/null; then
  echo "$phase instrumentation did not report probe_result=PASS" >&2
  exit 1
fi
if rg -F 'INSTRUMENTATION_RESULT: probe_result=FAIL' "$logfile" >/dev/null; then
  echo "$phase instrumentation reported probe_result=FAIL" >&2
  exit 1
fi
