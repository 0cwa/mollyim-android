# Standard patch forest: audit, design, and maintenance

## Audit and migration decision

Audited starting point: `9409c830af377e058155a13cda9da092ed6e260a` on
`dev/molly-827-reproducible-poc`, not the repository's default `main` branch.

The 23 existing patches were already `git format-patch` mailboxes. The problem
was the 72,283-byte JSON document named `series.yaml`: it repeated their names,
order, predecessor links, mailbox commit IDs, source-commit references, checksums,
and a derived provenance classification. Those facts also existed in the
filesystem or mailbox. The same document mixed this patch catalog with valuable
application-specific parity and adaptation assertions. The validator then
validated both the catalog and its duplication of the patches.

This migration removes the patch catalog, not the evidence. All 23 mailbox files
retain their exact original bytes, names, authors, messages, and source references.
The original Signal base, Molly comparison target, expected application commit,
and expected application tree remain pinned. The current inventory digest binds
the derived forest inputs and the separate evidence rather than an obsolete
manifest file. Historical reports and the original attribution ledger remain
historical evidence, not new test results.

Implementation sequence:

1. Introduce a small forest reader around standard mailbox files and line-based
   series. Reject ambiguous ordering, unsafe paths, orphan patches, and cycles.
2. Move parity assertions to `docs/827/parity-evidence.json`; derive all patch
   information from the forest in memory. Update every live consumer, including
   resource checks, inventory refresh, validation, and double replay.
3. Preserve the original release-tree, provenance, ownership, resource, and Android
   gates. Add independent dependency-closure checks and two legal full replay orders.
4. Exercise the new runner with real Git fixture repositories and the existing
   pinned-source replay tests before review. Do not change application source or
   promote this bounded PoC to a production release system.

## The authored format

```text
patches/827/
  base                              # one full upstream commit ID
  branding/
    series                          # one local mailbox filename per line
    0001-branding-default-launcher.patch
  unifiedpush/
    series                          # the existing 20-patch linear series
    0001-...patch
    ...
    0020-...patch
  build-validation/
    depends                         # unifiedpush (inherited release prerequisite)
    series
    0001-...patch
    0002-...patch
```

`series` is the conventional explicit ordered list of patches, not executable
shell and not a list of options. Entries are local numbered `*.patch` filenames;
blank lines and `#` comments are allowed. Filename numbers aid review; **the list
order is authoritative**. No patch may be unlisted, listed twice, or referenced
outside its feature directory. Each file contains exactly one format-patch
message, not a cover letter or concatenated mailbox. Binary Git patches work.

A feature's directory path is its name. Root siblings have no implied dependency.
A nested feature with its own `series` depends on the *whole series of its immediate
parent feature*. Every ancestor must therefore also have a `series`; there are no
ambiguous category-only parent folders. Selecting a child includes its ancestors;
selecting a parent does not enable all its children. For example:

```text
transport/series                    # shared transport groundwork
transport/socket/series             # depends on transport, not push
transport/push/series               # depends on transport, not socket
privacy/series                      # separate root
transport/push/privacy/series       # implicit parent: transport/push
transport/push/privacy/depends      # one extra line: privacy
```

Nesting and `depends` are the only project conventions beyond Git mailbox/series
files. Git itself does not define feature dependency graphs. A folder tree alone
cannot represent a feature needing two unrelated prerequisites, so we do not
pretend it can. `depends` contains forest-relative feature names, one per line.
There are no per-patch graph IDs, version constraints, priorities, or alternative
providers. Parent edges are implicit and must not be repeated. Missing edges,
self-dependencies, duplicate entries, and cycles are rejected.

The existing `build-validation -> unifiedpush` release prerequisite is retained
conservatively, rather than silently changing the old release policy. These two
validation patches concern URI test variant IDs and the Gradle wrapper checksum;
the edge is **not a new claim that they inherently need UnifiedPush code**. Review
and remove it separately once the desired standalone validation policy is agreed.
The current patch paths are preserved to avoid unnecessary attribution churn.

## Cross-feature changes

Extract common groundwork into a parent or shared prerequisite feature when two
features genuinely need it. Keep unrelated changes as siblings. When combining
otherwise separate features requires glue, put that glue in a small integration
feature depending on both; do not insert it into one root and rely on alphabetical
application order. Put the dependency rationale in its README or a `depends`
comment. If a feature needs only a prefix of another series, split that prefix into
its own feature instead of adding per-patch dependency syntax.

A dependency cycle means the proposed feature boundaries cannot be built in the
claimed order. Split the shared prerequisite out or combine the mutually dependent
changes into one series. Do not break the cycle with a priority flag or duplicate
a patch in multiple folders. Textual overlap alone is not a semantic dependency,
and clean application alone does not prove behavioral independence.

The generic runner permits dependent features to touch the same files. The #827
parity harness still enforces the pilot's explicit, disjoint file-ownership claims;
a future integration touching an already-owned file needs an intentional update
to that project's evidence/ownership policy, not a hidden relaxation during this
format migration.

## Daily commands

Git and Python 3.10+ are sufficient for the patch tools. The Android SDK is only
needed for application checks. Run from the repository root:

```sh
python3 tools/827/forest.py check
python3 tools/827/forest.py series
python3 tools/827/forest.py series --feature unifiedpush
python3 tools/827/forest.py apply --repo . --worktree /tmp/molly-feature \
  --feature unifiedpush
python3 tools/827/forest.py verify --repo .
```

