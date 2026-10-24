#!/usr/bin/env python3
"""Compute a Git tree ID after excluding declared metadata paths, without changing the checkout."""
import os
from pathlib import Path
import tempfile

import replay


def project_tree(repo: Path, revision: str, excluded_paths: list[str]) -> str:
    """Return the tree for `revision` with exact path exclusions applied in a private index."""
    repo = repo.resolve()
    checked = [replay.validate_git_path(path, 'metadata exclusion') for path in excluded_paths]
    if len(checked) != len(set(checked)):
        raise replay.ReplayError('metadata exclusions must be unique')
    with tempfile.TemporaryDirectory(prefix='molly827-source-index-') as temp:
        env = os.environ.copy()
        env['GIT_INDEX_FILE'] = str(Path(temp) / 'index')
        replay.git(repo, 'read-tree', revision, env=env)
        if checked:
            replay.git(repo, 'rm', '--cached', '-r', '-f', '--ignore-unmatch', '--', *checked, env=env)
        return replay.git(repo, 'write-tree', env=env).output.strip()
