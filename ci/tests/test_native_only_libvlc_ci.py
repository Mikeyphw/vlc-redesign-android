"""Regression and adversarial tests for native-only LibVLC CI qualification.

This verifies source-scoped behavior without pretending to compile ARM code
on the host. Real four-ABI ELF and Android JVM/APK gates remain hosted.
"""
import sys
import subprocess
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'ci'))
import workflow_policy as wp

COMPILER = ROOT/'buildsystem/compile.sh'
NATIVE = ROOT/'ci/build_medialibrary_abi.sh'
WORKFLOW = ROOT/'.github/workflows/vlc-pr.yml'

class NativeOnlyLibVLCCI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = COMPILER.read_text('utf-8')
        cls.native = NATIVE.read_text('utf-8')
        cls.workflow = WORKFLOW.read_text('utf-8')

    def test_current_source_guard_accepts_genuine_compiler(self):
        wp.require_native_only_libvlc_contract(self.native,self.compiler)
        self.assertEqual(subprocess.run(['sh','-n',str(COMPILER)],check=False).returncode,0)
        self.assertEqual(subprocess.run(['bash','-n',str(NATIVE)],check=False).returncode,0)

    def test_native_only_does_not_skip_android_qualification(self):
        source=self.workflow
        for token in ('needs: media-native','needs: [source-contracts, media-package]',
                      'bash ci/gradle_dependency_retry.sh test',
                      'bash ci/gradle_dependency_retry.sh assemble',
                      'python3 -B ci/medialibrary.py verify-abi',
                      'python3 -B ci/medialibrary.py verify-maven'):
            self.assertIn(token,source)

    def test_missing_native_only_flag_is_refused(self):
        self.assertEqual(self.native.count('VLC_NATIVE_CI_ONLY=1'),1)
        bad=self.native.replace('VLC_NATIVE_CI_ONLY=1 ','',1)
        with self.assertRaises(wp.ContractFailure):
            wp.require_native_only_libvlc_contract(bad,self.compiler)

    def test_flag_cannot_cover_medialibrary_compiler(self):
        bad=self.native.replace('./buildsystem/compile-medialibrary.sh -a "$ABI" --release',
                                'VLC_NATIVE_CI_ONLY=1 ./buildsystem/compile-medialibrary.sh -a "$ABI" --release',1)
        with self.assertRaises(wp.ContractFailure):
            wp.require_native_only_libvlc_contract(bad,self.compiler)

    def test_guards_must_not_be_omitted(self):
        for token in ('"${BUILD_LIBVLC:-0}" != "1"', '"${NO_ML:-0}" != "1"',
                      '"${RELEASE:-0}" != "1"','"${PREBUILT_CONTRIBS:-0}" != "1"',
                      'if [ ! -s "${OUT_DBG_DIR}/libvlcjni.so" ]; then',
                      'fail "VLC_NATIVE_CI_ONLY requires compiled LibVLC JNI ELF"'):
            self.assertIn(token,self.compiler)
            with self.subTest(token=token),self.assertRaises(wp.ContractFailure):
                wp.require_native_only_libvlc_contract(self.native,self.compiler.replace(token,'REMOVED',1))

    def test_early_native_exit_refused(self):
        native_compiler='${VLC_LIBJNI_PATH}/buildsystem/compile-libvlc.sh -a ${ARCH}'
        self.assertIn(native_compiler,self.compiler)
        early='if [ "${VLC_NATIVE_CI_ONLY:-0}" = "1" ]; then'
        bad=self.compiler.replace(early,'# scoped guard removed',1)
        with self.assertRaises(wp.ContractFailure):
            wp.require_native_only_libvlc_contract(self.native,bad)

    def test_native_compile_and_media_sequence_remain_required(self):
        for token in ('${VLC_LIBJNI_PATH}/buildsystem/compile-libvlc.sh -a ${ARCH}',
                      'cp -a ${VLC_LIBJNI_PATH}/libvlc/jni/obj/local/${ANDROID_ABI}/*.so "${OUT_DBG_DIR}"'):
            self.assertIn(token,self.compiler)
            with self.assertRaises(wp.ContractFailure):
                wp.require_native_only_libvlc_contract(self.native,self.compiler.replace(token,'REMOVED',1))
        with self.assertRaises(wp.ContractFailure):
            wp.require_native_only_libvlc_contract(self.native.replace(
                './buildsystem/compile-medialibrary.sh -a "$ABI" --release','exit 0',1),self.compiler)

if __name__=='__main__':
    unittest.main()
