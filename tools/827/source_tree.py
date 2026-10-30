#!/usr/bin/env python3
"""Compute a pinned application tree in a private Git index without altering the checkout."""
from pathlib import Path
import tempfile

import replay


def project_tree(repo: Path, revision: str, excluded_paths: list[str], *,
                 restore_from: str | None = None, restored_paths: tuple[str, ...] | list[str] = ()) -> str:
    """Exclude metadata and optionally restore pinned CI files in a private index.

    Restoring a small, explicit set of existing workflow files keeps source/patch
    parity tied to the immutable application snapshot. The raw HEAD projection
    remains independently available to report CI-only drift.
    """
    repo = repo.resolve()
    checked = [replay.validate_git_path(path, 'metadata exclusion') for path in excluded_paths]
    restored = [replay.validate_git_path(path, 'CI source override') for path in restored_paths]
    if len(checked) != len(set(checked)) or len(restored) != len(set(restored)):
        raise replay.ReplayError('projection paths must be unique')
    if set(checked) & set(restored):
        raise replay.ReplayError('CI source overrides cannot be metadata exclusions')
    if (restore_from is None) != (not restored):
        raise replay.ReplayError('restore_from and restored_paths must be supplied together')
    with tempfile.TemporaryDirectory(prefix='molly827-source-index-') as temp:
        index_file = Path(temp) / 'index'
        replay.git(repo, 'read-tree', revision, index_file=index_file)
        if checked:
            replay.git(repo, 'rm', '--cached', '-r', '-f', '--ignore-unmatch', '--', *checked,
                       index_file=index_file)
        if restored:
            # --staged never writes the worktree; the private index preserves
            # exact pinned blobs, executable modes, and path types.
            replay.git(repo, 'restore', '--source', restore_from, '--staged', '--', *restored,
                       index_file=index_file)
        return replay.git(repo, 'write-tree', index_file=index_file).output.strip()
