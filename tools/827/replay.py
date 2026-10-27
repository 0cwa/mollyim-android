#!/usr/bin/env python3
"""Replay a pinned, ordered patch series and verify full paths plus anchored integration fragments."""
import argparse
import hashlib
import gzip
import io
import json
import os
import re
import subprocess
import sys

from forest import Forest, ForestError, clean_git_env
from pathlib import Path, PurePosixPath


SHA = re.compile(r'^[a-f0-9]{40}$')
HEX64 = re.compile(r'^[a-f0-9]{64}$')
PINNED_SIGNAL_BASE = 'c47a74ba0961903eeaeda6d22347a990056c3e83'
PINNED_MOLLY_TARGET = '0e202dda90785771ff8c87526eaaf30c655f54f3'
ALLOWED_METADATA_EXCLUSIONS = {'.github/workflows/827-poc.yml', '.github/workflows/827-patch-forest.yml', 'docs/827', 'patches/827', 'reports/827', 'tools/827'}
class ReplayError(RuntimeError):
    pass

def git(repo, *args, check=True, env=None, binary=False, index_file=None):
    """Use the explicit repository, with an optional caller-created private index."""
    cmd = ['git', '-C', str(repo), *args]
    run_env = clean_git_env(env)
    if index_file is not None:
        run_env['GIT_INDEX_FILE'] = str(index_file)
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=run_env)
    if check and p.returncode:
        detail = p.stdout.decode(errors='replace')
        raise ReplayError(f"Command failed ({p.returncode}): {' '.join(cmd)}\n{detail}")
    if not binary:
        p.stdout = p.stdout.decode(errors='replace')
    p.output = p.stdout
    return p

def load_inputs(patch_root, evidence_path):
    """Join plain patch data with separate application assertions in memory only."""
    try:
        forest = Forest(patch_root)
        evidence = json.loads(Path(evidence_path).read_text(encoding='utf-8'))
    except (ForestError, OSError, ValueError) as exc:
        raise ReplayError(f'cannot load patch forest / parity evidence: {exc}') from exc
    if not isinstance(evidence, dict) or evidence.get('evidence_version') != 1:
        raise ReplayError('evidence_version must be 1')
    # The evidence file cannot override patch selection, topology, or the base.
    forbidden = {'signal_base', 'schema_version', 'patch_count', 'patch_provenance', 'expected_validation_commands'}
    if forbidden & evidence.keys():
        raise ReplayError('patch metadata belongs in the forest, not parity evidence')
    entries = evidence.get('features')
    if not isinstance(entries, list) or any(not isinstance(f, dict) for f in entries):
        raise ReplayError('evidence features must be a list of objects')
    allowed = {'id', 'parity_paths', 'integration_paths', 'adaptation_paths', 'added_paths'}
    for entry in entries:
        if set(entry) - allowed:
            raise ReplayError(f'unknown feature evidence fields: {sorted(set(entry) - allowed)}')
        if not isinstance(entry.get('id'), str):
            raise ReplayError('evidence feature needs an id')
    by_id = {f['id']: f for f in entries}
    if len(by_id) != len(entries) or set(by_id) != set(forest.features):
        raise ReplayError('evidence must cover each forest feature exactly once')
    features = []
    for feature in forest.order():
        features.append({**by_id[feature.name], 'dependencies': list(feature.dependencies),
                         'patches': [forest.metadata[name] for name in feature.patches]})
    return {**evidence, 'signal_base': forest.base, 'features': features}