Every `apply` creates a *new detached worktree* at `base`. Existing paths, symlinks,
parent traversal, and destinations inside the source checkout are refused. The
source branch, index, and uncommitted files are not reset, cleaned, or committed.
Hooks, automatic signing, and rerere reuse are disabled for replay. Mailbox author
identity is preserved; the replay committer identity/date are set explicitly.
Release application uses `git am --no-3way` even if local Git configuration enables
three-way fallback. A failing standalone application leaves its worktree and am
state for inspection; no automatic conflict resolution or history rewriting occurs.

```sh
git -C /tmp/molly-feature am --show-current-patch
# Inspect the failure; abort only this disposable replay worktree when finished.
git -C /tmp/molly-feature am --abort
git worktree remove /tmp/molly-feature
```

The flattened `series` output is an ordinary ordered patch list relative to
`patches/827`. No generated copy is checked in. To replay without the Python
application wrapper after reviewing the flattened list:

```sh
patch_root="$(pwd)/patches/827"
python3 tools/827/forest.py series > /tmp/molly.series
git worktree add --detach /tmp/molly-manual "$(cat "$patch_root/base")"
while IFS= read -r patch; do
  git -C /tmp/molly-manual -c core.hooksPath=/dev/null -c rerere.enabled=false \
    am --no-3way "$patch_root/$patch" || exit 1
done < /tmp/molly.series
```

For an audited release candidate, retain the stronger project checks:

```sh
python3 -m unittest discover -s tools/827 -p 'test_*.py'
python3 tools/827/validate.py --repo .
python3 tools/827/validate_inventory.py --repo .
python3 tools/827/replay_twice.py --repo . \
  --worktree-prefix /tmp/molly827 --report reports/827/replay/replay-twice.json
```

The full test suite and project validators require the pinned Git history. Fast
synthetic runner tests alone use `python3 tools/827/test_forest.py`. `forest verify`
replays each feature with only its declared prerequisite closure, then replays all
features in ascending and descending ready-node order and compares the trees.
Its own temporary worktrees are removed after each check, including failures.
This detects some hidden dependencies and order interactions; it is **not** an
exhaustive permutation test, an isolated-feature compilation test, or proof of
semantic independence. Keep the Android build/test/lint and runtime checks.

## Authoring and updating patches

Develop a feature as a linear topic branch based on the upstream base plus its
prerequisites. Export only that feature's commits, not its prerequisites. The
maintainer chooses and reviews those exact boundary refs:

```sh
# FEATURE_BASE and FEATURE_TIP are reviewed commit refs, not arbitrary merge tips.
test "$(git rev-list --count --merges "$FEATURE_BASE..$FEATURE_TIP")" = 0
git format-patch --binary --full-index --output-directory /tmp/feature-v2 \
  "$FEATURE_BASE..$FEATURE_TIP"
git range-diff "$OLD_FEATURE_BASE..$OLD_FEATURE_TIP" "$FEATURE_BASE..$FEATURE_TIP"
```

Review the new mailboxes and the corresponding `series` edit together. Replace
obsolete patches rather than leaving unlisted files behind. Preserve meaningful
commit messages, authorship, and `Source-Commit:`/`Source-Commits:` provenance for
ported upstream changes; those trailers are checked against the pinned Molly
history by the project validator. The mailbox `From` ID is an export identity,
not proof of upstream authorship and not a requirement to retain that commit object.

When upgrading upstream, rebase/resolve in maintenance branches, re-export reviewed
linear series, and update `base`. The generic forest supports another base; the
#827 audit intentionally also pins its original base and target in code. Updating
that audited scope is a separate review of constants, parity evidence, expected
application commit/tree, and tests. Do not automatically bless new expected hashes
from a failed replay. After reviewed evidence changes, refresh the live ledger
with `python3 tools/827/refresh_inventory.py --repo .` and validate it again.

Patch hashes are computed for reports and the live inventory's `inputs_sha256`,
not copied into a hand-maintained catalog. Git commits bind the complete authored
inputs; releases should identify the exact reviewed repository commit (and, under
the project's signing policy, a verified tag). A hash alone does not authenticate
who approved a change. Parity assertions remain JSON because they are structured
test evidence, but `forest.py` never reads them.

## git-carrier boundary

Git-carrier handles a **stopped merge**, not a `git am` session. It is optional
maintenance tooling, not a release dependency. Keep carrier branches separate:
`git park` records the stopped-merge state, `git unpark` exposes paths for resolution,
and `git land` prepares the resolved merge for the maintainer's own commit. Never
merge the carrier branch directly. Do not run `git park` on an am failure or export
`.hangar` as release patches. Both replay paths reject carrier state in the result.

After landing a maintenance merge, reconstruct/review the affected linear feature
series and compare old and new versions with `git range-diff`. `format-patch` omits
merge commits, so blindly exporting a carrier/landed merge range can lose conflict
resolution work. Review the actual feature delta and replayed tree before export
is accepted. No automated carrier import/export or compatibility claim is made.

References: [git format-patch](https://git-scm.com/docs/git-format-patch),
[git am](https://git-scm.com/docs/git-am),
[git range-diff](https://git-scm.com/docs/git-range-diff), and the
[git-carrier workflow](https://github.com/git-carrier/git-carrier#the-workflow).
