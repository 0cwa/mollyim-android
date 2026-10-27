#!/usr/bin/env python3
"""Reconstruct a complete pinned Molly tree, including every path and file mode."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

import forest
import replay


def pin(root, name):
    """Read one immutable commit ID from a forest's plain pin file."""
    values = forest.lines(root / name)
    if len(values) != 1 or not forest.SHA.fullmatch(values[0]):
        raise forest.ForestError(f'{name} must contain exactly one full lowercase commit SHA')
    return values[0]


def commit(repo, value, name):
    result = replay.git(repo, 'cat-file', '-t', value, check=False)
    if result.returncode or result.stdout.strip() != 'commit':
        raise forest.ForestError(f'{name} must resolve to a commit: {value}')


def changed_paths(repo, before, after):
    """Compare raw path names without rename heuristics or text decoding."""
    raw = replay.git(repo, 'diff-tree', '--no-commit-id', '--name-only',
                     '--no-renames', '-r', '-z', before, after, binary=True).stdout
    return set(raw.rstrip(b'\0').split(b'\0')) if raw else set()


def display_paths(paths):
    names = sorted(paths)
    shown = ', '.join(repr(os.fsdecode(path)) for path in names[:10])
    return shown + (f' (and {len(names) - 10} more)' if len(names) > 10 else '')


def clean_worktree(worktree):
    """Require the materialized files and index to agree with the reconstructed commit."""
    for options, label in (((), 'tracked working files'), (('--cached',), 'index')):
        check = replay.git(worktree, 'diff', *options, '--quiet', '--', check=False)
        if check.returncode:
            raw = replay.git(worktree, 'diff', *options, '--name-only', '-z', '--', binary=True).stdout
            paths = set(raw.rstrip(b'\0').split(b'\0')) if raw else set()
            raise forest.ForestError(f'{label} differ from the reconstructed tree: {display_paths(paths)}')
    # Deliberately omit --exclude-standard: ignored build/cache files are extras too.
    raw = replay.git(worktree, 'ls-files', '--others', '-z', binary=True).stdout
    if raw:
        paths = set(raw.rstrip(b'\0').split(b'\0'))
        raise forest.ForestError('unexpected untracked files in reconstructed worktree: '
                                 f'{display_paths(paths)}')


def validate_identity(data, repo):
    """Bind snapshot exports to the target and its recorded Signal merge parent."""
    target = pin(data.root, 'target')
    upstream_merge = pin(data.root, 'upstream-merge')
    for name, value in (('base', data.base), ('target', target), ('upstream-merge', upstream_merge)):
        commit(repo, value, name)
    parents = replay.git(repo, 'rev-list', '--parents', '-n', '1', upstream_merge).stdout.split()[1:]
    if len(parents) != 2 or parents[1] != data.base:
        raise forest.ForestError('upstream-merge must have exactly two parents with base as its second parent')
    if replay.git(repo, 'merge-base', '--is-ancestor', upstream_merge, target, check=False).returncode:
        raise forest.ForestError('upstream-merge must be an ancestor of target')
    for name, metadata in data.metadata.items():
        if metadata['source_commit_shas'] != [target]:
            raise forest.ForestError(f'{name}: Source-Commit must name exactly the pinned target snapshot')
    return {'base': data.base, 'target': target, 'upstream_merge': upstream_merge,
            'expected_tree': replay.git(repo, 'rev-parse', f'{target}^{{tree}}').stdout.strip()}


def ownership(data, repo, head, expected_paths):
    """Require unique feature ownership and complete coverage of the target delta."""
    commits = replay.git(repo, 'rev-list', '--reverse', '--first-parent',
                         f'{data.base}..{head}').stdout.split()
    if len(commits) != len(data.metadata):
        raise forest.ForestError('replay must create exactly one commit per mailbox')
    owners, features = {}, {}
    index = 0
    before = data.base
    for feature in data.order():
        paths = set()
        for _ in feature.patches:
            after = commits[index]
            paths.update(changed_paths(repo, before, after))
            before = after
            index += 1
        for path in paths:
            if path in owners:
                raise forest.ForestError(f'path belongs to both {owners[path]} and {feature.name}: '
                                         f'{os.fsdecode(path)!r}')
            owners[path] = feature.name
        features[feature.name] = {'patches': len(feature.patches), 'changed_paths': len(paths),
                                  'dependencies': list(feature.dependencies)}
    actual_paths = set(owners)
    if actual_paths != expected_paths:
        raise forest.ForestError('feature ownership differs from the complete base-to-target delta; '
                                 f'missing: {display_paths(expected_paths - actual_paths)}; '
                                 f'extra: {display_paths(actual_paths - expected_paths)}')
    return features


def verify(patches, repo, worktree=None):
    """Replay two legal orders and compare their whole Git trees to the source target."""
    repo = Path(repo).resolve()
    data = forest.Forest(patches)
    identity = validate_identity(data, repo)
    requested = forest.destination(repo, worktree) if worktree is not None else None
    expected_paths = changed_paths(repo, data.base, identity['target'])
    result = {'status': 'PASS', **identity, 'changed_paths': len(expected_paths),
              'patches': len(data.metadata), 'features': {}, 'replays': []}
    if requested is not None:
        result['worktree'] = str(requested)
    for reverse in (False, True):
        order = 'reverse-ready' if reverse else 'ready'
        preserve = requested is not None and not reverse
        with tempfile.TemporaryDirectory(prefix='molly-complete-') as temporary:
            destination = requested if preserve else Path(temporary) / 'worktree'
            try:
                applied = forest.apply(data, repo, destination, reverse=reverse,
                                       expected_tree=identity['expected_tree'])
                clean_worktree(destination)
                if not reverse:
                    head = replay.git(destination, 'rev-parse', 'HEAD').stdout.strip()
                    result['features'] = ownership(data, repo, head, expected_paths)
                result['replays'].append({'order': order, 'tree': applied['tree_sha'],
                                          'working_tree_clean': True,
                                          'whitespace_report': applied['whitespace_report']})
            except forest.ForestError as exc:
                detail = str(exc)
                if preserve and destination.exists():
                    detail += f'\nWorktree preserved at {destination}'
                elif not preserve:
                    detail = detail.replace('Worktree preserved at',
                                            'Temporary worktree (removed after verification) at')
                raise forest.ForestError(f'{order}: {detail}') from exc
            finally:
                if not preserve and destination.exists():
                    forest.git(repo, 'worktree', 'remove', '--force', str(destination))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--patches', type=Path, default=Path('patches/molly'))
    parser.add_argument('--repo', type=Path, default=Path('.'))
    parser.add_argument('--worktree', type=Path, help='retain the first replay at a new external destination')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    try:
        result = verify(args.patches, args.repo, args.worktree)
        code = 0
    except (forest.ForestError, replay.ReplayError, OSError, UnicodeError) as exc:
        result, code = {'status': 'FAIL', 'error': str(exc)}, 1
    serialized = json.dumps(result, indent=2) + '\n'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(serialized)
    print(serialized, end='')
    return code


if __name__ == '__main__':
    raise SystemExit(main())
