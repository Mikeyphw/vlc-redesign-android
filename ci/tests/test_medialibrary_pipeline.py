"""Host-independent positive and adversarial patched native MediaLibrary tests."""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
from unittest import mock
import shutil
import struct
import sys
import tempfile
import unittest
import zipfile

CI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CI_ROOT))
import medialibrary as ml


class TempMediaFixture:
    """Minimal KuchiSofts source fixture with *synthetic* native ELF libraries."""
    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='vlc-ml-test-')
        self.root = Path(self.tmp.name)
        self.native_cache = self.root/'native'
        self.maven = self.root/'maven'
        self.images = {}
        self.lock = json.loads((CI_ROOT/'medialibrary.lock.json').read_text())
        for name in self.lock['patches']:
            source = self.root/name
            source.parent.mkdir(parents=True,exist_ok=True)
            blob = (name + ' fixture patch\n').encode()
            source.write_bytes(blob)
            self.lock['patches'][name] = ml.git_blob(blob)
        self.write('ci/medialibrary.lock.json', ml.json_bytes(self.lock))
        self.write('ci/build_medialibrary_abi.sh', (CI_ROOT/'build_medialibrary_abi.sh').read_bytes())
        self.write('buildsystem/compile.sh', 'LIBVLCJNI_TESTED_HASH='+self.lock['libvlcjni_commit']+'\n')
        self.write('buildsystem/compile-medialibrary.sh', 'MEDIALIBRARY_HASH='+self.lock['medialibrary_commit']+'\ngit clone http://code.videolan.org/videolan/medialibrary.git\n')
        self.write('build.gradle', "medialibraryVersion = (vlcMajorVersion == 3 ? '0.13.24-rd1' : '0.13.22-vlc4')\nSystem.getenv('RD_MAVEN')\n")
        self.write('application/vlc-android/build.gradle', 'debugApi "org.videolan.android:medialibrary-all:$rootProject.ext.medialibraryVersion"\n')
        for abi in ml.ABIS:
            self.images[abi] = self.lock['images'][abi].split(':',1)[0] + '@sha256:' + 'a'*64

    def write(self, name, content):
        target = self.root/name
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(content.encode() if isinstance(content,str) else content)

    def elf(self, abi, marker: bytes=b'native'):
        bits, machine = ml.ABIS[abi]
        data = bytearray(128)
        data[:4] = b'\x7fELF'
        data[4] = bits
        data[5] = 1
        struct.pack_into('<H', data, 16, 3)
        struct.pack_into('<H', data, 18, machine)
        return bytes(data) + marker

    def collect(self):
        for abi in ml.ABIS:
            binary = self.root / ('input-' + abi + '.so')
            binary.write_bytes(self.elf(abi))
            ml.collect_abi(self.native_cache, abi, binary, self.images[abi], root=self.root)

    def aar(self, missing=(), duplicate=False):
        data = io.BytesIO()
        with zipfile.ZipFile(data, 'w') as z:
            z.writestr('jni/', b'')
            z.writestr('jni/arm64-v8a/', b'')
            z.writestr('AndroidManifest.xml','<manifest/>')
            z.writestr('classes.jar','old-java-classes')
            z.writestr('jni/arm64-v8a/libc++_shared.so','unchanged-cxx')
            for abi in ml.ABIS:
                if abi not in missing:
                    z.writestr(f'jni/{abi}/libmla.so',self.elf(abi,b'original'))
                    if duplicate and abi == 'x86':
                        z.writestr('jni/x86/libmla.so',self.elf(abi,b'duplicate'))
        return data.getvalue()

    def pom(self):
        return b'<project><modelVersion>4.0.0</modelVersion><groupId>org.videolan.android</groupId><artifactId>medialibrary-all</artifactId><version>0.13.24</version></project>'

    def official(self):
        return {'aar': self.aar(), 'pom': self.pom()}

    def close(self):
        self.tmp.cleanup()


