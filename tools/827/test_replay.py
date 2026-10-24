"""Focused safety checks for the #827 replay manifest and path guards."""
import gzip
import json
from pathlib import Path
import tempfile
import os
import shutil
import unittest
import subprocess
import sys

import replay
import validate
from source_tree import project_tree

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / 'patches/827/series.yaml'


class ReplaySafetyTests(unittest.TestCase):
    def test_source_projection_removes_only_declared_metadata_from_private_index(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            subprocess.run(['git', 'init', '-q', str(repo)], check=True)
            subprocess.run(['git', '-C', str(repo), 'config', 'user.email', 'test@example.invalid'], check=True)
            subprocess.run(['git', '-C', str(repo), 'config', 'user.name', 'Test'], check=True)
            (repo / 'app').mkdir()
            (repo / 'app/main.kt').write_text('app')
            subprocess.run(['git', '-C', str(repo), 'add', 'app/main.kt'], check=True)
            subprocess.run(['git', '-C', str(repo), 'commit', '-qm', 'application'], check=True)
            app_tree = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD^{tree}'], text=True).strip()
            (repo / 'docs/827').mkdir(parents=True)
            (repo / 'docs/827/report.md').write_text('metadata')
            subprocess.run(['git', '-C', str(repo), 'add', 'docs/827/report.md'], check=True)
            subprocess.run(['git', '-C', str(repo), 'commit', '-qm', 'metadata'], check=True)
            index_before = subprocess.check_output(['git', '-C', str(repo), 'write-tree'], text=True).strip()
            projected = project_tree(repo, 'HEAD', ['docs/827'])
            index_after = subprocess.check_output(['git', '-C', str(repo), 'write-tree'], text=True).strip()
            self.assertEqual(projected, app_tree)
            self.assertEqual(index_after, index_before)

    def test_residual_diff_compression_is_deterministic_and_lossless(self):
        payload = b'@@ -1 +1 @@\n-signal\n+molly\n'
        first = replay.deterministic_gzip(payload)
        second = replay.deterministic_gzip(payload)
        self.assertEqual(first, second)
        self.assertEqual(first[4:8], b'\x00\x00\x00\x00')
        self.assertEqual(gzip.decompress(first), payload)

    def test_declared_series_checksums_and_provenance(self):
        result = validate.validate(MANIFEST)
        self.assertEqual(result['status'], 'PASS')
        manifest = json.loads(MANIFEST.read_text())
        self.assertEqual(result['patch_count'], sum(len(f['patches']) for f in manifest['features']))

    def test_git_paths_reject_traversal_and_git_metadata(self):
        for unsafe in ('../outside', '/absolute', 'a/../b', '.git/config', 'a\\b'):
            with self.subTest(path=unsafe), self.assertRaises(replay.ReplayError):
                replay.validate_git_path(unsafe, 'test path')

    def test_manifest_rejects_mismatched_mailbox_provenance(self):
        data = json.loads(MANIFEST.read_text())
        data['features'][0]['patches'][0]['mailbox_commit_sha'] = '0' * 40
        with self.assertRaisesRegex(replay.ReplayError, 'mailbox commit SHA'):
            replay.validate_manifest(data, MANIFEST.parent)

    def test_manifest_rejects_parent_patch_path(self):
        data = json.loads(MANIFEST.read_text())
        data['features'][0]['patches'][0]['path'] = '../outside.patch'
        with tempfile.TemporaryDirectory() as temp:
            manifest = Path(temp) / 'series.yaml'
            manifest.write_text(json.dumps(data))
            with self.assertRaises(replay.ReplayError):
                replay.validate_manifest(data, manifest.parent)

    def test_manifest_rejects_symlinked_patch_file(self):
        data = json.loads(MANIFEST.read_text())
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'branding').mkdir()
            original = MANIFEST.parent / data['features'][0]['patches'][0]['path']
            link = root / 'branding/linked.patch'
            link.symlink_to(original)
            patch = data['features'][0]['patches'][0]
            patch['path'] = 'branding/linked.patch'
            with self.assertRaisesRegex(replay.ReplayError, 'symlink'):
                replay.validate_manifest(data, root)

    def test_manifest_rejects_changed_base_and_target_pins(self):
        for field in ('signal_base', 'molly_expected'):
            data = json.loads(MANIFEST.read_text())
            data[field] = 'b8d5375b3fb6013f7939935ce73e250b53515381'
            with self.subTest(field=field), self.assertRaisesRegex(replay.ReplayError, field):
                replay.validate_manifest(data, MANIFEST.parent)

    def test_manifest_supports_paths_required_absent_from_target(self):
        data = json.loads(MANIFEST.read_text())
        data['features'][1]['added_paths'] = [{
            'path': 'app/src/test/java/example/NewReplayTest.kt',
            'expected_replay_sha256': 'a' * 64,
            'evidence': 'Focused security regression fixture added to exercise locked-state routing invalidation.',
            'tests': ['app/src/test/java/example/NewReplayTest.kt']
        }]
        _, features = replay.validate_manifest(data, MANIFEST.parent)
        self.assertEqual(features[1]['added_paths'][0]['path'], 'app/src/test/java/example/NewReplayTest.kt')
        data['features'][1]['added_paths'][0]['expected_replay_sha256'] = 'bad'
        with self.assertRaisesRegex(replay.ReplayError, 'expected_replay_sha256'):
            replay.validate_manifest(data, MANIFEST.parent)

    def test_feature_dependency_must_precede_consumer(self):
        data = json.loads(MANIFEST.read_text())
        data['features'][0]['dependencies'] = ['unifiedpush']
        with self.assertRaisesRegex(replay.ReplayError, 'dependencies must be listed earlier'):
            replay.validate_manifest(data, MANIFEST.parent)

    def test_full_replay_works_without_identity_and_with_ambient_signing(self):
        with tempfile.TemporaryDirectory() as temp:
            temp_root = Path(temp)
            repo = temp_root / 'repo'
            repo.mkdir()
            subprocess.run(['git', 'init', '-q', str(repo)], check=True)
            # Share immutable Git objects so the fixture stays quick without copying the large source repo.
            common_dir = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse',
                                                  '--path-format=absolute', '--git-common-dir'], text=True).strip()
            objects_dir = Path(common_dir) / 'objects'
            alternates = repo / '.git/objects/info/alternates'
            alternates.parent.mkdir(parents=True, exist_ok=True)
            alternates.write_text(str(objects_dir) + '\n')
            app_commit = json.loads(MANIFEST.read_text())['expected_application_commit']
            subprocess.run(['git', '-C', str(repo), 'update-ref', 'refs/heads/source-app', app_commit], check=True)
            subprocess.run(['git', '-C', str(repo), 'symbolic-ref', 'HEAD', 'refs/heads/source-app'], check=True)
            global_config = temp_root / 'global.gitconfig'
            global_config.write_text('[commit]\n\tgpgSign = true\n[gpg]\n\tprogram = /bin/false\n')
            environment = os.environ.copy()
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
            proc = subprocess.run([sys.executable, str(ROOT / 'tools/827/replay.py'),
                                   '--repo', str(repo), '--manifest', str(MANIFEST),
                                   '--worktree', str(destination), '--report', str(report)],
                                  env=environment, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            result = json.loads(report.read_text())
            self.assertEqual(result['tree_sha'], json.loads(MANIFEST.read_text())['expected_tree_sha'])
            self.assertEqual(result['source_projection_match'], True)
            committer = subprocess.check_output(['git', '-C', str(destination), 'show', '-s',
                                                 '--format=%cn <%ce>', 'HEAD'], text=True).strip()
            self.assertEqual(committer, 'Molly Replay Tool <molly-replay-tool@example.invalid>')
            self.assertNotEqual(subprocess.run(['git', '-C', str(repo), 'config', '--get', 'user.email'],
                                               env=environment, capture_output=True).returncode, 0)
            self.assertEqual(subprocess.check_output(['git', '-C', str(repo), 'config', '--get', 'commit.gpgSign'],
                                                     env=environment, text=True).strip(), 'true')
            subprocess.run(['git', '-C', str(repo), 'worktree', 'remove', '--force', str(destination)], check=True)

    def test_replay_twice_failure_json_includes_git_am_error_tail(self):
        with tempfile.TemporaryDirectory() as temp:
            temp_root = Path(temp)
            manifest = json.loads(MANIFEST.read_text())
            for feature in manifest['features']:
                for patch in feature['patches']:
                    relative = patch['path']
                    source_patch = MANIFEST.parent / relative
                    destination = temp_root / relative
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source_patch, destination)
                    if feature['id'] == 'branding' and relative.endswith('.patch'):
                        raw = destination.read_bytes()
                        marker = raw.find(b'\n---\n')
                        self.assertGreater(marker, 0)
                        damaged = raw[:marker + len(b'\n---\n')] + b'not a unified diff\n'
                        destination.write_bytes(damaged)
                        patch['sha256'] = __import__('hashlib').sha256(damaged).hexdigest()
            manifest_path = temp_root / 'series.yaml'
            manifest_path.write_text(json.dumps(manifest))
            report = temp_root / 'replay-twice.json'
            prefix = temp_root / 'failed-worktree'
            proc = subprocess.run([sys.executable, str(ROOT / 'tools/827/replay_twice.py'),
                                   '--repo', str(ROOT), '--manifest', str(manifest_path),
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
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            subprocess.run(['git', '-C', str(ROOT), 'worktree', 'remove', '--force', str(worktree)], check=False,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    def test_existing_worktree_destination_is_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            destination = Path(temp) / 'already-there'
            destination.mkdir()
            # The CLI check is intentionally performed before git worktree add.
            self.assertTrue(destination.exists())
            with self.assertRaisesRegex(replay.ReplayError, 'REFUSE'):
                replay.run_replay(type('Args', (), {'repo': ROOT, 'manifest': MANIFEST,
                                                    'worktree': destination,
                                                    'report': Path(temp) / 'report.json'})())

    def run_for_destination(self, repo, destination, report):
        return replay.run_replay(type('Args', (), {'repo': repo, 'manifest': MANIFEST,
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
