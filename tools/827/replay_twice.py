#!/usr/bin/env python3
"""Replay the series twice into independent worktrees and compare Git trees."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path('.'))
    parser.add_argument('--manifest', type=Path, default=Path('patches/827/series.yaml'))
    parser.add_argument('--worktree-prefix', required=True, type=Path)
    parser.add_argument('--report', required=True, type=Path)
    args = parser.parse_args()
    repo, manifest = args.repo.resolve(), args.manifest.resolve()
    prefix = args.worktree_prefix.absolute()
    worktrees = [Path(f'{prefix}-run-{n}') for n in (1, 2)]
    existing = [str(p) for p in worktrees if os.path.lexists(p)]
    result = {'status': 'STARTED', 'runs': [], 'tree_sha_equal': False,
              'expected_tree_sha': None, 'worktrees_preserved': [str(p) for p in worktrees]}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    try:
        validation = subprocess.run([sys.executable, str(Path(__file__).with_name('validate.py')),
                                     '--manifest', str(manifest), '--repo', str(repo)], capture_output=True, text=True)
        if validation.returncode:
            raise RuntimeError(f'manifest validation failed: {validation.stdout}{validation.stderr}')
        manifest_data = json.loads(manifest.read_text())
        result['expected_tree_sha'] = manifest_data['expected_tree_sha']
        if existing:
            raise RuntimeError(f'refusing existing worktree destinations: {existing}')
        for index, worktree in enumerate(worktrees, 1):
            child_report = args.report.parent / f'{args.report.stem}-run-{index}.json'
            cmd = [sys.executable, str(Path(__file__).with_name('replay.py')), '--repo', str(repo),
                   '--manifest', str(manifest), '--worktree', str(worktree), '--report', str(child_report)]
            proc = subprocess.run(cmd, capture_output=True, text=True)
            log = args.report.parent / f'{args.report.stem}-run-{index}.log'
            log.write_text(proc.stdout + proc.stderr)
            child = json.loads(child_report.read_text()) if child_report.exists() else {}
            result['runs'].append({'command': cmd, 'exit_code': proc.returncode,
                                   'report': str(child_report), 'log': str(log),
                                   'status': child.get('status'), 'tree_sha': child.get('tree_sha'),
                                   'expected_tree_match': child.get('expected_tree_match')})
            if proc.returncode or child.get('status') != 'PASS':
                raise RuntimeError(f'replay {index} failed; see {child_report} and {log}')
        result['tree_sha_equal'] = result['runs'][0]['tree_sha'] == result['runs'][1]['tree_sha']
        result['status'] = ('PASS' if result['tree_sha_equal'] and
                            all(r['tree_sha'] == result['expected_tree_sha'] for r in result['runs'])
                            else 'TREE_MISMATCH')
    except Exception as exc:
        result.update(status='FAIL', error=str(exc))
    args.report.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'PASS' else 1

if __name__ == '__main__':
    raise SystemExit(main())
