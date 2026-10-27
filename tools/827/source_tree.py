#!/usr/bin/env python3
"""Compute a Git tree ID after excluding declared metadata paths, without changing the checkout."""
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
        index_file = Path(temp) / 'index'
        replay.git(repo, 'read-tree', revision, index_file=index_file)
        if checked:
            replay.git(repo, 'rm', '--cached', '-r', '-f', '--ignore-unmatch', '--', *checked,
                       index_file=index_file)
        return replay.git(repo, 'write-tree', index_file=index_file).output.strip()
