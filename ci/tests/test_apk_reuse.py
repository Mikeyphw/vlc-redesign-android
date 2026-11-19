"""Positive and adversarial JVM-tested APK binary reuse contracts."""
from __future__ import annotations
import io
import json
from pathlib import Path
import sys
import tempfile
from unittest import mock
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import apk_reuse as ar


class ReuseTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='vlc-apk-reuse-test-')
        self.root=Path(self.temp.name)
        self.maven=self.root/'maven'
        dest=self.maven/ar.MAVEN_REL
        dest.parent.mkdir(parents=True)
        with zipfile.ZipFile(dest,'w') as z:
            z.writestr('classes.jar', b'j'*4096)
            z.writestr('AndroidManifest.xml', b'<manifest />')
        (self.maven/ar.POM_REL).write_text('<project><version>0.13.24-rd1</version></project>')
        (self.maven/ar.PROVENANCE_REL).write_text('{"origin":"verified-fixture"}')
        self.apk_dir=self.root/'built'
        self.apk_dir.mkdir()
        with zipfile.ZipFile(self.apk_dir/'vlc-debug.apk','w') as z:
            z.writestr('AndroidManifest.xml', b'manifest')
            z.writestr('classes.dex',b'dex_data')
            z.writestr('res/layout.xml',b'layout')
        self.cache=self.root/'cache'
        self.pin=mock.patch.object(ar,'source_fingerprint',return_value='0'*64)
        self.pin.start()
        self.key=ar.cache_identity(self.root,self.maven,'ubuntu24-20261111')

    def tearDown(self):
        self.pin.stop();self.temp.cleanup()

    def make(self):
        return ar.seal(self.cache,self.apk_dir,self.key)

    def test_source_fingerprint_skips_only_ci_and_docs(self):
        def e(path,hexsha):return b'100644 blob '+hexsha.encode()+b'\t'+path.encode()+b'\0'
        head=e('application/app/src/Main.kt','a'*40)
        self.assertEqual(ar.fingerprint_tree(head+e('ci/workflow_policy.py','b'*40)),ar.fingerprint_tree(head))
        self.assertEqual(ar.fingerprint_tree(head+e('docs/CI.md','b'*40)),ar.fingerprint_tree(head))
        self.assertNotEqual(ar.fingerprint_tree(head),ar.fingerprint_tree(e('application/app/src/Main.kt','c'*40)))
        self.assertNotEqual(ar.fingerprint_tree(head),ar.fingerprint_tree(head+e('build.gradle','b'*40)))

    def test_malformed_tracked_tree_refused(self):
        for source in (b'not-git\0',b'100644 blob a\t../escape\0',b'100644 blob '+'a'.encode()*40+b'\t/x\0'):
            with self.assertRaises(ar.ReuseError):ar.fingerprint_tree(source)

    def test_artifact_roundtrip_and_jvm_test_receipt(self):
        receipt=self.make()
        self.assertEqual(receipt['jvm_tests'],'passed')
        self.assertEqual(ar.verify(self.cache,self.key),receipt)
        self.assertTrue(receipt['cache_key'].startswith('vlc-debug-apk-v1-'))

    def test_modified_artifact_cannot_pass_cache(self):
        self.make()
        path=self.cache/'vlc-debug.apk'
        path.write_bytes(path.read_bytes()+b'mutated')
        with self.assertRaisesRegex(ar.ReuseError,'SHA256 mismatch'):
            ar.verify(self.cache,self.key)

    def test_source_change_invalidates_cache(self):
        self.make()
        other=json.loads(json.dumps(self.key))
        other['inputs']['source_tree_sha256']='1'*64
        with self.assertRaises(ar.ReuseError):ar.verify(self.cache,other)

    def test_maven_change_invalidates_cache(self):
        self.make()
        with zipfile.ZipFile(self.maven/ar.MAVEN_REL,'a') as z:z.writestr('resources.arsc',b'new')
        next_key=ar.cache_identity(self.root,self.maven,'ubuntu24-20261111')
        self.assertNotEqual(self.key['key'],next_key['key'])
        with self.assertRaises(ar.ReuseError):ar.verify(self.cache,next_key)

    def test_changed_pom_or_maven_receipt_invalidates_cache(self):
        self.make()
        for candidate in (ar.POM_REL,ar.PROVENANCE_REL):
            file=self.maven/candidate
            old=file.read_bytes()
            file.write_bytes(old+b'\nmodified')
            current=ar.cache_identity(self.root,self.maven,'ubuntu24-20261111')
            self.assertNotEqual(current['key'],self.key['key'])
            with self.subTest(candidate=candidate),self.assertRaises(ar.ReuseError):
                ar.verify(self.cache,current)
            file.write_bytes(old)

    def test_runner_image_drift_invalidates_cache(self):
        self.make()
        other=ar.cache_identity(self.root,self.maven,'ubuntu24-20261201')
        with self.assertRaises(ar.ReuseError):ar.verify(self.cache,other)

    def test_mismatched_receipt_and_claimed_tests_refused(self):
        self.make()
        p=ar.receipt_file(self.cache)
        record=json.loads(p.read_text());record['jvm_tests']='skipped';p.write_bytes(ar.canonical(record))
        with self.assertRaises(ar.ReuseError):ar.verify(self.cache,self.key)

    def test_added_foreign_file_refused(self):
        self.make();(self.cache/'unknown.txt').write_text('poison')
        with self.assertRaises(ar.ReuseError):ar.verify(self.cache,self.key)

    def test_symlinked_apk_refused(self):
        self.make();p=self.cache/'vlc-debug.apk';p.unlink();p.symlink_to(self.apk_dir/'vlc-debug.apk')
        with self.assertRaises(ar.ReuseError):ar.verify(self.cache,self.key)

    def test_forged_non_apk_archive_refused(self):
        src=self.apk_dir/'vlc-debug.apk'
        with zipfile.ZipFile(src,'w') as z:z.writestr('fake.txt',b'a')
        with self.assertRaises(ar.ReuseError):self.make()

    def test_missing_apk_or_cache_overwrite_refused(self):
        (self.apk_dir/'vlc-debug.apk').unlink()
        with self.assertRaises(ar.ReuseError):self.make()
        with zipfile.ZipFile(self.apk_dir/'vlc-debug.apk','w') as z:
            z.writestr('AndroidManifest.xml','manifest');z.writestr('classes.dex','dex')
        self.make()
        with self.assertRaises(ar.ReuseError):self.make()

    def test_invalid_runner_image_refused(self):
        for runner in ('', '../evil', 'unknown version', 'x'):
            with self.assertRaises(ar.ReuseError):ar.cache_identity(self.root,self.maven,runner)

if __name__=='__main__':unittest.main()
