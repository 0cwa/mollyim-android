# Independent replay and safety review

Date: 2026-10-24 UTC  
Feature source commit: `36578d8bb7058f862d5dd379440a12c1fbd7f3af`  
Source projection/replay tree: `26956e0f159c0b60719d4a20667aeef8913fa365`

## Results

- **PASS — manifest and provenance.** `python3 tools/827/validate.py --repo . --manifest patches/827/series.yaml` validates all 22 patch checksums/dependencies, exact Signal/Molly pins, and source-commit references. The 9 distinct Molly source commits resolve and are ancestors of the pinned target. Reconstruction mailbox commits and original Molly source commits are identified separately.
- **PASS — inventory.** `python3 tools/827/validate_inventory.py --repo .` checks all 3,171 base-to-target records and the 83-path manifest ledger: 12 exact files, 12 fragments, 62 adaptations, and one target-absent regression test. The rest is explicitly excluded or unresolved.
- **PASS — resource parity.** `python3 tools/827/check_resource_parity.py --repo .` reports 1,242/1,242 selected localized XML elements matching the Molly target, no candidate values outside the target delta, and all 112 unrelated baseline XML files unchanged.
- **PASS — 18 replay safety fixtures.** `python3 tools/827/test_replay.py` covers traversal, symlink destinations and patch inputs, ownership/dependency/checksum/provenance checks, deterministic gzip, absent Git identity with signing enabled, and malformed-patch diagnostics.
- **PASS — two independent final replays.** `python3 tools/827/replay_twice.py --repo . --manifest patches/827/series.yaml --worktree-prefix /tmp/codex-827-final-22patch --report reports/827/independent/replay-frozen-final.json` produced `26956e0f159c0b60719d4a20667aeef8913fa365` in both runs, matching the projected source tree. Each run reports 83 changed paths, zero unowned paths, 12/12 exact files, 12/12 anchored fragments, 62/62 adaptation hashes, one target-absent test, no whitespace errors, and no unmerged entries.
- **PASS — compressed residuals.** All 70 gzip artifacts per run pass independent decompression, hash, and byte-count checks. Their timestamps are zero and corresponding compressed artifacts are byte-identical across runs. I removed my temporary worktrees; the source HEAD did not change.
- **PASS — focused app tests and formatting.** Direct JUnit XML inspection confirms 9 receiver tests plus 16 URI tests passed with zero failures. The F5 changed-endpoint test verifies the refresh job’s failure path: stale availability becomes `UNKNOWN`, endpoint/device state remains intact, and network fallback restarts. A same-endpoint callback leaves registration and job scheduling unchanged. The formatted app ktlint run passed.
- **PASS — full staging tests and app lint.** On feature source commit `36578d8bb7058f862d5dd379440a12c1fbd7f3af`, the unfiltered staging unit task passed 2,800 tests across 251 XML suites, with zero failures/errors and 78 skipped. I independently checked that every JUnit XML count and SHA-256 matches the machine summary. The full test log hash is `229ad4620f493207925116bdb5937b0fc73e1eed462ab633cbaaacd649955a83`; the separate app ktlint log hash is `a5b47598a6eff3f286494d0e747569a53a94defd5afe0f2bb84f8202c`. Both logs contain `BUILD SUCCESSFUL`.
- **PENDING — current-head CI and full build matrix.** The previous full Android build ended in disk exhaustion with historical URI fixture failures; the corrected URI tests and full staging suite now pass, but a current full project build/variant assembly has not passed. GitHub Actions run `40105996791` failed at patch application before Android checks. Run `40108357095` was still ongoing at the latest status; no final result was available for this review.

## Security and parity limits

The replay tool rejects destination traversal, symlink components, destinations inside the primary checkout, and patch paths outside the manifest root. It checks patch hashes, owned paths, conflicts, and declared parity. A concurrent local process could replace a destination parent between validation and `git worktree add`; the stated threat model assumes a trusted local caller.

The adaptation hashes and residual diffs show reproducibility, not semantic equivalence. The result does not establish behavior for all 62 adaptations, full Molly parity, production readiness, live service behavior, or physical-device behavior. The F5 test injects an IOException in place of live MollySocket timing, and the WebSocket reset/start methods are mocked.

## Evidence files

- `manifest-validation-final.json`
- `inventory-validation-final.json`
- `replay-frozen-final.json` and its per-run reports/logs
- `gzip-source-projection-final.json`
- `full-staging-independent-check.json`
- `reports/827/inventory/resource-parity.json`