def audit_digest(inputs):
    """Digest the derived topology, patch bytes/provenance, and parity assertions."""
    return hashlib.sha256(json.dumps(inputs, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def validate_git_path(name, label):
    if not isinstance(name, str) or not name or '\\' in name or '\0' in name:
        raise ReplayError(f'invalid {label}: {name!r}')
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in ('', '.', '..') for part in name.split('/')):
        raise ReplayError(f'invalid {label}: {name!r}')
    if name == '.git' or name.startswith('.git/'):
        raise ReplayError('never claim .git internals')
    return name.rstrip('/')

def covers(scope, path):
    return path == scope or path.startswith(scope.rstrip('/') + '/')

def overlap(a, b):
    return covers(a, b) or covers(b, a)

def validate_evidence(manifest, root):
    version = manifest.get('evidence_version')
    if version != 1:
        raise ReplayError('evidence_version must be 1')
    if not isinstance(manifest.get('expected_tree_sha'), str) or not SHA.fullmatch(manifest['expected_tree_sha']):
        raise ReplayError('expected_tree_sha must be a full pinned Git tree SHA')
    expected_application_commit = manifest.get('expected_application_commit')
    if not isinstance(expected_application_commit, str) or not SHA.fullmatch(expected_application_commit):
        raise ReplayError('expected_application_commit must be a full pinned commit SHA')
    metadata_exclusions = manifest.get('metadata_exclusions')
    if not isinstance(metadata_exclusions, list) or set(metadata_exclusions) != ALLOWED_METADATA_EXCLUSIONS:
        raise ReplayError('metadata_exclusions must match the explicit #827 metadata path allowlist')
    for excluded in metadata_exclusions:
        validate_git_path(excluded, 'metadata exclusion')
    for key in ('signal_base', 'molly_expected'):
        if not isinstance(manifest.get(key), str) or not SHA.fullmatch(manifest[key]):
            raise ReplayError(f'{key} must be pinned full 40-hex commit SHA')
    if manifest['signal_base'] != PINNED_SIGNAL_BASE:
        raise ReplayError(f'signal_base must remain pinned to audited Signal commit {PINNED_SIGNAL_BASE}')
    if manifest['molly_expected'] != PINNED_MOLLY_TARGET:
        raise ReplayError(f'molly_expected must remain pinned to audited Molly target {PINNED_MOLLY_TARGET}')
    features = manifest.get('features')
    if not isinstance(features, list) or len(features) < 2:
        raise ReplayError('PoC needs at least two feature bundles')
    ids, claims, prepared = set(), [], []
    ordered_ids = []
    for feature in features:
        if not isinstance(feature, dict):
            raise ReplayError('feature entries must be objects')
        feature_id = feature.get('id')
        if not isinstance(feature_id, str) or not re.fullmatch(r'[a-z][a-z0-9-]*(?:/[a-z][a-z0-9-]*)*', feature_id) or feature_id in ids:
            raise ReplayError('feature IDs must be unique slug strings')
        dependencies = feature.get('dependencies', [])
        if not isinstance(dependencies, list) or any(dep not in ordered_ids for dep in dependencies):
            raise ReplayError(f'{feature_id} dependencies must be listed earlier in manifest order')
        ids.add(feature_id)
        ordered_ids.append(feature_id)
        patches = feature.get('patches')
        if not isinstance(patches, list) or not patches:
            raise ReplayError(f'{feature_id} needs real nonempty patches')
        parity_paths = feature.get('parity_paths', [])
        integrations = feature.get('integration_paths', [])
        adaptations = feature.get('adaptation_paths', [])
        added_paths = feature.get('added_paths', [])
        if not isinstance(parity_paths, list) or not isinstance(integrations, list) or not isinstance(adaptations, list) or not isinstance(added_paths, list):
            raise ReplayError(f'{feature_id} path declarations must be lists')
        if not parity_paths and not integrations and not adaptations and not added_paths:
            raise ReplayError(f'{feature_id} needs parity_paths, integration_paths, or adaptation_paths')
        scopes = []
        for item in parity_paths:
            scope = validate_git_path(item, 'parity path')
            scopes.append(('parity', scope))
        int_prepared = []
        for entry in integrations:
            if not isinstance(entry, dict):
                raise ReplayError(f'{feature_id} integration path entry must be an object')
            path = validate_git_path(entry.get('path'), 'integration path')
            fragments = entry.get('fragments')
            if not isinstance(fragments, list) or not fragments:
                raise ReplayError(f'{feature_id}:{path} needs at least one fragment check')
            fragment_ids = set()
            checked = []
            for fragment in fragments:
                if not isinstance(fragment, dict):
                    raise ReplayError('integration fragment must be an object')
                fid = fragment.get('id')
                start = fragment.get('start_anchor')
                end = fragment.get('end_anchor')
                evidence = fragment.get('evidence')
                digest = fragment.get('target_sha256')
                if not isinstance(fid, str) or not fid or fid in fragment_ids:
                    raise ReplayError(f'{feature_id}:{path} fragment IDs must be unique strings')
                if not isinstance(start, str) or not start or not isinstance(end, str) or not end:
                    raise ReplayError(f'{feature_id}:{path}:{fid} needs nonempty start/end anchors')
                if not isinstance(evidence, str) or not evidence.strip():
                    raise ReplayError(f'{feature_id}:{path}:{fid} needs an evidence record')
                if not isinstance(digest, str) or not HEX64.fullmatch(digest):
                    raise ReplayError(f'{feature_id}:{path}:{fid} target_sha256 must be lowercase SHA-256')
                fragment_ids.add(fid)
                checked.append({'id': fid, 'start_anchor': start, 'end_anchor': end,
                                'target_sha256': digest, 'evidence': evidence})
            scopes.append(('integration', path))
            int_prepared.append({'path': path, 'fragments': checked})
        adaptation_prepared = []
        for entry in adaptations:
            if not isinstance(entry, dict):
                raise ReplayError(f'{feature_id} adaptation path entry must be an object')
            path = validate_git_path(entry.get('path'), 'adaptation path')
            if entry.get('path', '').endswith('/'):
                raise ReplayError(f'{feature_id}:{path} adaptation path must name a file')
            expected = entry.get('expected_replay_sha256')
            target_digest = entry.get('target_sha256')
            evidence = entry.get('evidence')
            tests = entry.get('tests')
            if not isinstance(expected, str) or not HEX64.fullmatch(expected):
                raise ReplayError(f'{feature_id}:{path} expected_replay_sha256 must be lowercase SHA-256')
            if not isinstance(target_digest, str) or not HEX64.fullmatch(target_digest):
                raise ReplayError(f'{feature_id}:{path} target_sha256 must be lowercase SHA-256')
            if expected == target_digest:
                raise ReplayError(f'{feature_id}:{path} adaptation hashes must differ; use parity_paths for exact target parity')
            if not isinstance(evidence, str) or len(evidence.strip()) < 20:
                raise ReplayError(f'{feature_id}:{path} needs substantive adaptation evidence')
            if not isinstance(tests, list) or not tests or any(not isinstance(t, str) or not t.strip() for t in tests):
                raise ReplayError(f'{feature_id}:{path} needs test/report references')
            scopes.append(('adaptation', path))
            adaptation_prepared.append({'path': path, 'expected_replay_sha256': expected,
                                         'target_sha256': target_digest, 'evidence': evidence.strip(),
                                         'tests': tests})
        added_prepared = []
        for entry in added_paths:
            if not isinstance(entry, dict):
                raise ReplayError(f'{feature_id} added path entry must be an object')
            path = validate_git_path(entry.get('path'), 'target-absent added path')
            expected = entry.get('expected_replay_sha256')
            evidence = entry.get('evidence')
            tests = entry.get('tests')
            if not isinstance(expected, str) or not HEX64.fullmatch(expected):
                raise ReplayError(f'{feature_id}:{path} expected_replay_sha256 must be lowercase SHA-256')
            if not isinstance(evidence, str) or len(evidence.strip()) < 20:
                raise ReplayError(f'{feature_id}:{path} needs substantive target-absence evidence')
            if not isinstance(tests, list) or not tests or any(not isinstance(t, str) or not t.strip() for t in tests):
                raise ReplayError(f'{feature_id}:{path} needs test/report references')
            scopes.append(('added', path))
            added_prepared.append({'path': path, 'expected_replay_sha256': expected,
                                   'evidence': evidence.strip(), 'tests': tests})
        for kind, scope in scopes:
            for previous_id, previous_scope in claims:
                if overlap(scope, previous_scope):
                    raise ReplayError(f'overlapping path ownership: {previous_id}:{previous_scope} and {feature_id}:{scope}')
            claims.append((feature_id, scope))
        # Forest has already validated paths, mailboxes, order, and dependencies.
        patch_prepared = [{'file': p['path'], 'resolved': root / p['path'], 'sha256': p['sha256']}
                          for p in patches]
        prepared.append({'id': feature_id, 'parity_paths': [s for k, s in scopes if k == 'parity'],
                         'integration_paths': int_prepared, 'adaptation_paths': adaptation_prepared,
                         'added_paths': added_prepared,
                         'scopes': [s for _, s in scopes],
                         'patches': patch_prepared})
    return version, prepared

def named_paths(repo, old, new):
    raw = git(repo, 'diff', '--name-only', '-z', old, new, binary=True).stdout
    return [p.decode('utf-8', errors='surrogateescape') for p in raw.split(b'\0') if p]

def fragment_bytes(blob, check, label):
    start = check['start_anchor'].encode('utf-8')
    end = check['end_anchor'].encode('utf-8')
    first = blob.find(start)
    last = blob.rfind(start)
    if first < 0 or first != last:
        raise ReplayError(f'{label}: start anchor must occur exactly once')
    end_first = blob.find(end)
    end_last = blob.rfind(end)
    if end_first < 0 or end_first != end_last:
        raise ReplayError(f'{label}: end anchor must occur exactly once')
    end_pos = end_first + len(end)
    if end_pos <= first:
        raise ReplayError(f'{label}: end anchor precedes start anchor')
    return blob[first:end_pos]

def blob(repo, rev, path):
    p = git(repo, 'show', f'{rev}:{path}', check=False, binary=True)
    if p.returncode:
        raise ReplayError(f'cannot read declared path {path!r} at {rev}')
    return p.stdout

def deterministic_gzip(data):
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode='wb', filename='', compresslevel=9, mtime=0) as stream:
        stream.write(data)
    return buffer.getvalue()

