# Patch forest

`base` pins the upstream commit. Each feature directory contains ordinary
`git format-patch` mailboxes and a plain `series` file listing them in order.
A nested feature requires its parent feature; an optional `depends` file lists
additional forest-relative prerequisites. Siblings have no implicit dependency.

Run from the repository root with Git and Python 3.10+:

```sh
python3 tools/827/forest.py check
python3 tools/827/forest.py series
python3 tools/827/forest.py apply --repo . --worktree /tmp/molly-replay
python3 tools/827/forest.py verify --repo .
```

`apply` creates a new detached worktree and preserves it on failure for inspection.
`verify` uses temporary worktrees to check feature closures and two legal full
orders. Application assertions are separate in `docs/827/parity-evidence.json`.

See the [maintenance guide](../../docs/827/PATCH-FOREST.md) for dependency semantics,
patch authoring, Git safety settings, and the optional git-carrier boundary.
The [runbook](../../docs/827/RUNBOOK.md) covers application checks, and
[PARITY.md](../../docs/827/PARITY.md) defines this bounded launcher-artwork and
UnifiedPush proof's scope.
