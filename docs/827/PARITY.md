# Scope and parity

The #827 proof reconstructs selected launcher artwork and UnifiedPush/MollySocket
integration from a pinned Signal base. It does not reconstruct the full Molly
feature set. [PATCH-FOREST.md](PATCH-FOREST.md) describes the patch format and
[RUNBOOK.md](RUNBOOK.md) gives the validation commands.

## Pinned scope

| Input | Commit or tree |
| --- | --- |
| Signal base | `c47a74ba0961903eeaeda6d22347a990056c3e83` |
| Molly comparison target | `0e202dda90785771ff8c87526eaaf30c655f54f3` |
| Expected application commit | `d99876269eb6556e37bb2d584ba08e8334e8e5db` |
| Expected application tree | `e783cf54487a5b5d78c3241ec977fd8c8cd23f1d` |

The application tree excludes the explicitly allowed patch tooling,
documentation, reports, and workflow metadata. The projection uses a private Git
index and leaves the checkout's index intact. The expected application tree is a
validation target, not a statement that a particular current run passed.

The authored forest selects and orders mailbox patches. The separate
[`parity-evidence.json`](parity-evidence.json) records application assertions;
it cannot override forest topology or patch selection.

## What each assertion means

| Assertion | What the validator checks | Limit |
| --- | --- | --- |
| Full-file parity | The selected path matches the pinned Molly target. | Says nothing about other target files. |
| Integration fragment | Named, anchored content matches the target within a shared file. | Other content in that file can differ. |
| Adaptation | The reconstructed file has the reviewed expected hash and declared rationale. | Reproducibility is not semantic equivalence. |
| Added validation path | A declared test or build input belongs to the patch scope. | A target-absent test is not Molly parity. |
| Ownership | Applied changes belong to declared feature paths, with no unowned change. | Path ownership does not establish the origin of every hunk. |
| Source provenance | Cited source commits exist in the pinned target ancestry. | A patch citing several commits does not attribute each hunk to every cited commit. |

`Source-Commit:` and `Source-Commits:` trailers identify original source refs.
The mailbox `From` SHA identifies a reconstructed export and is a different
kind of evidence. The tools preserve that distinction.

The feature inventory's historical target boundary and the current forest's
owned-path ledger are separate inputs. The current ledger includes test and
toolchain adaptations as well as feature paths. Their presence does not expand
the claimed Molly feature coverage.

## Resource comparison

`check_resource_parity.py` compares named XML elements across the base, target,
and expected application tree. Candidate-changed resource keys must be declared
and present in the pinned target delta. Unrelated baseline resource files are
checked for preservation.

One QR instruction has a quote-balancing adaptation. Its target and candidate
source bytes, element hashes, aapt2 outputs, and compiled runtime text are bound
by the fixture under
[`reports/827/inventory/resource-aapt2`](../../reports/827/inventory/resource-aapt2).
The checker accepts only that specific compiler-proven equivalence. This does
not establish general XML equivalence, resource merging, or rendered UI behavior.

## Evidence inputs and generated results

The validators consume the parity assertions, [`feature-inventory.tsv`](feature-inventory.tsv),
and the inventory ledgers/fixtures under `reports/827/inventory`. These are test
inputs. Replay reports and CI logs describe individual executions and belong in
CI artifacts and linked review discussions. A pair of matching replay trees
demonstrates repeatable patch application for those inputs; it does not establish
APK reproducibility or acceptance on a device.

## Boundaries

The rest of the Signal-to-Molly difference remains outside this pilot, including
unrelated Molly functionality, upstream evolution, broad refactors, binary art,
release infrastructure, and unresolved mixed-origin edits. Shared files are
covered only by their declared assertions. The application still includes its
Signal-derived Google/Firebase dependencies.

Build failures and current verification are tracked in [issue #4](https://github.com/0cwa/mollyim-android/issues/4).
Live delivery, linking, device behavior, clipboard presentation, and cryptographic
lock semantics require separate acceptance in [issue #5](https://github.com/0cwa/mollyim-android/issues/5).
[Issue #3](https://github.com/0cwa/mollyim-android/issues/3) tracks a current matched
comparison oracle. The pinned proof makes no claim of current-release parity,
Google-free packaging, complete security signoff, or production readiness.