def write_residual_diff(directory, name, data):
    compressed = deterministic_gzip(data)
    artifact = directory / (name + '.gz')
    artifact.write_bytes(compressed)
    uncompressed_sha = hashlib.sha256(data).hexdigest()
    compressed_sha = hashlib.sha256(compressed).hexdigest()
    return {'artifact': str(artifact), 'compressed_path': str(artifact),
            'compressed_sha256': compressed_sha, 'compressed_bytes': len(compressed),
            'uncompressed_sha256': uncompressed_sha, 'uncompressed_bytes': len(data),
            'sha256': uncompressed_sha, 'bytes': len(data), 'empty': not data,
            'compression': {'format': 'gzip', 'mtime': 0, 'level': 9}}

def conflict_markers(repo, paths):
    found = []
    marker = re.compile(rb'^(?:<<<<<<< .+|=======|>>>>>>> .+)(?:\r?\n)?$')
    for path in paths:
        result = git(repo, 'show', f'HEAD:{path}', check=False, binary=True)
        if result.returncode:
            continue
        if b'\0' in result.stdout:
            continue
        for line_no, line in enumerate(result.stdout.splitlines(keepends=True), 1):
            if marker.fullmatch(line):
                found.append({'path': path, 'line': line_no, 'marker': line.decode('utf-8', errors='replace').strip()})
    return found

