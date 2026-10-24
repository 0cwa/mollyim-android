"""Focused safety checks for the #827 replay manifest and path guards."""
import gzip
import json
from pathlib import Path
import tempfile
import unittest

import replay
import validate

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / 'patches/827/series.yaml'


class ReplaySafetyTests(unittest.TestCase):
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
