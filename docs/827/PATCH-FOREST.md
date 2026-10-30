# Patch forest maintenance

Three forests use ordinary `git format-patch` mailboxes, explicit patch order and
declared prerequisites:

| Forest | Reconstruction | Verification |
| --- | --- | --- |
| [`patches/molly-signal-8.33.2`](../../patches/molly-signal-8.33.2/README.md) | Derived Molly port onto Signal 8.33.2 | `verify_complete.py` checks the pinned port tree and carryover/adapted categories |
| [`patches/molly`](../../patches/molly/README.md) | Complete pinned Molly 8.19.2-4 source tree from its Signal 8.19.2 base | `verify_complete.py` checks the entire target tree without exclusions |
| [`patches/827`](../../patches/827/README.md) | Adapted launcher artwork and UnifiedPush/MollySocket pilot | `replay_twice.py` checks the pilot's application assertions |

Each forest starts from its own pinned Signal base. The complete 8.19.2 snapshot
and pilot are preserved when preparing the separate 8.33.2 port. [PARITY.md](PARITY.md)
defines their scopes; [RUNBOOK.md](RUNBOOK.md) covers the pilot's replay and Android
checks. The complete forest has its own [usage guide](../../patches/molly/README.md).

## Format

```text
patches/827/
  base
  branding/
    series
    0001-branding-default-launcher.patch
  unifiedpush/
    series
    0001-...patch
    ...
    0020-...patch
  build-validation/
    depends
    series
    0001-...patch
    0002-...patch
```

`base` contains one full upstream commit ID. Each feature's `series` lists its
local numbered `*.patch` filenames in application order. Blank lines and `#`
comments are allowed; the file is data, not executable shell. The list order is
authoritative even when filenames contain sequence numbers. Each mailbox contains
one format-patch message. Binary patches are supported.

The loader rejects unsafe paths, symlinks, unlisted or duplicated patches,
invalid mailboxes, and malformed dependency graphs. Patches stay in their owning
feature directory.

### Feature dependencies

A feature's directory path is its name. A nested feature depends on the entire
series of its immediate parent; each ancestor therefore needs its own `series`.
Selecting a child includes its prerequisites. Selecting a parent does not enable
its children. Siblings have no implicit dependency.

```text
transport/series
transport/socket/series
transport/push/series
privacy/series
transport/push/privacy/series
transport/push/privacy/depends
```

In this example, `transport/socket` and `transport/push` both require `transport`
but do not require each other. `transport/push/privacy` requires its parent
`transport/push`; a line containing `privacy` in its `depends` file adds the
separate root feature as another prerequisite.

`depends` lists forest-relative feature names, one per line, with the same blank
line and comment syntax as `series`. Unknown features, duplicate or self
dependencies, repeated implicit parent edges, and cycles are errors. Nesting and
`depends` are project conventions; Git itself does not define feature graphs.

The pilot's `build-validation` feature explicitly depends on `unifiedpush`. This
retains the pilot's release order. Its URI-test and wrapper-checksum patches are
validation changes, so that edge does not establish an inherent code dependency
on UnifiedPush.

### Shared changes

Put shared groundwork in a parent or separate prerequisite. Put glue needed to
combine two otherwise independent features in an integration feature that depends
on both. Record the rationale in the feature README or a `depends` comment. When
only a prefix of a series is shared, make that prefix its own feature.

Resolve cycles by extracting a common prerequisite or combining dependent
changes. Duplicating patches or relying on alphabetical order hides dependencies.
Textual overlap and clean application alone do not establish semantic independence.

The generic forest runner allows dependent features to edit the same file. The
#827 parity harness additionally enforces its declared disjoint path ownership.
A new integration that shares an owned file needs a corresponding reviewed change
to that application's evidence policy.

## Inspect and apply

Git and Python 3.10+ are sufficient for the forest commands. The following
commands use the default `patches/827` pilot. Run them from the repository root:

```sh
python3 tools/827/forest.py check
python3 tools/827/forest.py series
python3 tools/827/forest.py series --feature unifiedpush
python3 tools/827/forest.py apply --repo . --worktree /tmp/molly-feature \
  --feature unifiedpush
python3 tools/827/forest.py verify --repo .
```

`--feature` can be repeated to select several features and their prerequisite
closures. Omitting it selects the full forest. `series` prints the ordered patch
paths relative to `patches/827`, which is useful for inspection or other tooling:

```sh
python3 tools/827/forest.py series > /tmp/molly.series
```

Use `forest.py apply` to replay that forest. The list alone does not supply the
runner's destination checks or Git settings; a bare `git am` loop is not an
equivalent replay command.

For the complete Molly forest, select its patch root explicitly:

```sh
python3 tools/827/forest.py check --patches patches/molly
python3 tools/827/forest.py series --patches patches/molly
python3 tools/827/verify_complete.py --repo . --patches patches/molly
```

The complete verifier checks source pins, merge ancestry, snapshot provenance,
actual changed-path ownership and coverage, then replays two legal full orders.
Both results must equal the entire pinned Molly tree, with a clean index and
working files and no untracked files, including ignored files. Its sixteen groups organize
review; they do not promise that a selected subset compiles independently.
See the [complete forest guide](../../patches/molly/README.md) for pins, grouping
and the required Git history.

### Porting to another Signal release

The [Signal 8.33.2 port guide](../../patches/molly-signal-8.33.2/README.md) describes
its source merge, export and build commands. Its feature directories separate
`carryover` mailboxes from `adapted` mailboxes. Carryover requires unchanged
upstream file entries and unchanged Molly target entries relative to the two
origin pins. All other exported file changes are adapted; changes already
absorbed by upstream need no mailbox. Mode and symlink changes count as changes.

