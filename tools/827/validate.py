#!/usr/bin/env python3
"""Validate the plain patch forest and the separate #827 parity assertions."""
import argparse
import json
from pathlib import Path
import sys

import replay


def validate(patches: Path, repo: Path, evidence: Path) -> dict:
    data = replay.load_inputs(patches, evidence)
    version, features = replay.validate_evidence(data, patches.absolute())
    resolved_sources = []
    for feature in data['features']:
        for patch in feature['patches']:
            for source_sha in patch['source_commit_shas']:
                object_type = replay.git(repo, 'cat-file', '-t', source_sha, check=False)
                ancestor = replay.git(repo, 'merge-base', '--is-ancestor', source_sha,
                                      data['molly_expected'], check=False).returncode == 0
                record = {'feature': feature['id'], 'patch': patch['path'],
                          'source_commit_sha': source_sha,
                          'object_type': object_type.stdout.strip() if object_type.returncode == 0 else None,
                          'resolves': object_type.returncode == 0,
                          'ancestor_of_molly_target': ancestor}
                resolved_sources.append(record)
                if record['object_type'] != 'commit' or not ancestor:
                    raise replay.ReplayError(f'source commit missing or outside pinned Molly history: {source_sha}')
    return {'status': 'PASS', 'evidence_version': version, 'features': [f['id'] for f in features],
            'patch_count': sum(len(f['patches']) for f in features),
            'inputs_sha256': replay.audit_digest(data), 'signal_base': data['signal_base'],
            'resolved_upstream_sources': resolved_sources,
            'molly_expected': data['molly_expected'], 'expected_tree_sha': data['expected_tree_sha'],
            'message': 'Forest, mailbox provenance, and parity evidence validated; replay is a separate check.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--patches', type=Path, default=Path('patches/827'))
    parser.add_argument('--evidence', type=Path, default=Path('docs/827/parity-evidence.json'))
    parser.add_argument('--report', type=Path)
    parser.add_argument('--repo', type=Path, default=Path('.'))
    args = parser.parse_args()
    try:
        result = validate(args.patches, args.repo.resolve(), args.evidence)
        code = 0
    except (replay.ReplayError, OSError) as exc:
        result, code = {'status': 'FAIL', 'error': str(exc)}, 1
    serialized = json.dumps(result, indent=2) + '\n'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(serialized)
    print(serialized, end='')
    return code


if __name__ == '__main__':
    raise SystemExit(main())
