"""Safety checks for #827 parity evidence and replay (full Git history required)."""
import gzip
import json
from pathlib import Path
import tempfile
import os
import shutil
import unittest
from unittest import mock
import subprocess
import sys

from forest import clean_git_env
import replay
import validate
from check_resource_parity import verify_fixture_sources, AAPT_EQUIVALENCE
from source_tree import project_tree

ROOT = Path(__file__).resolve().parents[2]
PATCHES = ROOT / 'patches/827'
EVIDENCE = ROOT / 'docs/827/parity-evidence.json'

def inputs():
    return replay.load_inputs(PATCHES, EVIDENCE)


class ReplayGitEnvironmentTests(unittest.TestCase):
    @staticmethod
    def git(repo, *args):
        env = clean_git_env()
        env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)
        return subprocess.check_output(
            ['git', '-C', str(repo), '-c', 'core.hooksPath=/dev/null',
             '-c', 'commit.gpgSign=false', '-c', 'user.name=Replay Test',
             '-c', 'user.email=replay-test@example.invalid', *args],
            env=env, text=True, stderr=subprocess.PIPE).strip()

    def make_repo(self, repo, marker):
        repo.mkdir()
        self.git(repo, 'init', '-q')
        (repo / 'marker').write_text(marker)
        self.git(repo, 'add', 'marker')
        self.git(repo, 'commit', '-qm', marker)
        return self.git(repo, 'rev-parse', 'HEAD')

    def test_git_ignores_locations_in_inherited_and_explicit_environments(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            caller, target = root / 'caller', root / 'target'
            caller_head = self.make_repo(caller, 'caller')
            target_head = self.make_repo(target, 'target')
            (caller / 'marker').write_text('staged caller change')
            self.git(caller, 'add', 'marker')
            (caller / 'marker').write_text('unstaged caller change')
            index_before = (caller / '.git/index').read_bytes()
            global_config = root / 'global.gitconfig'
            global_config.write_text('[test]\n\tpreserved = yes\n')
            environment = clean_git_env()
            environment.update({
                'GIT_DIR': str(caller / '.git'), 'GIT_WORK_TREE': str(caller),
                'GIT_COMMON_DIR': str(caller / '.git'),
                'GIT_INDEX_FILE': str(caller / '.git/index'),
                'GIT_OBJECT_DIRECTORY': str(caller / '.git/objects'),
                'GIT_ALTERNATE_OBJECT_DIRECTORIES': str(caller / '.git/objects'),
                'GIT_PREFIX': 'caller/', 'GIT_NAMESPACE': 'caller',
                'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': str(global_config),
                'GIT_LFS_SKIP_SMUDGE': '1',
            })
            original = environment.copy()
            for explicit in (False, True):
                with self.subTest(explicit=explicit):
                    with mock.patch.dict(os.environ, environment, clear=True):
                        kwargs = {'env': environment} if explicit else {}
                        self.assertEqual(replay.git(target, 'cat-file', '-t', target_head, **kwargs).output.strip(),
                                         'commit')
                        self.assertEqual(replay.git(target, 'rev-parse', '--show-toplevel', **kwargs).output.strip(),
                                         str(target))
                        self.assertEqual(replay.git(target, 'config', '--get', 'test.preserved', **kwargs).output.strip(),
                                         'yes')
                        (target / 'marker').write_text(f'target change {explicit}')
                        replay.git(target, 'add', 'marker', **kwargs)
                        self.assertEqual(dict(os.environ), original)
                    self.assertEqual(environment, original)
                    self.assertEqual(self.git(target, 'show', ':marker'), f'target change {explicit}')
                    self.assertEqual(self.git(caller, 'rev-parse', 'HEAD'), caller_head)
                    self.assertEqual((caller / '.git/index').read_bytes(), index_before)
                    self.assertEqual((caller / 'marker').read_text(), 'unstaged caller change')


class ReplaySafetyTests(unittest.TestCase):
    def test_aapt2_fixtures_are_bound_to_source_blobs(self):
        target = (ROOT / AAPT_EQUIVALENCE['target_fixture']).read_bytes()
        candidate = (ROOT / AAPT_EQUIVALENCE['candidate_fixture']).read_bytes()
        hashes = verify_fixture_sources(ROOT, target, candidate)
        self.assertEqual(hashes['target'], AAPT_EQUIVALENCE['target_source_sha256'])
        self.assertEqual(hashes['candidate'], AAPT_EQUIVALENCE['candidate_source_sha256'])
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            for key in ('target_fixture', 'candidate_fixture'):
                destination = repo / AAPT_EQUIVALENCE[key]
                destination.parent.mkdir(parents=True, exist_ok=True)
                source = (ROOT / AAPT_EQUIVALENCE[key]).read_bytes()
                destination.write_bytes(source + b'<!-- modified fixture -->')
            with self.assertRaisesRegex(ValueError, 'not byte-identical'):
                verify_fixture_sources(repo, target, candidate)

    def test_source_projection_removes_only_declared_metadata_from_private_index(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            subprocess.run(['git', 'init', '-q', str(repo)], check=True, env=clean_git_env())
            subprocess.run(['git', '-C', str(repo), 'config', 'user.email', 'test@example.invalid'], check=True, env=clean_git_env())
            subprocess.run(['git', '-C', str(repo), 'config', 'user.name', 'Test'], check=True, env=clean_git_env())
            (repo / 'app').mkdir()
            (repo / 'app/main.kt').write_text('app')
            subprocess.run(['git', '-C', str(repo), 'add', 'app/main.kt'], check=True, env=clean_git_env())
            subprocess.run(['git', '-C', str(repo), 'commit', '-qm', 'application'], check=True, env=clean_git_env())
            app_tree = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD^{tree}'], text=True, env=clean_git_env()).strip()
            (repo / 'docs/827').mkdir(parents=True)
            (repo / 'docs/827/report.md').write_text('metadata')
            subprocess.run(['git', '-C', str(repo), 'add', 'docs/827/report.md'], check=True, env=clean_git_env())
            subprocess.run(['git', '-C', str(repo), 'commit', '-qm', 'metadata'], check=True, env=clean_git_env())
            head_before = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'],
                                                  text=True, env=clean_git_env()).strip()
            (repo / 'app/main.kt').write_text('staged app change')
            subprocess.run(['git', '-C', str(repo), 'add', 'app/main.kt'], check=True, env=clean_git_env())
            (repo / 'app/main.kt').write_text('unstaged app change')
            index_before = subprocess.check_output(['git', '-C', str(repo), 'write-tree'], text=True, env=clean_git_env()).strip()
            index_bytes = (repo / '.git/index').read_bytes()
            with mock.patch.dict(os.environ, {'GIT_DIR': str(repo / '.git'), 'GIT_WORK_TREE': str(repo),
                                             'GIT_INDEX_FILE': str(repo / '.git/index')}):
                projected = project_tree(repo, 'HEAD', ['docs/827'])
            self.assertEqual((repo / '.git/index').read_bytes(), index_bytes)
            index_after = subprocess.check_output(['git', '-C', str(repo), 'write-tree'], text=True, env=clean_git_env()).strip()
            self.assertEqual(projected, app_tree)
            self.assertEqual(index_after, index_before)
            self.assertEqual(subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'],
                                                     text=True, env=clean_git_env()).strip(), head_before)
            self.assertEqual((repo / 'app/main.kt').read_text(), 'unstaged app change')

    def test_residual_diff_compression_is_deterministic_and_lossless(self):
        payload = b'@@ -1 +1 @@\n-signal\n+molly\n'
        first = replay.deterministic_gzip(payload)
        second = replay.deterministic_gzip(payload)
        self.assertEqual(first, second)
        self.assertEqual(first[4:8], b'\x00\x00\x00\x00')
        self.assertEqual(gzip.decompress(first), payload)

    def test_declared_series_checksums_and_provenance(self):
        result = validate.validate(PATCHES, ROOT, EVIDENCE)
        self.assertEqual(result['status'], 'PASS')
        manifest = inputs()
        self.assertEqual(result['patch_count'], sum(len(f['patches']) for f in manifest['features']))

    def test_git_paths_reject_traversal_and_git_metadata(self):
        for unsafe in ('../outside', '/absolute', 'a/../b', '.git/config', 'a\\b'):
            with self.subTest(path=unsafe), self.assertRaises(replay.ReplayError):
                replay.validate_git_path(unsafe, 'test path')

    def test_evidence_cannot_override_patch_metadata(self):
        data = json.loads(EVIDENCE.read_text())
        for key in ('patches', 'dependencies'):
            data['features'][0][key] = []
            with tempfile.TemporaryDirectory() as temp:
                path = Path(temp) / 'evidence.json'
                path.write_text(json.dumps(data))
                with self.assertRaisesRegex(replay.ReplayError, 'unknown feature evidence'):
                    replay.load_inputs(PATCHES, path)
            del data['features'][0][key]

    def test_evidence_must_cover_exactly_the_live_features(self):
        data = json.loads(EVIDENCE.read_text())
        for entries in (data['features'][:-1], data['features'] + [data['features'][0]]):
            with tempfile.TemporaryDirectory() as temp:
                path = Path(temp) / 'evidence.json'
                path.write_text(json.dumps({**data, 'features': entries}))
                with self.assertRaisesRegex(replay.ReplayError, 'exactly once'):
                    replay.load_inputs(PATCHES, path)

    def test_digest_binds_order_topology_patch_bytes_and_assertions(self):
        original = inputs()
        digest = replay.audit_digest(original)
        for mutate in (lambda d: d['features'][1]['patches'].reverse(),
                       lambda d: d['features'][1]['dependencies'].append('branding'),
                       lambda d: d['features'][0]['patches'][0].update(sha256='0'*64),
                       lambda d: d.update(expected_tree_sha='0'*40)):
            data = json.loads(json.dumps(original))
            mutate(data)
            self.assertNotEqual(replay.audit_digest(data), digest)

    def test_inventory_digest_is_current(self):
        import csv
        import hashlib
        inventory = ROOT / 'reports/827/inventory'
        ledger = inventory / 'current-series-owned.tsv'
        with ledger.open() as stream:
            rows = list(csv.DictReader(stream, delimiter='\t'))
        self.assertTrue(rows)
        self.assertEqual({r['inputs_sha256'] for r in rows}, {replay.audit_digest(inputs())})
        summary = json.loads((inventory / 'summary.json').read_text())
        self.assertEqual(summary['selected_boundary']['live_manifest_ledger_sha256'],
                         hashlib.sha256(ledger.read_bytes()).hexdigest())

    def test_evidence_rejects_changed_base_and_target_pins(self):
        for field in ('signal_base', 'molly_expected'):
            data = inputs()
            data[field] = 'b8d5375b3fb6013f7939935ce73e250b53515381'
            with self.subTest(field=field), self.assertRaisesRegex(replay.ReplayError, field):
                replay.validate_evidence(data, PATCHES)

    def test_evidence_supports_paths_required_absent_from_target(self):
        data = inputs()
        data['features'][1]['added_paths'] = [{
            'path': 'app/src/test/java/example/NewReplayTest.kt',
            'expected_replay_sha256': 'a' * 64,
            'evidence': 'Focused security regression fixture added to exercise locked-state routing invalidation.',
            'tests': ['app/src/test/java/example/NewReplayTest.kt']
        }]
        _, features = replay.validate_evidence(data, PATCHES)
        self.assertEqual(features[1]['added_paths'][0]['path'], 'app/src/test/java/example/NewReplayTest.kt')
        data['features'][1]['added_paths'][0]['expected_replay_sha256'] = 'bad'
        with self.assertRaisesRegex(replay.ReplayError, 'expected_replay_sha256'):
            replay.validate_evidence(data, PATCHES)

    def test_feature_dependency_must_precede_consumer(self):
        data = inputs()
        data['features'][0]['dependencies'] = ['unifiedpush']
        with self.assertRaisesRegex(replay.ReplayError, 'dependencies must be listed earlier'):
            replay.validate_evidence(data, PATCHES)

    def test_full_replay_works_without_identity_and_with_ambient_signing(self):
        with tempfile.TemporaryDirectory() as temp:
            temp_root = Path(temp)
            repo = temp_root / 'repo'
            repo.mkdir()
            subprocess.run(['git', 'init', '-q', str(repo)], check=True, env=clean_git_env())
            # Share immutable Git objects so the fixture stays quick without copying the large source repo.
            common_dir = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse',
                                                  '--path-format=absolute', '--git-common-dir'], text=True, env=clean_git_env()).strip()
            objects_dir = Path(common_dir) / 'objects'
            alternates = repo / '.git/objects/info/alternates'
            alternates.parent.mkdir(parents=True, exist_ok=True)
            alternates.write_text(str(objects_dir) + '\n')
            app_commit = inputs()['expected_application_commit']
            subprocess.run(['git', '-C', str(repo), 'update-ref', 'refs/heads/source-app', app_commit], check=True, env=clean_git_env())
            subprocess.run(['git', '-C', str(repo), 'symbolic-ref', 'HEAD', 'refs/heads/source-app'], check=True, env=clean_git_env())
            subprocess.run(['git', '-C', str(repo), 'read-tree', app_commit], check=True, env=clean_git_env())
            index_before = (repo / '.git/index').read_bytes()
            (repo / 'source-note').write_text('leave the source checkout alone')
            global_config = temp_root / 'global.gitconfig'
            global_config.write_text('[commit]\n\tgpgSign = true\n[gpg]\n\tprogram = /bin/false\n')
            environment = clean_git_env()
            environment.update({'HOME': str(temp_root / 'home'), 'GIT_CONFIG_GLOBAL': str(global_config),
                                'GIT_CONFIG_NOSYSTEM': '1'})
            for key in ('GIT_AUTHOR_NAME', 'GIT_AUTHOR_EMAIL', 'GIT_AUTHOR_DATE',
                        'GIT_COMMITTER_NAME', 'GIT_COMMITTER_EMAIL', 'GIT_COMMITTER_DATE'):
                environment.pop(key, None)
            (temp_root / 'home').mkdir()
            self.assertNotEqual(subprocess.run(['git', '-C', str(repo), 'config', '--get', 'user.email'],
                                               env=environment, capture_output=True).returncode, 0)
            self.assertEqual(subprocess.check_output(['git', '-C', str(repo), 'config', '--get', 'commit.gpgSign'],
                                                     env=environment, text=True).strip(), 'true')
            destination = temp_root / 'replayed'
            report = temp_root / 'replay-report.json'
            environment.update({'GIT_DIR': str(repo / '.git'), 'GIT_WORK_TREE': str(repo),
                                'GIT_COMMON_DIR': str(repo / '.git'),
                                'GIT_INDEX_FILE': str(repo / '.git/index'),
                                'GIT_OBJECT_DIRECTORY': str(repo / '.git/objects')})
            proc = subprocess.run([sys.executable, str(ROOT / 'tools/827/replay.py'),
                                   '--repo', str(repo), '--patches', str(PATCHES), '--evidence', str(EVIDENCE),
                                   '--worktree', str(destination), '--report', str(report)],
                                  env=environment, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            result = json.loads(report.read_text())
            self.assertEqual(result['tree_sha'], inputs()['expected_tree_sha'])
            self.assertEqual(result['source_projection_match'], True)
            self.assertEqual(subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'],
                                                     text=True, env=clean_git_env()).strip(), app_commit)
            self.assertEqual((repo / '.git/index').read_bytes(), index_before)
            self.assertEqual((repo / 'source-note').read_text(), 'leave the source checkout alone')
            committer = subprocess.check_output(['git', '-C', str(destination), 'show', '-s',
                                                 '--format=%cn <%ce>', 'HEAD'], text=True, env=clean_git_env()).strip()
            self.assertEqual(committer, 'Molly Replay Tool <molly-replay-tool@example.invalid>')
            self.assertNotEqual(subprocess.run(['git', '-C', str(repo), 'config', '--get', 'user.email'],
                                               env=clean_git_env(environment), capture_output=True).returncode, 0)
            self.assertEqual(subprocess.check_output(['git', '-C', str(repo), 'config', '--get', 'commit.gpgSign'],
                                                     env=clean_git_env(environment), text=True).strip(), 'true')
            subprocess.run(['git', '-C', str(repo), 'worktree', 'remove', '--force', str(destination)], check=True, env=clean_git_env())

    def test_full_replay_supports_nested_features_and_safe_log_names(self):
        with tempfile.TemporaryDirectory() as temp:
            temp_root = Path(temp)
            patches = temp_root / 'patches'
            shutil.copytree(PATCHES, patches)
            (patches / 'branding').rename(patches / 'unifiedpush/branding')
            evidence = json.loads(EVIDENCE.read_text())
            next(f for f in evidence['features'] if f['id'] == 'branding')['id'] = 'unifiedpush/branding'
            evidence_path = temp_root / 'evidence.json'
            evidence_path.write_text(json.dumps(evidence))
            report = temp_root / 'nested.json'
            destination = temp_root / 'replayed'
            try:
                proc = subprocess.run([sys.executable, str(ROOT / 'tools/827/replay.py'),
                                       '--repo', str(ROOT), '--patches', str(patches),
                                       '--evidence', str(evidence_path), '--worktree', str(destination),
                                       '--report', str(report)], capture_output=True, text=True)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                self.assertEqual(json.loads(report.read_text())['tree_sha'], evidence['expected_tree_sha'])
                self.assertTrue((temp_root / 'nested-logs/unifiedpush_branding-01.git-am.log').is_file())
            finally:
                if destination.exists():
                    subprocess.run(['git', '-C', str(ROOT), 'worktree', 'remove', '--force', str(destination)],
                                   check=True, capture_output=True, env=clean_git_env())

    def test_replay_twice_failure_json_includes_git_am_error_tail(self):
        with tempfile.TemporaryDirectory() as temp:
            temp_root = Path(temp)
            patch_root = temp_root / 'patches'
            shutil.copytree(PATCHES, patch_root)
            destination = next((patch_root / 'branding').glob('*.patch'))
            raw = destination.read_bytes()
            marker = raw.find(b'\ndiff --git ')
            self.assertGreater(marker, 0)
            damaged = raw[:marker] + (b'\ndiff --git a/NO-SUCH-FILE b/NO-SUCH-FILE\n'
                                      b'--- a/NO-SUCH-FILE\n+++ b/NO-SUCH-FILE\n'
                                      b'@@ -1 +1 @@\n-missing\n+new\n')
            destination.write_bytes(damaged)
            report = temp_root / 'replay-twice.json'
            prefix = temp_root / 'failed-worktree'
            proc = subprocess.run([sys.executable, str(ROOT / 'tools/827/replay_twice.py'),
                                   '--repo', str(ROOT), '--patches', str(patch_root), '--evidence', str(EVIDENCE),
                                   '--worktree-prefix', str(prefix), '--report', str(report)],
                                  capture_output=True, text=True)
            self.assertNotEqual(proc.returncode, 0)
            output = json.loads(proc.stdout)
            self.assertEqual(output['status'], 'FAIL')
            run = output['runs'][0]
            self.assertEqual(run['status'], 'PATCH_FAILED')
            self.assertIn('Patch failed', run['error'])
            self.assertTrue(run['git_am_failure']['log_tail'])
            tail = '\n'.join(run['git_am_failure']['log_tail']).lower()
            self.assertTrue('error:' in tail or 'fatal:' in tail)
            self.assertEqual(json.loads(report.read_text()), output)
            child = json.loads(Path(run['report']).read_text())
            worktree = Path(child['worktree'])
            subprocess.run(['git', '-C', str(worktree), 'am', '--abort'], check=False,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=clean_git_env())
            subprocess.run(['git', '-C', str(ROOT), 'worktree', 'remove', '--force', str(worktree)], check=False,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=clean_git_env())

    def test_existing_worktree_destination_is_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / 'already-there'
            destination.mkdir()
            # The CLI check is intentionally performed before git worktree add.
            self.assertTrue(destination.exists())
            with self.assertRaisesRegex(replay.ReplayError, 'REFUSE'):
                replay.run_replay(type('Args', (), {'repo': ROOT, 'patches': PATCHES, 'evidence': EVIDENCE,
                                                    'worktree': destination,
                                                    'report': Path(temp) / 'report.json'})())

    def run_for_destination(self, repo, destination, report):
        return replay.run_replay(type('Args', (), {'repo': repo, 'patches': PATCHES, 'evidence': EVIDENCE,
                                                   'worktree': destination, 'report': report})())

    def test_ordinary_destination_inside_primary_checkout_is_refused(self):
        destination = ROOT / '.827-test-destination-must-not-exist'
        self.assertFalse(destination.exists())
        with tempfile.TemporaryDirectory() as temp, self.assertRaisesRegex(replay.ReplayError, 'inside source'):
            self.run_for_destination(ROOT, destination, Path(temp) / 'report.json')

    def test_symlinked_parent_resolving_inside_primary_checkout_is_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            alias = Path(temp) / 'inside'
            alias.symlink_to(ROOT, target_is_directory=True)
            with self.assertRaisesRegex(replay.ReplayError, 'symlink component'):
                self.run_for_destination(ROOT, alias / 'child', Path(temp) / 'report.json')

    def test_symlinked_parent_resolving_outside_checkout_is_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            outside = Path(temp) / 'outside'
            outside.mkdir()
            alias = Path(temp) / 'outside-link'
            alias.symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(replay.ReplayError, 'symlink component'):
                self.run_for_destination(ROOT, alias / 'child', Path(temp) / 'report.json')

    def test_leaf_and_dangling_symlinks_are_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            for name, dangling in [('leaf', False), ('dangling', True)]:
                link = Path(temp) / name
                target = Path(temp) / (name + '-target')
                if not dangling:
                    target.mkdir()
                link.symlink_to(target, target_is_directory=True)
                self.assertTrue(link.exists() or link.is_symlink())
                with self.subTest(name=name), self.assertRaisesRegex(replay.ReplayError, 'symlink component|destination exists'):
                    self.run_for_destination(ROOT, link, Path(temp) / f'{name}-report.json')

    def test_worktree_parent_traversal_is_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(replay.ReplayError, 'parent traversal'):
                self.run_for_destination(ROOT, Path(temp) / '..' / 'outside', Path(temp) / 'report.json')


if __name__ == '__main__':
    unittest.main()