def run_replay(args):
    source = args.repo.resolve()
    root = args.patches.absolute()
    expected_application_commit = None
    metadata_exclusions = None
    raw_worktree = args.worktree
    worktree = raw_worktree.absolute()
    if '..' in raw_worktree.parts:
        raise ReplayError('REFUSE: worktree destination may not contain parent traversal')
    candidate = Path(worktree.anchor)
    for part in worktree.parts[1:]:
        candidate = candidate / part
        if candidate.is_symlink():
            raise ReplayError(f'REFUSE: symlink component in worktree destination: {candidate}')
    if os.path.lexists(worktree):
        raise ReplayError(f'REFUSE: worktree destination exists (including symlinks): {worktree}')
    resolved_worktree = worktree.resolve(strict=False)
    if resolved_worktree == source or resolved_worktree.is_relative_to(source):
        raise ReplayError('REFUSE: worktree destination inside source checkout')
    manifest = load_inputs(root, args.evidence)
    version, features = validate_evidence(manifest, root)
    expected_application_commit = manifest['expected_application_commit']
    metadata_exclusions = manifest['metadata_exclusions']
    for key in ('signal_base', 'molly_expected'):
        if git(source, 'cat-file', '-t', manifest[key]).stdout.strip() != 'commit':
            raise ReplayError(f'missing commit {key}: {manifest[key]}')
    if git(source, 'merge-base', '--is-ancestor', manifest['signal_base'], manifest['molly_expected'], check=False).returncode:
        raise ReplayError('Signal is not ancestor of expected Molly commit')
    if git(source, 'cat-file', '-t', expected_application_commit, check=False).output.strip() != 'commit':
        raise ReplayError(f'missing expected application source commit: {expected_application_commit}')
    from source_tree import project_tree
    expected_source_tree = project_tree(source, expected_application_commit, metadata_exclusions)
    if expected_source_tree != manifest['expected_tree_sha']:
        raise ReplayError('expected_tree_sha does not match projected expected_application_commit tree')
    source_projection_tree = project_tree(source, 'HEAD', metadata_exclusions)

    for feature in manifest['features']:
        for patch in feature['patches']:
            for source_sha in patch.get('source_commit_shas', []):
                if git(source, 'cat-file', '-t', source_sha, check=False).returncode or git(
                        source, 'merge-base', '--is-ancestor', source_sha, manifest['molly_expected'], check=False).returncode:
                    raise ReplayError(f'upstream source commit is missing or outside pinned Molly target history: {source_sha}')

    args.report.parent.mkdir(parents=True, exist_ok=True)
    log_dir = args.report.parent / (args.report.stem + '-logs')
    diff_dir = args.report.parent / (args.report.stem + '-residual-diffs')
    log_dir.mkdir(parents=True, exist_ok=True)
    safe_env = clean_git_env()
    safe_env['GIT_LFS_SKIP_SMUDGE'] = '1'
    has_integrations = any(f['integration_paths'] for f in features)
    has_adaptations = any(f['adaptation_paths'] for f in features)
    has_added_paths = any(f['added_paths'] for f in features)
    report = {
        'status': 'STARTED', 'evidence_version': version, 'inputs_sha256': audit_digest(manifest),
        'signal_base': manifest['signal_base'], 'molly_expected': manifest['molly_expected'],
        'worktree': str(worktree), 'expected_tree_sha': manifest.get('expected_tree_sha'),
        'expected_application_commit': manifest['expected_application_commit'],
        'source_head_sha': git(source, 'rev-parse', 'HEAD').output.strip(),
        'source_projected_tree_sha': source_projection_tree,
        'metadata_exclusions': manifest['metadata_exclusions'], 'features': [], 'warnings': [
            'Full parity is checked only on declared parity_paths; this is not full application or APK equivalence.'
        ],
        'original_A2_4': 'REVISED' if (has_integrations or has_adaptations) else 'FULL_DECLARED_PATH_PARITY',
        'parity_claims': {'full_file_parity_paths': [], 'anchored_integration_fragments': [],
                          'documented_adaptations': [], 'target-absent-added-paths': []},
    }
    try:
        git(source, '-c', 'core.hooksPath=/dev/null', 'worktree', 'add', '--detach', str(worktree), manifest['signal_base'], env=safe_env)
        for feature in features:
            previous_head = git(worktree, 'rev-parse', 'HEAD').output.strip()
            record = {'id': feature['id'], 'patches': [], 'parity_paths': feature['parity_paths'],
                      'integration_paths': feature['integration_paths'],
                      'adaptation_paths': feature['adaptation_paths'],
                      'added_paths': feature['added_paths']}
            report['features'].append(record)
            for index, patch_info in enumerate(feature['patches'], start=1):
                patch = patch_info['resolved']
                data = patch.read_bytes()
                actual = hashlib.sha256(data).hexdigest()
                if actual != patch_info['sha256']:
                    raise ReplayError(f'patch changed after validation: {patch_info["file"]}')
                log_path = log_dir / f'{feature["id"].replace("/", "_")}-{index:02d}.git-am.log'
                cmd = git(worktree, '-c', 'core.hooksPath=/dev/null',
                          '-c', 'user.name=Molly Replay Tool',
                          '-c', 'user.email=molly-replay-tool@example.invalid',
                          '-c', 'commit.gpgSign=false',
                          '-c', 'rerere.enabled=false', '-c', 'core.autocrlf=false',
                          'am', '--committer-date-is-author-date', '--no-3way', '--whitespace=nowarn', str(patch),
                          check=False, env=safe_env, binary=True)
                log_data = cmd.stdout
                log_path.write_bytes(log_data)
                record['patches'].append({'file': patch_info['file'], 'sha256': actual,
                    'result': cmd.returncode, 'full_log': str(log_path),
                    'full_log_sha256': hashlib.sha256(log_data).hexdigest()})
                if cmd.returncode:
                    report['status'] = 'PATCH_FAILED'
                    log_text = log_data.decode('utf-8', errors='replace')
                    report['git_am_failure'] = {'patch': patch_info['file'], 'log_path': str(log_path),
                                                'log_tail': log_text.splitlines()[-40:]}
                    raise ReplayError(f'Patch failed: {patch_info["file"]} (worktree left for inspection; git am --abort before cleanup)')
            feature_changes = named_paths(worktree, previous_head, 'HEAD')
            record['changed_paths'] = feature_changes
            feature_unowned = [p for p in feature_changes if not any(covers(scope, p) for scope in feature['scopes'])]
            record['unowned_changes'] = feature_unowned
            if feature_unowned:
                report['status'] = 'OWNERSHIP_FAILED'
                raise ReplayError(f'Feature {feature["id"]} changed unowned paths: {feature_unowned}')
        if git(worktree, 'ls-files', '--', '.hangar').output.strip():
            raise ReplayError('carrier .hangar state must not enter a release tree')
        report['tree_sha'] = git(worktree, 'rev-parse', 'HEAD^{tree}').output.strip()
        report['expected_tree_match'] = (report['tree_sha'] == manifest['expected_tree_sha']) if manifest.get('expected_tree_sha') else None
        report['source_projection_match'] = report['source_projected_tree_sha'] == report['tree_sha']
        changed = named_paths(worktree, manifest['signal_base'], 'HEAD')
        report['changed_paths'] = changed
        scopes = [scope for feature in features for scope in feature['scopes']]
        unowned = [p for p in changed if not any(covers(scope, p) for scope in scopes)]
        report['unowned_changes'] = unowned

        full_parity = {}
        for feature in features:
            for path in feature['parity_paths']:
                diff = git(worktree, 'diff', '--no-ext-diff', '--name-only', manifest['molly_expected'], 'HEAD', '--', path)
                paths = diff.output.splitlines()
                full_parity[path] = {'pass': not paths, 'different_files': paths,
                                     'claim': 'exact declared path tree parity'}
                report['parity_claims']['full_file_parity_paths'].append(path)
        report['parity'] = full_parity

        fragment_results, residuals = [], []
        for feature in features:
            for integration in feature['integration_paths']:
                path = integration['path']
                diff = git(worktree, 'diff', '--no-ext-diff', '--no-color', manifest['molly_expected'], 'HEAD', '--', path, binary=True)
                diff_dir.mkdir(parents=True, exist_ok=True)
                name = hashlib.sha256((feature['id'] + '\0' + path).encode()).hexdigest()[:16] + '.diff'
                residual = write_residual_diff(diff_dir, name, diff.stdout)
                residual.update({'feature': feature['id'], 'path': path})
                residuals.append(residual)
                target_blob = blob(source, manifest['molly_expected'], path)
                replay_blob = blob(worktree, 'HEAD', path)
                for check in integration['fragments']:
                    label = f'{feature["id"]}:{path}:{check["id"]}'
                    expected = check['target_sha256']
                    result = {'feature': feature['id'], 'path': path, 'fragment_id': check['id'],
                              'evidence': check['evidence'], 'target_sha256': None, 'replay_sha256': None,
                              'pass': False, 'whole_file_parity_claimed': False}
                    errors = []
                    try:
                        target_fragment = fragment_bytes(target_blob, check, label + ' target')
                        result['target_sha256'] = hashlib.sha256(target_fragment).hexdigest()
                        if result['target_sha256'] != expected:
                            errors.append('manifest target_sha256 does not match pinned target fragment')
                    except ReplayError as exc:
                        errors.append(str(exc))
                    try:
                        replay_fragment = fragment_bytes(replay_blob, check, label + ' replay')
                        result['replay_sha256'] = hashlib.sha256(replay_fragment).hexdigest()
                        if result['replay_sha256'] != expected:
                            errors.append('replay fragment differs from target_sha256')
                    except ReplayError as exc:
                        errors.append(str(exc))
                    result['pass'] = not errors
                    if errors:
                        result['errors'] = errors
                    fragment_results.append(result)
                    report['parity_claims']['anchored_integration_fragments'].append(label)
        report['integration_checks'] = fragment_results
        report['residual_shared_file_diffs'] = residuals

        added_results = []
        for feature in features:
            for added in feature['added_paths']:
                path = added['path']
                target_entry = git(source, 'cat-file', '-e', f'{manifest["molly_expected"]}:{path}', check=False)
                replay_blob = blob(worktree, 'HEAD', path)
                replay_digest = hashlib.sha256(replay_blob).hexdigest()
                result = {'feature': feature['id'], 'path': path, 'target_absent': target_entry.returncode != 0,
                          'replay_sha256': replay_digest, 'expected_replay_sha256': added['expected_replay_sha256'],
                          'replay_matches_evidence': replay_digest == added['expected_replay_sha256'],
                          'evidence': added['evidence'], 'tests': added['tests']}
                result['pass'] = result['target_absent'] and result['replay_matches_evidence']
                added_results.append(result)
                report['parity_claims']['target-absent-added-paths'].append(f'{feature["id"]}:{path}')
        report['added_path_checks'] = added_results

        adaptation_results = []
        adaptation_diffs = []
        for feature in features:
            for adaptation in feature['adaptation_paths']:
                path = adaptation['path']
                target_blob = blob(source, manifest['molly_expected'], path)
                replay_blob = blob(worktree, 'HEAD', path)
                target_digest = hashlib.sha256(target_blob).hexdigest()
                replay_digest = hashlib.sha256(replay_blob).hexdigest()
                diff = git(worktree, 'diff', '--no-ext-diff', '--no-color', manifest['molly_expected'], 'HEAD', '--', path, binary=True)
                diff_dir.mkdir(parents=True, exist_ok=True)
                name = hashlib.sha256((feature['id'] + '\0adaptation\0' + path).encode()).hexdigest()[:16] + '.diff'
                residual = write_residual_diff(diff_dir, name, diff.stdout)
                residual.update({'feature': feature['id'], 'path': path})
                adaptation_diffs.append(residual)
                target_ok = target_digest == adaptation['target_sha256']
                replay_ok = replay_digest == adaptation['expected_replay_sha256']
                result = {'feature': feature['id'], 'path': path, 'match': 'documented-adaptation' if target_ok and replay_ok else 'failed-adaptation',
                          'target_sha256': target_digest, 'expected_target_sha256': adaptation['target_sha256'],
                          'replay_sha256': replay_digest, 'expected_replay_sha256': adaptation['expected_replay_sha256'],
                          'target_matches_evidence': target_ok, 'replay_matches_evidence': replay_ok,
                          'target_parity': False, 'whole_file_target_parity_claimed': False,
                          'evidence': adaptation['evidence'], 'tests': adaptation['tests'],
                          'residual_diff_artifact': residual['artifact']}
                adaptation_results.append(result)
                report['parity_claims']['documented_adaptations'].append(f'{feature["id"]}:{path}')
        report['adaptation_checks'] = adaptation_results
        report['residual_adaptation_diffs'] = adaptation_diffs
        report['whitespace_check'] = git(worktree, 'diff', '--check', manifest['signal_base'], 'HEAD', check=False).output.strip()
        report['unmerged_index_entries'] = git(worktree, 'ls-files', '--unmerged').output.splitlines()
        report['conflict_markers'] = conflict_markers(worktree, changed)
        passed = (not unowned and not report['whitespace_check'] and not report['unmerged_index_entries']
                  and not report['conflict_markers']
                  and report['expected_tree_match'] is not False
                  and report['source_projection_match']
                  and all(item['pass'] for item in full_parity.values())
                  and all(item['pass'] for item in fragment_results)
                  and all(item['pass'] for item in added_results)
                  and all(item['match'] == 'documented-adaptation' for item in adaptation_results))
        if has_integrations:
            report['warnings'].append('A2-4 is revised for integration_paths: only anchored fragments were compared; residual file diffs are artifacts and whole-file parity is not claimed.')
        if has_adaptations:
            report['warnings'].append('A2-4 is revised for adaptation_paths: whole-file hashes match the documented replay adaptation and pinned target respectively; target parity is false and residual diffs are artifacts. Hash agreement is a reproducibility oracle, not semantic proof.')
        if has_added_paths:
            report['warnings'].append('Declared added_paths are expected to be absent from the pinned Molly target and are checked for target absence plus exact replay content hash.')
        report['status'] = 'PASS' if passed else 'FAIL'
    except Exception as exc:
        report['error'] = str(exc)
        if report['status'] == 'STARTED':
            report['status'] = 'ERROR'
    finally:
        args.report.write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))
    return report

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True, type=Path)
    parser.add_argument('--patches', type=Path, default=Path('patches/827'))
    parser.add_argument('--evidence', type=Path, default=Path('docs/827/parity-evidence.json'))
    parser.add_argument('--worktree', required=True, type=Path)
    parser.add_argument('--report', required=True, type=Path)
    args = parser.parse_args()
    try:
        report = run_replay(args)
    except ReplayError as exc:
        print(f'replay refused: {exc}', file=sys.stderr)
        return 2
    return 0 if report['status'] == 'PASS' else 1

if __name__ == '__main__':
    raise SystemExit(main())
