"""Runnable positive and negative contracts for official host-mounted SDK 36."""
from pathlib import Path
import os
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from verify_android_sdk import verify_sdk, SDKLayoutError


class SDKLayoutTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='vlc-sdk-test-')
        self.root = Path(self.temp.name)
        self.platform = self.root/'platforms/android-36'
        self.tools = self.root/'build-tools/36.0.0'
        self.platform.mkdir(parents=True)
        self.tools.mkdir(parents=True)
        (self.platform/'source.properties').write_text('AndroidVersion.ApiLevel=36\nPkg.Revision=2\n')
        (self.platform/'android.jar').write_bytes(b'zip contents')
        (self.tools/'source.properties').write_text('Pkg.Revision=36.0.0\n')
        (self.tools/'aapt2').write_bytes(b'android build tool')
        (self.tools/'aapt2').chmod(0o755)

    def tearDown(self):
        self.temp.cleanup()

    def test_verified_official_layout(self):
        verify_sdk(self.root)

    def test_missing_platform_or_build_tools_refused(self):
        for item in (self.platform/'android.jar', self.tools/'aapt2'):
            content=item.read_bytes()
            item.unlink()
            with self.subTest(item=str(item)), self.assertRaises(SDKLayoutError):
                verify_sdk(self.root)
            item.write_bytes(content)
            if item.name=='aapt2': item.chmod(0o755)

    def test_wrong_api_or_revision_refused(self):
        for item, bad in ((self.platform/'source.properties','AndroidVersion.ApiLevel=35\n'),
                          (self.tools/'source.properties','Pkg.Revision=35.0.0\n')):
            before=item.read_text()
            item.write_text(bad)
            with self.subTest(item=str(item)), self.assertRaises(SDKLayoutError):
                verify_sdk(self.root)
            item.write_text(before)

    def test_symlinked_package_or_file_refused(self):
        target=self.platform/'android.jar'
        target.unlink()
        outside=self.root/'foreign'
        outside.write_bytes(b'foreign SDK')
        target.symlink_to(outside)
        with self.assertRaises(SDKLayoutError): verify_sdk(self.root)

    def test_empty_sdk_component_refused(self):
        (self.platform/'android.jar').write_bytes(b'')
        with self.assertRaises(SDKLayoutError): verify_sdk(self.root)

    def test_aapt2_needs_execute_permission(self):
        (self.tools/'aapt2').chmod(0o644)
        with self.assertRaises(SDKLayoutError): verify_sdk(self.root)


if __name__=='__main__':
    unittest.main()
