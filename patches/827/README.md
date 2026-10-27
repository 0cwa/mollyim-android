# Patch forest

`base` pins the upstream commit. Each feature directory contains ordinary
`git format-patch` mailboxes and a plain `series` file listing them in order.
A nested feature depends on its parent feature; an optional `depends` file lists
additional forest-relative feature prerequisites. Independent siblings have no
implied dependency. All listed prerequisites apply before the consumer's series.

```sh
python3 tools/827/forest.py check
python3 tools/827/forest.py series
python3 tools/827/forest.py apply --repo . --worktree /tmp/molly-replay
python3 tools/827/forest.py verify --repo .
```

Run from the repository root. Standalone application preserves a failed worktree
for inspection; verification uses disposable temporary worktrees. Application
parity evidence is separate in `docs/827/parity-evidence.json`, not a patch catalog.
See [the audit and maintenance guide](../../docs/827/PATCH-FOREST.md) for nested
features, cross-tree dependencies, re-exporting patches, release gates, and the
optional git-carrier maintenance boundary. This remains the bounded #827 PoC,
not a full Molly reconstruction or a claim of production readiness.