class NativeMediaContracts(unittest.TestCase):
    def setUp(self):
        self.f = TempMediaFixture()
        self.pin_patch = mock.patch.object(ml,'TRUSTED_PATCH_BLOBS',self.f.lock['patches'])
        self.pin_patch.start()

    def tearDown(self):
        self.pin_patch.stop()
        self.f.close()

    def test_source_lock_and_upstream_pins(self):
        self.assertEqual(ml.check_source(self.f.root), self.f.lock)

    def test_media_patch_tampering_is_fatal(self):
        path = self.f.root/next(iter(self.f.lock['patches']))
        path.write_bytes(b'bad patch')
        with self.assertRaisesRegex(ml.MediaContractError,'patch drift'):
            ml.check_source(self.f.root)

    def test_source_hash_drift_is_fatal(self):
        path = self.f.root/'buildsystem/compile-medialibrary.sh'
        path.write_text('MEDIALIBRARY_HASH=deadbeef\n')
        with self.assertRaises(ml.MediaContractError): ml.check_source(self.f.root)

    def test_missing_https_rewrite_is_fatal(self):
        p = self.f.root/'ci/build_medialibrary_abi.sh'
        p.write_text('echo no-tls-upgrade\n')
        with self.assertRaises(ml.MediaContractError): ml.check_source(self.f.root)

    def test_abi_binary_receipt_and_cache_roundtrip(self):
        self.f.collect()
        for abi in ml.ABIS:
            receipt=ml.validate_abi(self.f.native_cache,abi,compiler_digest=self.f.images[abi],root=self.f.root)
            self.assertEqual(receipt['library_sha256'],ml.sha(self.f.elf(abi)))
            self.assertEqual(receipt['abi'],abi)

    def test_wrong_architecture_is_blocked(self):
        src=self.f.root/'wrong.so';src.write_bytes(self.f.elf('x86'))
        with self.assertRaisesRegex(ml.MediaContractError, 'ELF'):
            ml.collect_abi(self.f.native_cache,'arm64-v8a',src,self.f.images['arm64-v8a'],root=self.f.root)

    def test_replaced_cache_binary_is_blocked(self):
        self.f.collect()
        path=ml.abi_location(self.f.native_cache,'arm64-v8a')/'libmla.so'
        path.write_bytes(self.f.elf('arm64-v8a',b'evil'))
        with self.assertRaisesRegex(ml.MediaContractError,'receipt'):
            ml.validate_abi(self.f.native_cache,'arm64-v8a',root=self.f.root)

    def test_cache_container_digest_mismatch_is_blocked(self):
        self.f.collect()
        with self.assertRaises(ml.MediaContractError):
            ml.validate_abi(self.f.native_cache,'x86',compiler_digest=self.f.images['x86'].replace('aaaa','bbbb'),root=self.f.root)

    def test_already_collected_abi_is_not_overwritten(self):
        self.f.collect()
        src=self.f.root/'input-x86.so'
        with self.assertRaisesRegex(ml.MediaContractError,'overwrite'):
            ml.collect_abi(self.f.native_cache,'x86',src,self.f.images['x86'],root=self.f.root)

    def test_deterministic_patched_aar_and_unmodified_java(self):
        self.f.collect()
        baseline=self.f.official()
        meta=ml.package_maven(self.f.native_cache,self.f.maven,baseline,root=self.f.root)
        self.assertEqual(meta['coordinate'],'org.videolan.android:medialibrary-all:0.13.24-rd1')
        ml.verify_maven(self.f.native_cache,self.f.maven,root=self.f.root)
        path=ml.receipt_dir(self.f.maven,self.f.lock)/'medialibrary-all-0.13.24-rd1.aar'
        with zipfile.ZipFile(path) as packed, zipfile.ZipFile(io.BytesIO(baseline['aar'])) as official:
            self.assertEqual(packed.read('classes.jar'),official.read('classes.jar'))
            self.assertEqual(packed.read('jni/arm64-v8a/libc++_shared.so'),official.read('jni/arm64-v8a/libc++_shared.so'))
            for abi in ml.ABIS:
                self.assertEqual(packed.read(f'jni/{abi}/libmla.so'),self.f.elf(abi))
            self.assertEqual(packed.namelist(),sorted(packed.namelist()))

    def test_missing_official_abi_slot_fails_closed(self):
        self.f.collect()
        with self.assertRaisesRegex(ml.MediaContractError,'four expected'):
            ml.package_maven(self.f.native_cache,self.f.maven,{'aar':self.f.aar(missing=['x86']), 'pom':self.f.pom()},root=self.f.root)

    def test_duplicate_official_abi_slot_fails_closed(self):
        self.f.collect()
        with self.assertWarns(UserWarning):
            raw=self.f.aar(duplicate=True)
        with self.assertRaisesRegex(ml.MediaContractError,'duplicate'):
            ml.package_maven(self.f.native_cache,self.f.maven,{'aar':raw,'pom':self.f.pom()},root=self.f.root)

    def test_wrong_pom_version_fails_closed(self):
        self.f.collect()
        with self.assertRaisesRegex(ml.MediaContractError,'POM'):
            ml.package_maven(self.f.native_cache,self.f.maven,{'aar':self.f.aar(), 'pom':self.f.pom().replace(b'0.13.24',b'0.13.23')},root=self.f.root)

    def test_tampered_package_rejected_before_gradle(self):
        self.f.collect()
        ml.package_maven(self.f.native_cache,self.f.maven,self.f.official(),root=self.f.root)
        path=ml.receipt_dir(self.f.maven,self.f.lock)/'medialibrary-all-0.13.24-rd1.aar'
        path.write_bytes(path.read_bytes()+b'tampered')
        with self.assertRaisesRegex(ml.MediaContractError,'checksum'):
            ml.verify_maven(self.f.native_cache,self.f.maven,root=self.f.root)

    def test_cached_artifact_invalidated_when_source_lock_changes(self):
        self.f.collect()
        ml.package_maven(self.f.native_cache,self.f.maven,self.f.official(),root=self.f.root)
        lock=self.f.lock.copy();lock['libvlcjni_commit']='b'*40
        self.f.write('ci/medialibrary.lock.json',ml.json_bytes(lock))
        with self.assertRaises(ml.MediaContractError):
            ml.verify_maven(self.f.native_cache,self.f.maven,root=self.f.root)

    def test_official_baseline_receipt_checksum_negative(self):
        official=self.f.official()
        root=self.f.root/'official';root.mkdir()
        for k,v in official.items(): (root/('medialibrary-all-0.13.24.'+k)).write_bytes(v)
        manifest={'schema':1,'source':'repo.maven.apache.org', 'files_sha256':{
          'medialibrary-all-0.13.24.'+k:ml.sha(v) for k,v in official.items()}}
        (root/'official-manifest.json').write_bytes(ml.json_bytes(manifest))
        self.assertEqual(ml.read_official(root),official)
        (root/'medialibrary-all-0.13.24.aar').write_bytes(b'different')
        with self.assertRaisesRegex(ml.MediaContractError,'checksum'):
            ml.read_official(root)

    def test_unsafe_docker_registry_digest_refused(self):
        self.f.collect()
        with self.assertRaises(ml.MediaContractError):
            ml.make_receipt('x86',image='evil.example@sha256:'+'b'*64,native=self.f.elf('x86'),lock=self.f.lock)

    def test_cache_key_is_source_and_binary_bound(self):
        self.f.collect()
        k1=ml.cache_key(self.f.native_cache,'a'*64,root=self.f.root)
        k2=ml.cache_key(self.f.native_cache,'b'*64,root=self.f.root)
        self.assertNotEqual(k1,k2)
        self.assertRegex(k1, r'^vlc-patched-media-v1-[0-9a-f]{64}$')


if __name__ == '__main__':
    unittest.main()
