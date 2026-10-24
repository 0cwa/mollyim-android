#!/usr/bin/env python3
"""Validate the Molly #827 patch series and its mailbox provenance."""
import argparse
import json
import re
from pathlib import Path
import sys
import subprocess

import replay

PINNED_SIGNAL_BASE = replay.PINNED_SIGNAL_BASE
PINNED_MOLLY_TARGET = replay.PINNED_MOLLY_TARGET
COMMIT = re.compile(r'^From ([0-9a-f]{40}) ', re.M)
SOURCE = re.compile(r'^Source-Commits?:\s*(.*)$', re.M)
SHA = re.compile(r'^[0-9a-f]{40}$')


def validate(path: Path, repo: Path | None = None) -> dict:
    path = path.resolve()
    repo = (repo or path.parents[1]).resolve()
    try:
        data = json.loads(path.read_text())  # JSON is a valid YAML 1.2 document.
    except Exception as exc:
        raise replay.ReplayError(f'cannot parse series manifest: {exc}') from exc
    version, features = replay.validate_manifest(data, path.parent)
    ids = [f['id'] for f in features]
    seen = set()
    patch_count = 0
    resolved_sources = []
    for item in data['features']:
        fid = item['id']
        deps = item.get('dependencies')
        if not isinstance(deps, list) or any(not isinstance(dep, str) for dep in deps):
            raise replay.ReplayError(f'{fid}: dependencies must be a list of feature IDs')
        if any(dep not in seen for dep in deps):
            raise replay.ReplayError(f'{fid}: dependency must occur earlier in the ordered series')
        if len(deps) != len(set(deps)) or fid in deps:
            raise replay.ReplayError(f'{fid}: invalid or duplicate dependency')
        seen.add(fid)
        patches = item['patches']
        earlier_patches = set()
        for patch in patches:
            deps = patch.get('depends_on')
            if not isinstance(deps, list) or any(dep not in earlier_patches for dep in deps):
                raise replay.ReplayError(f'{fid}: patch dependencies must point to earlier patches')
            content = (path.parent / patch['path']).read_bytes()
            text = content.decode('utf-8', errors='replace')
            match = COMMIT.search(text)
            if not match or match.group(1) != patch.get('mailbox_commit_sha'):
                raise replay.ReplayError(f'{fid}: mailbox commit SHA mismatch: {patch["path"]}')
            source_shas = []
            for field in SOURCE.findall(text):
                references = field.split()
                if any(not SHA.fullmatch(ref) for ref in references):
                    raise replay.ReplayError(f'{fid}: malformed upstream source SHA in {patch["path"]}')
                source_shas.extend(references)
            if patch.get('source_commit_shas') != source_shas:
                raise replay.ReplayError(f'{fid}: source commit references do not match patch metadata')
            expected_kind = 'upstream-source' if source_shas else 'poc-adaptation'
            if patch.get('provenance_kind') != expected_kind:
                raise replay.ReplayError(f'{fid}: upstream-source vs PoC adaptation classification mismatch')
            for source_sha in source_shas:
                object_type = subprocess.run(['git', '-C', str(repo), 'cat-file', '-t', source_sha],
                                             capture_output=True, text=True)
                is_target_ancestor = subprocess.run(['git', '-C', str(repo), 'merge-base', '--is-ancestor',
                                                     source_sha, data['molly_expected']],
                                                    capture_output=True).returncode == 0
                record = {'feature': fid, 'patch': patch['path'], 'source_commit_sha': source_sha,
                          'object_type': object_type.stdout.strip() if object_type.returncode == 0 else None,
                          'resolves': object_type.returncode == 0, 'ancestor_of_molly_target': is_target_ancestor}
                resolved_sources.append(record)
                if record['object_type'] != 'commit' or not is_target_ancestor:
                    raise replay.ReplayError(f'{fid}: source commit missing or outside pinned Molly target history: {source_sha}')
            earlier_patches.add(patch['path'])
            patch_count += 1
    expected_count = data.get('patch_count')
    if expected_count != patch_count:
        raise replay.ReplayError(f'patch_count mismatch: declared {expected_count}, found {patch_count}')
    expected_tree = data.get('expected_tree_sha')
    if not isinstance(expected_tree, str) or not SHA.fullmatch(expected_tree):
        raise replay.ReplayError('expected_tree_sha must be a full 40-character lowercase Git tree SHA')
    return {'status': 'PASS', 'schema_version': version, 'features': ids,
            'patch_count': patch_count, 'signal_base': data['signal_base'],
            'resolved_upstream_sources': resolved_sources,
            'molly_expected': data['molly_expected'], 'expected_tree_sha': data['expected_tree_sha'],
            'message': 'Manifest, full patch checksums, dependency order, and mailbox source provenance verified.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=Path('patches/827/series.yaml'))
    parser.add_argument('--report', type=Path)
    parser.add_argument('--repo', type=Path, default=Path('.'), help='Git checkout containing the pinned target and source commits')
    args = parser.parse_args()
    try:
        result = validate(args.manifest, args.repo)
        code = 0
    except replay.ReplayError as exc:
        result, code = {'status': 'FAIL', 'error': str(exc)}, 1
    serialized = json.dumps(result, indent=2) + '\n'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(serialized)
    print(serialized, end='')
    return code

if __name__ == '__main__':
    raise SystemExit(main())
