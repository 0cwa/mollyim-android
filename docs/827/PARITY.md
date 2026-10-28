# Scope and parity

The repository contains three separate reconstructions, each bound to its own
pinned source inputs:

| Forest | Intended result | Scope of equality |
| --- | --- | --- |
| [`patches/molly-signal-8.33.2`](../../patches/molly-signal-8.33.2/README.md) | Derived Molly port onto Signal 8.33.2 | Entire pinned port tree and file-entry classification against original Molly/Signal pins |
| [`patches/molly`](../../patches/molly/README.md) | Complete Molly 8.19.2-4 source snapshot | Entire target Git tree, with no exclusions |
| [`patches/827`](../../patches/827/README.md) | Adapted launcher artwork and UnifiedPush/MollySocket pilot | Declared files/fragments and reviewed adaptation hashes |

The complete forest does not replace the pilot or its additional regression test
and toolchain adaptations. [PATCH-FOREST.md](PATCH-FOREST.md) describes the common
patch format; [RUNBOOK.md](RUNBOOK.md) gives the pilot's validation commands.

## Complete pinned source reconstruction

`patches/molly` reconstructs target commit
`0e202dda90785771ff8c87526eaaf30c655f54f3`, whose complete tree is
`3cd0bb01cf840e4b702187085432020d163d80ce`, from Signal 8.19.2 commit
`c47a74ba0961903eeaeda6d22347a990056c3e83`. Molly's upstream merge
`3e0860a84b4e13c33c11adbaaabbe4cab8f10c63` records that Signal commit as its
second parent and belongs to the target's ancestry.

The full delta contains 3,178 paths, counting both sides of renames. Sixteen
disjoint review groups include the application features, shared integration,
resources, imported code, removed modules, tests, build/release configuration and
documentation. These groups are not independently buildable feature selections.

```sh
python3 tools/827/verify_complete.py --repo . --patches patches/molly
```

The verifier checks pins, merge ancestry and snapshot source trailers; derives
ownership from the applied commits; rejects overlapping or missing changed paths;
and compares two legal full replays with the target's entire Git tree. No
metadata or source paths are projected out. Exact equality covers additions,
deletions, binary content, modes and symlinks. The target's inherited whitespace
is preserved and reported rather than normalized.

The materialized index and working files must also be clean, with no untracked
files, including ignored files. This catches leftover or altered files even
when the reconstructed commit has the expected tree.

This proves reconstruction of the pinned tracked source contents. It does not
prove Android compilation, APK reproducibility, current-release parity or
runtime/security acceptance. LFS pointer equality does not verify downloaded LFS
payloads. The [complete forest guide](../../patches/molly/README.md) documents the
source pins, groups and verification prerequisites.

## Derived Signal 8.33.2 port

`patches/molly-signal-8.33.2` starts from Signal release `v8.33.2`, commit
`6e9dddc01f1b26e608ac683807c51e139c141ed2`. Its `origin-base` and `origin-target`
pins record the original Signal 8.19.2 / Molly 8.19.2-4 comparison above. Its
`target` records the reviewed derived source commit, with the Signal 8.33.2
merge recorded in `upstream-merge`.

The complete verifier proves that this separate forest reconstructs that derived
target exactly and labels every exported file change correctly. A `carryover`
mailbox requires identical old/new upstream entries and identical original/new
Molly entries. An `adapted` mailbox contains the remaining changed paths. A path
already equal to new Signal needs no patch. The original complete forest remains
unchanged so its official Molly source proof can be repeated independently.

The derived target is a development port, not an official Molly release. Exact
reconstruction and passing build tests do not establish equivalent security or
device behavior. Current Android build results belong in
[issue #4](https://github.com/0cwa/mollyim-android/issues/4); device acceptance
belongs in [issue #5](https://github.com/0cwa/mollyim-android/issues/5).

## Pilot pins and application projection

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

## What each pilot assertion means

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

## Pilot resource comparison

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

The pilot validators consume the parity assertions, [`feature-inventory.tsv`](feature-inventory.tsv),
and the inventory ledgers/fixtures under `reports/827/inventory`. These are test
inputs. Replay reports and CI logs describe individual executions and belong in
CI artifacts and linked review discussions. A pair of matching replay trees
demonstrates repeatable patch application for those inputs; it does not establish
APK reproducibility or acceptance on a device.

## Boundaries

The rest of the Signal-to-Molly difference is represented by the separate
complete forest and remains outside the pilot's assertions. In the pilot, shared
files are covered only by their declared checks, and the application still
includes its Signal-derived Google/Firebase dependencies. The historical pilot
inventory is not a complete feature classification of the Molly target.

Build failures and current verification are tracked in [issue #4](https://github.com/0cwa/mollyim-android/issues/4).
Live delivery, linking, device behavior, clipboard presentation, and cryptographic
lock semantics require separate acceptance in [issue #5](https://github.com/0cwa/mollyim-android/issues/5).
[Issue #3](https://github.com/0cwa/mollyim-android/issues/3) tracks the comparison
oracle and remaining reconstruction validation. Source reconstruction alone does not establish
current-release parity, Google-free APK packaging, complete security signoff or
production readiness.
