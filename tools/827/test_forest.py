"""Hermetic tests: real format-patch/am in tiny repositories; no network or SDK."""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest

import forest


class ForestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.repo = self.home / 'repo'
        self.repo.mkdir()
        self.root = self.home / 'patches'
        self.root.mkdir()
        self.git('init', '-q')
        self.git('config', 'user.name', 'Original Author')
        self.git('config', 'user.email', 'author@example.invalid')
        (self.repo / 'common').write_text('base\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'base')
        self.base = self.git('rev-parse', 'HEAD')
        (self.root / 'base').write_text(self.base + '\n')
        self.patch_number = {}

    def git(self, *args, binary=False):
        env = os.environ.copy()
        env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)
        raw = subprocess.check_output(['git', '-C', str(self.repo), *args], env=env, stderr=subprocess.PIPE)
        return raw if binary else raw.decode().strip()

    def add_feature(self, name, parent=None, depends=(), filename=None, content=None, message=None):
        self.git('checkout', '--detach', '-q', parent or self.base)
        filename = filename or name.replace('/', '-')
        target = self.repo / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content if content is not None else (name + '\n').encode())
        self.git('add', '.')
        self.git('commit', '-qm', message or ('Add ' + name))
        commit = self.git('rev-parse', 'HEAD')
        directory = self.root / name
        directory.mkdir(parents=True, exist_ok=True)
        n = self.patch_number.get(name, 0) + 1
        self.patch_number[name] = n
        patch_name = f'{n:04d}-change.patch'
        (directory / patch_name).write_bytes(self.git('format-patch', '--binary', '--full-index', '--stdout', '-1', binary=True))
        with (directory / 'series').open('a') as stream:
            stream.write(patch_name + '\n')
        if depends:
            (directory / 'depends').write_text('\n'.join(depends) + '\n')
        return commit

    def names(self, selected=None, reverse=False):
        return [f.name for f in forest.Forest(self.root).order(selected, reverse)]

    def test_independent_siblings_and_stable_orders(self):
        self.add_feature('beta'); self.add_feature('alpha')
        self.assertEqual(self.names(), ['alpha', 'beta'])
        self.assertEqual(self.names(reverse=True), ['beta', 'alpha'])
        self.assertEqual(self.names(['beta']), ['beta'])

    def test_series_order_not_filename_sort(self):
        self.add_feature('alpha')
        self.add_feature('alpha')
        (self.root / 'alpha/series').write_text('0002-change.patch\n0001-change.patch\n')
        self.assertEqual([Path(p).name for p in forest.Forest(self.root).patches()],
                         ['0002-change.patch', '0001-change.patch'])

    def test_nested_feature_inherits_entire_parent_series(self):
        first = self.add_feature('core')
        second = self.add_feature('core', parent=first, filename='second')
        self.add_feature('core/child', parent=second)
        self.add_feature('unrelated')
        f = forest.Forest(self.root)
        self.assertEqual(self.names(['core/child']), ['core', 'core/child'])
        self.assertEqual(len(f.patches(['core/child'])), 3)
        self.assertEqual(self.names(['core']), ['core'])
        result = forest.apply(f, self.repo, self.home / 'out', ['core/child'])
        self.assertEqual(result['status'], 'PASS')

    def test_diamond_dependency_deduplicates_shared_prefix(self):
        self.add_feature('common'); self.add_feature('left', depends=['common'])
        self.add_feature('right', depends=['common']); self.add_feature('integration', depends=['left','right'])
        self.assertEqual(self.names(['integration']), ['common','left','right','integration'])

    def test_cross_tree_edge(self):
        self.add_feature('first'); self.add_feature('second', depends=['first'])
        self.assertEqual(self.names(['second']), ['first','second'])

    def test_missing_dependency_and_missing_parent(self):
        self.add_feature('one', depends=['missing'])
        with self.assertRaisesRegex(forest.ForestError, 'unknown'): forest.Forest(self.root)
        (self.root / 'one/depends').unlink()
        self.add_feature('absent/child')
        with self.assertRaisesRegex(forest.ForestError, 'unknown'): forest.Forest(self.root)

    def test_cycles_including_implicit_parent(self):
        self.add_feature('parent', depends=['parent/child'])
        self.add_feature('parent/child')
        with self.assertRaisesRegex(forest.ForestError, 'cycle'): forest.Forest(self.root)

    def test_duplicate_dependency_and_redundant_parent(self):
        self.add_feature('parent'); self.add_feature('parent/child', depends=['parent'])
        with self.assertRaisesRegex(forest.ForestError, 'implicit'): forest.Forest(self.root)
        (self.root / 'parent/child/depends').write_text('parent\nparent\n')
        with self.assertRaisesRegex(forest.ForestError, 'duplicate'): forest.Forest(self.root)

    def test_comments_blank_lines_and_unknown_selection(self):
        self.add_feature('one')
        (self.root/'one/series').write_text('# ordered series\n\n0001-change.patch # keep this patch\n')
        self.assertEqual(self.names(), ['one'])
        with self.assertRaisesRegex(forest.ForestError, 'unknown feature'): self.names(['missing'])

    def test_empty_or_duplicate_series(self):
        self.add_feature('one')
        for content in ('# nothing\n', '0001-change.patch\n0001-change.patch\n'):
            (self.root/'one/series').write_text(content)
            with self.assertRaises(forest.ForestError): forest.Forest(self.root)

    def test_unlisted_patch_and_orphan_depends(self):
        self.add_feature('one')
        stray = self.root/'one/0002-stray.patch'
        shutil.copyfile(self.root/'one/0001-change.patch', stray)
        with self.assertRaisesRegex(forest.ForestError, 'unlisted'): forest.Forest(self.root)
        stray.unlink(); (self.root/'orphan').mkdir(); (self.root/'orphan/depends').write_text('one\n')
        with self.assertRaisesRegex(forest.ForestError, 'without'): forest.Forest(self.root)

    def test_series_paths_reject_traversal_absolute_paths_and_options(self):
        self.add_feature('one')
        for name in ('../0001-outside.patch','/tmp/0001-outside.patch','--abort','a/0001-other.patch','a\\b.patch'):
            (self.root/'one/series').write_text(name + '\n')
            with self.subTest(name=name), self.assertRaises(forest.ForestError): forest.Forest(self.root)

    def test_base_requires_full_commit_id(self):
        self.add_feature('one')
        for base in ('HEAD','abc123','0'*40+'\n'+'1'*40,'../bad'):
            (self.root/'base').write_text(base+'\n')
            with self.assertRaises(forest.ForestError): forest.Forest(self.root)

    def test_symlink_root_file_directory_and_broken_link_rejected(self):
        self.add_feature('one')
        alias = self.home/'alias'; alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(forest.ForestError, 'symlink'): forest.Forest(alias)
        for target in (self.root/'one', self.root/'one/series', self.home/'missing'):
            link = self.root/'link'; link.symlink_to(target)
            with self.assertRaisesRegex(forest.ForestError, 'symlink'): forest.Forest(self.root)
            link.unlink()

    def test_mailbox_single_message_and_required_headers(self):
        self.add_feature('one')
        p = self.root/'one/0001-change.patch'; raw=p.read_bytes()
        for bad in (b'not a mailbox', raw+raw, raw.replace(b'Subject:',b'Other:')):
            p.write_bytes(bad)
            with self.assertRaises(forest.ForestError): forest.Forest(self.root)

    def test_source_provenance_is_derived_from_message_not_diff(self):
        self.add_feature('one', message='Add one\n\nSource-Commit: '+self.base,
                         content=('Source-Commit: '+ '0'*40+'\n').encode())
        f=forest.Forest(self.root)
        self.assertEqual(next(iter(f.metadata.values()))['source_commit_shas'], [self.base])

    def test_invalid_source_provenance_rejected(self):
        self.add_feature('one', message='Add one\n\nSource-Commit: HEAD')
        with self.assertRaisesRegex(forest.ForestError, 'Source-Commit'): forest.Forest(self.root)

    def test_ambient_whitespace_fix_cannot_silently_rewrite_patch_bytes(self):
        self.add_feature('one', content=b'trailing space \n')
        self.git('config', 'apply.whitespace', 'fix')
        out = self.home / 'out'
        # The final whitespace check must fail, not accept an auto-fixed patch.
        with self.assertRaisesRegex(forest.ForestError, 'trailing whitespace'):
            forest.apply(forest.Forest(self.root), self.repo, out)
        self.assertEqual((out / 'one').read_bytes(), b'trailing space \n')

    def test_apply_preserves_author_and_binary_bytes(self):
        data = bytes(range(256)) * 3
        commit = self.add_feature('binary', filename='data.bin', content=data)
        f=forest.Forest(self.root); result=forest.apply(f,self.repo,self.home/'out')
        self.assertEqual((self.home/'out/data.bin').read_bytes(),data)
        self.assertEqual(result['tree_sha'],self.git('rev-parse',commit+'^{tree}'))
        author=subprocess.check_output(['git','-C',str(self.home/'out'),'show','-s','--format=%an <%ae>'],text=True).strip()
        self.assertEqual(author,'Original Author <author@example.invalid>')

    def test_apply_twice_exact_tree_without_identity_with_ambient_signing(self):
        self.add_feature('one')
        self.git('config','--unset','user.name'); self.git('config','--unset','user.email')
        self.git('config','commit.gpgSign','true'); self.git('config','gpg.program','/bin/false')
        f=forest.Forest(self.root)
        a=forest.apply(f,self.repo,self.home/'a'); b=forest.apply(f,self.repo,self.home/'b')
        self.assertEqual(a['tree_sha'],b['tree_sha'])
        self.assertEqual(self.git('config','commit.gpgSign'),'true')

    def test_does_not_change_dirty_source_head_index_or_working_files(self):
        self.add_feature('one'); before=self.git('rev-parse','HEAD')
        (self.repo/'common').write_text('staged\n'); self.git('add','common')
        (self.repo/'untracked').write_text('keep me\n')
        index=self.git('write-tree'); status=self.git('status','--porcelain')
        forest.apply(forest.Forest(self.root),self.repo,self.home/'out')
        self.assertEqual(self.git('rev-parse','HEAD'),before)
        self.assertEqual(self.git('write-tree'),index)
        self.assertEqual(self.git('status','--porcelain'),status)

    def test_destination_guards(self):
        self.add_feature('one'); f=forest.Forest(self.root)
        existing=self.home/'existing';existing.mkdir();(existing/'keep').write_text('keep')
        alias=self.home/'alias';alias.symlink_to(self.home/'missing')
        for dest in (existing,alias,self.repo/'inside',self.home/'x/../outside'):
            with self.subTest(dest=dest),self.assertRaisesRegex(forest.ForestError,'REFUSE'):
                forest.apply(f,self.repo,dest)
        self.assertEqual((existing/'keep').read_text(),'keep')

    def test_patch_changed_after_validation_refused(self):
        self.add_feature('one'); f=forest.Forest(self.root)
        p=self.root/'one/0001-change.patch';p.write_bytes(p.read_bytes()+b'changed\n')
        with self.assertRaisesRegex(forest.ForestError,'changed after validation'):
            forest.apply(f,self.repo,self.home/'out')

    def test_strict_conflict_leaves_am_state_for_inspection(self):
        self.add_feature('alpha',filename='common',content=b'alpha\n')
        self.add_feature('beta',filename='common',content=b'beta\n')
        self.git('config','am.threeWay','true'); self.git('config','rerere.enabled','true')
        out=self.home/'out'
        with self.assertRaisesRegex(forest.ForestError,'Worktree preserved'):
            forest.apply(forest.Forest(self.root),self.repo,out)
        shown=subprocess.run(['git','-C',str(out),'am','--show-current-patch'],capture_output=True)
        self.assertEqual(shown.returncode,0)
        self.assertEqual((out/'common').read_text(),'alpha\n')

    def test_verify_isolated_closures_and_reverse_full_order(self):
        self.add_feature('alpha'); self.add_feature('beta'); self.add_feature('beta/child')
        result=forest.verify(forest.Forest(self.root),self.repo)
        self.assertEqual(len(result['closures']),3)
        self.assertEqual(result['full_orders'][0],result['full_orders'][1])
        self.assertEqual(self.git('worktree','list','--porcelain').count('worktree '),1)

    def test_verify_detects_hidden_dependency_and_cleans_own_worktrees(self):
        first=self.add_feature('alpha',filename='common',content=b'alpha\n')
        self.add_feature('beta',parent=first,filename='common',content=b'beta\n')
        with self.assertRaises(forest.ForestError): forest.verify(forest.Forest(self.root),self.repo)
        self.assertEqual(self.git('worktree','list','--porcelain').count('worktree '),1)
        (self.root/'beta/depends').write_text('alpha\n')
        self.assertEqual(forest.verify(forest.Forest(self.root),self.repo)['status'],'PASS')

    def test_carrier_state_cannot_enter_release(self):
        self.add_feature('one',filename='.hangar/state',content=b'carrier\n')
        with self.assertRaisesRegex(forest.ForestError,'hangar'):
            forest.apply(forest.Forest(self.root),self.repo,self.home/'out')

    def test_real_repository_patch_catalog_is_complete(self):
        root=Path(__file__).resolve().parents[2]/'patches/827'
        if not root.exists(): self.skipTest('no checkout patch fixture')
        f=forest.Forest(root)
        self.assertEqual(len(f.patches()),23)
        self.assertEqual(f.features['build-validation'].dependencies,('unifiedpush',))


if __name__ == '__main__':
    unittest.main()