These categories are checked from Git trees, not inferred from a clean patch
application. They help focus review on affected modules; a carryover file can
still need runtime validation because its callers or dependencies have changed.
Each path remains whole and belongs to one feature and one mailbox.

Before starting another port, `port_impact.py` compares the original complete
forest with a proposed Signal base without editing a checkout:

```sh
python3 tools/827/port_impact.py --repo . --source-forest patches/molly \
  --base 6e9dddc01f1b26e608ac683807c51e139c141ed2
```

### Worktree and Git behavior

Every `apply` creates a new detached worktree at `base`. Existing destinations,
symlink components, parent traversal, and destinations inside the source checkout
are refused. The source branch, index, and uncommitted files are not reset,
cleaned, or committed.

The Git helpers remove inherited repository-location and index overrides before
running commands against the selected repository. Replay disables hooks, commit
signing, rerere reuse, and automatic line-ending conversion, and skips LFS
smudging. Mailbox authorship is preserved; the replay committer identity is
explicit and the committer date follows the author date. Patches apply with
`git am --no-3way --whitespace=nowarn`, so local whitespace-fix settings cannot
silently rewrite their content. A final `git diff --check` checks the result.
Carrier `.hangar` state is rejected in the release tree.

The complete-source verifier handles the pinned target's inherited whitespace
by requiring an exact trusted target-tree match and reporting those findings.
The generic CLI retains its strict whitespace policy, so use
`verify_complete.py` for `patches/molly` rather than the generic `apply`/`verify`
commands. Neither path silently fixes whitespace.

A failed standalone application retains the worktree and am state. In a normal
shell without exported Git repository overrides, inspect it with:

```sh
git -C /tmp/molly-feature status
git -C /tmp/molly-feature am --show-current-patch
```

After inspection, `git -C /tmp/molly-feature am --abort` aborts that worktree's
application; `git worktree remove /tmp/molly-feature` removes it. The runner does
not resolve conflicts automatically.

### Verification scope

`forest.py verify` applies each feature with only its declared prerequisites,
then applies the full forest in ascending and descending ready-node order and
compares the resulting trees. Its temporary worktrees are removed after each
case, including failures. This detects some missing dependencies and ordering
interactions. It is not exhaustive permutation testing, isolated-feature
compilation, or proof of semantic independence.

For the pilot's application-specific checks:

```sh
python3 -m unittest discover -s tools/827 -p 'test_*.py'
python3 tools/827/validate.py --repo .
python3 tools/827/validate_inventory.py --repo .
python3 tools/827/replay_twice.py --repo . \
  --worktree-prefix /tmp/molly827 --report reports/827/replay/replay-twice.json
```

The full suite and validators need pinned history. Synthetic forest tests run
independently with `python3 tools/827/test_forest.py`; Android checks are in the
[runbook](RUNBOOK.md).

## Authoring and upgrading

Develop each feature on a linear topic branch based on the upstream base and its
prerequisites. Export only that feature's commits. With reviewed old and new
boundary refs:

```sh
test "$(git rev-list --count --merges "$FEATURE_BASE..$FEATURE_TIP")" = 0 || exit 1
git format-patch --binary --full-index --output-directory /tmp/feature-v2 \
  "$FEATURE_BASE..$FEATURE_TIP"
git range-diff "$OLD_FEATURE_BASE..$OLD_FEATURE_TIP" "$FEATURE_BASE..$FEATURE_TIP"
```

Review new mailboxes and `series` changes together and remove obsolete patches.
Retain meaningful commit messages, authorship, and `Source-Commit:` or
`Source-Commits:` trailers for ported changes. The application validator checks
those source refs against the pinned Molly history. A mailbox's `From` ID
identifies the exported commit; it does not itself prove upstream authorship or
require that reconstructed commit object to remain available.

For an upstream upgrade, resolve conflicts in maintenance branches, export the
reviewed linear series, and update `base`. The generic runner supports another
base. The bounded #827 harness also pins its base, comparison target, expected
application commit/tree, and parity assertions, so upgrading that proof requires
reviewing those inputs together. Expected hashes describe the intended result;
changing them to match an unexplained failure removes the check.

The complete Molly forest is a snapshot export of the full base-to-target delta.
Its `Source-Commit:` trailers identify the target snapshot, including imported
code, upstream fixes and merge resolutions; they are not per-hunk authorship
claims. Changing that snapshot requires reviewing its base, target and upstream
merge pins together and verifying the complete resulting tree. Keep adaptations
to another base separate from a forest that promises exact target equality.

After pilot parity-evidence changes, run `python3 tools/827/refresh_inventory.py --repo .`,
review the derived inventory diff, and validate again. Checksums are computed
from authored inputs. Identify the reviewed Git revision when sharing a release.

## Optional git-carrier maintenance

Git-carrier handles a stopped merge, not a `git am` failure. It can assist
maintenance without becoming a replay dependency: `git park` records stopped
merge state, `git unpark` exposes paths for resolution, and `git land` prepares
the resolved merge for a maintainer commit. Carrier branches and `.hangar` state
are not release patches.

After landing a maintenance merge, reconstruct the affected linear feature
series and compare it with `git range-diff`. `format-patch` omits merge commits;
exporting an arbitrary merge range can therefore lose conflict-resolution work.
Review the feature delta and replayed tree. No automatic carrier adapter is
provided.

References: [git format-patch](https://git-scm.com/docs/git-format-patch),
[git am](https://git-scm.com/docs/git-am),
[git range-diff](https://git-scm.com/docs/git-range-diff), and the
[git-carrier workflow](https://github.com/git-carrier/git-carrier#the-workflow).
