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
- **PENDING — broad Android checks and CI.** The full staging suite has not completed. The prior full build ended in disk exhaustion with URI fixture failures; the URI regression now passes in focused tests, but a full current build has not passed. GitHub Actions run `40105996791` failed at patch application before Android checks. The corrected workflow has not yet produced a result.

## Security and parity limits

The replay tool rejects destination traversal, symlink components, destinations inside the primary checkout, and patch paths outside the manifest root. It checks patch hashes, owned paths, conflicts, and declared parity. A concurrent local process could replace a destination parent between validation and `git worktree add`; the stated threat model assumes a trusted local caller.

The adaptation hashes and residual diffs show reproducibility, not semantic equivalence. The result does not establish behavior for all 62 adaptations, full Molly parity, production readiness, live service behavior, or physical-device behavior. The F5 test injects an IOException in place of live MollySocket timing, and the WebSocket reset/start methods are mocked.

## Evidence files

- `manifest-validation-final.json`
- `inventory-validation-final.json`
- `replay-frozen-final.json` and its per-run reports/logs
- `gzip-source-projection-final.json`
- `reports/827/inventory/resource-parity.json`
