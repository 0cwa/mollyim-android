# Independent replay and safety review

Date: 2026-10-24 UTC  
Candidate: `/workspace/work/p2-integration/candidate15-replay-1`  
Source commit: `0e34c904f72fb899947967e5d2b37f78ca71b70e`  
Source tree: `f00af8f47e8f5bef1cb65559d0a8c7c45d2e5f77`

## Results

- **PASS — exact pins and provenance.** `python3 tools/827/validate.py --repo . --manifest patches/827/series.yaml` validated the pinned Signal base and Molly target, all 20 patch checksums/dependencies, and the Molly source-commit references. The 9 unique Molly source commits resolve locally and are ancestors of the pinned Molly target. The 20 mailbox `From` SHAs identify reconstruction patches; original source commits are separate metadata and are not misrepresented as the patch authors.
- **PASS — two independent final replays.** `python3 tools/827/replay_twice.py --repo . --manifest patches/827/series.yaml --worktree-prefix /tmp/codex-827-final-gzip-independent --report reports/827/independent/replay-gzip-final.json` produced tree `f00af8f47e8f5bef1cb65559d0a8c7c45d2e5f77` in both runs. I independently compared it to `git rev-parse HEAD^{tree}` for source commit `0e34c904...`; the values match exactly.
- **PASS — replay scope checks.** Both reports record 83 changed paths, zero unowned paths, 12/12 exact whole-file matches, 12/12 anchored fragments, 62/62 documented adaptation hashes, and one passing target-absent path check for the new receiver test. There are no whitespace errors or unmerged index entries. These adaptation hashes establish reproducibility; they do not establish semantic parity.
- **PASS — 14 malicious-input and replay fixtures.** `python3 tools/827/test_replay.py` passes. The tests include patch/path traversal, outside manifest symlinks, worktree destinations inside the checkout, symlinked parents resolving inside or outside, existing and dangling leaf symlinks, feature dependency order, checksums, and provenance metadata.
- **PASS — compressed diff integrity and primary checkout safety.** All 70 residual diff artifacts per run decompress to the recorded uncompressed SHA-256 and byte count; compressed SHA-256 and byte counts match too. Gzip headers have `mtime=0`, and each corresponding artifact is byte-identical across the two independent replays. I removed both temporary worktrees; the source branch HEAD remained unchanged. The temporary worktrees are registered in the source repository's Git administration while replay runs, then removed.
- **BLOCKED — inventory cross-check.** My `python3 tools/827/validate_inventory.py --repo .` run reports `FAIL: current-series-owned.tsv path set differs from live patch manifest`. The manifest has 83 paths, while the current ledger still has 80 rows. The archaeology owner is refreshing this ledger; rerun the validator after that update.
- **PENDING — F4 Gradle test.** The current focused receiver test has not yet completed a successful Gradle run. An earlier compile attempt failed on an unresolved MockK `anyConstructed` import, which has since been removed; the build owner has a frozen rerun in progress. Historical API 30 synthetic runtime checks were against the prior tree and do not verify this new locked-callback fix.
- **BLOCKED — full build and CI.** Existing evidence reports the full Android build stopped on disk exhaustion and `SuffixUriUtilTest` failures. The new workflow exists, but no successful CI run is recorded. Do not mark the full build, CI, or complete security signoff as PASS.

## Findings and limits

The replay tool now rejects destination path traversal, any symlink component, destinations within the primary checkout, and patch paths that escape the manifest root. It independently checks patch hashes before application, owned paths after each feature, exact declared target paths/fragments/adaptations, and conflict state. The expanded fixtures exercise these guards. A concurrent process could still replace a destination parent between validation and `git worktree add`; the CLI assumes a trusted local caller and the owner has documented that residual race rather than treating it as a blocker.

The 62 adapted files have per-file expected replay hashes and residual diffs. The manifest and `PARITY.md` correctly state these are adaptations and do not claim target parity. Several adaptation rationales remain broad; the machine check is a reproducibility oracle, not semantic proof. The inventory explicitly marks changes outside the pilot as excluded or unresolved.

The F4 source change is in the committed source tree and the replay reproduces it. The new Robolectric tests assert that locked endpoint rotation, registration failure, and distributor removal clear routing availability while writing only the registration-status key and preserving MollySocket endpoint/device credentials. They mock network restart, so even after the test passes they establish callback state behavior, not an actual device WebSocket reconnection. No live distributor, account, server, or physical-device test is claimed.

## Evidence files

- `manifest-validation-final.json`
- `replay-gzip-final.json` and per-run reports/logs
- `replay-twice-final-run-{1,2}.json` and matching logs
- `inventory-validation-final.json` (current failure pending ledger refresh)
- `gzip-audit-final.json`
- `primary-checkout-snapshot.json` (source HEAD and tree stayed unchanged during replay)
