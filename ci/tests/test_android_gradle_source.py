"""Current LibVLCJNI source-locked Gradle bootstrap, positive and negative gates."""
from __future__ import annotations

from pathlib import Path
import subprocess
import sys
from unittest import mock
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import medialibrary as ml
import prepare_android_gradle as prep
from test_medialibrary_pipeline import TempMediaFixture


class AndroidGradleSource(unittest.TestCase):
    def setUp(self):
        self.f = TempMediaFixture()
        self.lock_pins = mock.patch.object(ml, 'TRUSTED_PATCH_BLOBS', self.f.lock['patches'])
        self.lock_pins.start()
        self.pin = self.f.lock['libvlcjni_commit']
        self.f.write('settings.gradle', "include ':libvlcjni:libvlc', ':medialibrary'\n")
        self.f.write('medialibrary/build.gradle', "apply plugin: 'com.android.library'\n")
        self.dest = self.f.root / 'libvlcjni'

    def tearDown(self):
        self.lock_pins.stop()
        self.f.close()

    def create_checkout(self):
        self.f.write('libvlcjni/.git/config', '[core]\n')
        self.f.write('libvlcjni/libvlc/build.gradle', "apply plugin: 'com.android.library'\n")

    def fake_git(self, root, *args, **kwargs):
        if tuple(args) == ('rev-parse', '--show-toplevel'):
            return str(self.dest.resolve())
        if tuple(args) == ('remote', 'get-url', 'origin'):
            return prep.SOURCE_URL
        if tuple(args) == ('rev-parse', 'HEAD'):
            return self.pin
        if tuple(args) == ('status', '--porcelain=v1', '--untracked-files=no'):
            return ''
        if tuple(args[:2]) == ('-c', 'advice.detachedHead=false'):
            self.assertEqual(tuple(args[2:]), ('checkout', '--detach', self.pin))
            return ''
        self.fail('Unreviewed git command: ' + repr(args))

    def test_expected_kuchisofts_lock_matches_exact_libvlcjni_project(self):
        self.assertEqual(self.pin, '0b8dc65efb203c86a0476bc337ddd99ecf1c0ef6')
        self.assertEqual(prep.locked_commit(self.f.root), self.pin)
        self.create_checkout()
        with mock.patch.object(prep, 'git', side_effect=self.fake_git):
            self.assertEqual(prep.verify(self.f.root)['libvlcjni_commit'], self.pin)

    def test_missing_checkout_refused_not_stubbed(self):
        with self.assertRaisesRegex(prep.PreparationError, 'missing'):
            prep.verify(self.f.root)

    def test_reject_dummy_project_directory(self):
        self.f.write('libvlcjni/.git/config', '[core]\n')
        with self.assertRaisesRegex(prep.PreparationError, 'Gradle project missing'):
            prep.verify(self.f.root)

    def test_destination_symlink_refused(self):
        self.dest.symlink_to(self.f.root/'medialibrary',target_is_directory=True)
        with self.assertRaisesRegex(prep.PreparationError, 'symlink'):
            prep.verify(self.f.root)
        with self.assertRaisesRegex(prep.PreparationError, 'already exists'):
            prep.prepare(self.f.root)

    def test_origin_mismatch_refused(self):
        self.create_checkout()
        def wrong(root,*args,**kwargs):
            return 'https://evil.test/libvlcjni.git' if args == ('remote','get-url','origin') else self.fake_git(root,*args,**kwargs)
        with mock.patch.object(prep, 'git', side_effect=wrong), self.assertRaisesRegex(prep.PreparationError,'origin mismatch'):
            prep.verify(self.f.root)

    def test_floating_branch_commit_refused(self):
        self.create_checkout()
        def wrong(root,*args,**kwargs):
            return 'a'*40 if args == ('rev-parse','HEAD') else self.fake_git(root,*args,**kwargs)
        with mock.patch.object(prep, 'git', side_effect=wrong), self.assertRaisesRegex(prep.PreparationError,'locked'):
            prep.verify(self.f.root)

    def test_dirty_tracked_checkout_refused(self):
        self.create_checkout()
        def wrong(root,*args,**kwargs):
            return ' M libvlc/build.gradle' if args[:2] == ('status','--porcelain=v1') else self.fake_git(root,*args,**kwargs)
        with mock.patch.object(prep, 'git', side_effect=wrong), self.assertRaisesRegex(prep.PreparationError,'changed'):
            prep.verify(self.f.root)

    def test_nested_worktree_source_refused(self):
        self.create_checkout()
        def wrong(root,*args,**kwargs):
            return str(self.f.root) if args == ('rev-parse','--show-toplevel') else self.fake_git(root,*args,**kwargs)
        with mock.patch.object(prep, 'git', side_effect=wrong), self.assertRaisesRegex(prep.PreparationError,'boundary'):
            prep.verify(self.f.root)

    def test_source_lock_compile_sh_drift_refused(self):
        self.f.write('buildsystem/compile.sh', 'LIBVLCJNI_TESTED_HASH='+'a'*40+'\n')
        with self.assertRaisesRegex(prep.PreparationError, 'disagrees'):
            prep.locked_commit(self.f.root)

    def test_gradle_project_declaration_drift_refused(self):
        self.f.write('settings.gradle', "include ':application:app'\n")
        with self.assertRaisesRegex(prep.PreparationError, 'inclusion changed'):
            prep.locked_commit(self.f.root)

    def test_missing_media_project_refused(self):
        (self.f.root/'medialibrary/build.gradle').unlink()
        with self.assertRaisesRegex(prep.PreparationError, 'MediaLibrary'):
            prep.locked_commit(self.f.root)

    def test_exact_https_clone_and_detached_commit_checkout(self):
        commands=[]
        def fake_run(args,**kwargs):
            commands.append(list(args))
            self.assertEqual(args[:6], ['git','clone','--single-branch','--no-tags','--branch',prep.SOURCE_BRANCH])
            self.assertEqual(args[6:], [prep.SOURCE_URL,str(self.dest)])
            self.assertEqual(kwargs['env']['GIT_TERMINAL_PROMPT'],'0')
            self.create_checkout()
            return subprocess.CompletedProcess(args,0)
        with mock.patch.object(prep.subprocess,'run',side_effect=fake_run),mock.patch.object(prep,'git',side_effect=self.fake_git):
            self.assertEqual(prep.prepare(self.f.root)['libvlcjni_commit'], self.pin)
        self.assertEqual(len(commands),1)

    def test_existing_checkout_cannot_be_overwritten(self):
        self.create_checkout()
        with mock.patch.object(prep.subprocess,'run') as run, self.assertRaisesRegex(prep.PreparationError,'already exists'):
            prep.prepare(self.f.root)
        run.assert_not_called()

    def test_failed_clone_remains_failed(self):
        with mock.patch.object(prep.subprocess,'run',side_effect=subprocess.CalledProcessError(128,['git','clone'])):
            with self.assertRaises(subprocess.CalledProcessError):prep.prepare(self.f.root)


if __name__ == '__main__':
    unittest.main()
