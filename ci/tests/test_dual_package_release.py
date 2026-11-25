"""M9 two identities, original VLC signer non-continuity and release safety contracts."""
from __future__ import annotations
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'ci'))
import release_qualify as q

def manifest_fixture(pkg):
    lines=['E: manifest','  E: application']
    for suffix in ('.tv','.provider','.artwork','.thumbprovider'):
        lines += ['    E: provider',f'      A: android:authorities(0x01010018)="{pkg}{suffix}"']
    for suffix in ('.MEDIA','.permission.READ_EXTENSION_DATA','.permission.BIND_DATA_CONSUMER','.permission.REMOTE_ACCESS_CONTROL'):
        lines += ['  E: permission',f'    A: android:name(0x01010003)="{pkg}{suffix}"']
    lines += ['  E: uses-permission','    A: android:name(0x01010003)="android.permission.REQUEST_INSTALL_PACKAGES"']
    for tag,name in (('activity','UpdateActivity'),('activity','UpdateConfirmationActivity'),('service','UpdateJobService'),('receiver','UpdateInstallReceiver')):
        lines += [f'    E: {tag}',f'      A: android:name(0x01010003)="org.videolan.vlc.rd.updater.{name}"','      A: android:exported(0x01010010)=(type 0x12)0x0']
        if tag=='service':lines += ['      A: android:permission(0x01010006)="android.permission.BIND_JOB_SERVICE"']
    return '\n'.join(lines)

class DualPackageReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gradle=(ROOT/'build.gradle').read_text('utf-8')
        cls.app=(ROOT/'application/app/build.gradle').read_text('utf-8')
        cls.workflow=(ROOT/'.github/workflows/vlc-release.yml').read_text('utf-8')

    def test_two_package_ids_without_upstream_id_confusion(self):
        self.assertEqual(q.RELEASE_IDENTITIES, {
            'standalone':'com.mikeyphw.vlcredesign','original':'org.videolan.vlc'})
        self.assertNotIn('org.kuchisofts.vlcredesign', q.RELEASE_IDENTITIES.values())
        self.assertIn('rdReleaseIdentity',self.gradle)
        self.assertIn('RD_RELEASE_IDENTITY',self.gradle)
        self.assertIn('assembleSignedRelease',self.gradle)
        self.assertIn('appId = "com.mikeyphw.vlcredesign"',self.gradle)
        self.assertIn('appId = "org.videolan.vlc"',self.gradle)
        self.assertIn("redesignVersionName = '0.7.6'",self.gradle)
        self.assertIn('rootProject.ext.rdReleaseIdentity',self.app)

    def test_matrix_is_protected_and_nonpublishing(self):
        q.require_release_workflow_contract(self.workflow)
        # M7's release verifier finds the post-signing boundary by this prefix.
        # Matrix builds must retain the boundary, not weaken its check.
        marker='      - name: Check signed APKs'
        self.assertEqual(self.workflow.count(marker), 1)
        before,after=self.workflow.split(marker,1)
        self.assertIn('secrets.RD_RELEASE_KEYSTORE_B64', before)
        self.assertNotIn('secrets.', after)
        self.assertIn('release_identity: [standalone, original]',self.workflow)
        self.assertIn('environment: vlc-release',self.workflow)
        self.assertIn('RD_RELEASE_IDENTITY: ${{ matrix.release_identity }}',self.workflow)
        self.assertIn('RD_OFFICIAL_VLC_CERT_SHA256:',self.workflow)
        self.assertIn('--release-identity "$RD_RELEASE_IDENTITY"',self.workflow)
        self.assertIn('name: vlc-signed-staging-${{ matrix.release_identity }}-${{ github.sha }}',self.workflow)
        self.assertNotIn('gh release create',self.workflow)
        self.assertNotIn('pull_request_target:',self.workflow)
        self.assertNotIn('secrets.'+ 'RD_RELEASE_KEYSTORE_B64'+' }}'+'\n  workflow_dispatch',self.workflow)

    def test_post_verification_signing_secret_is_refused(self):
        # A secret introduced after APK verification must still fail closed.
        mark='      - name: Stage qualified artifacts for separate manual release approval'
        self.assertEqual(self.workflow.count(mark), 1)
        mutated=self.workflow.replace(mark,
            '      - name: Unsafe secret access after verification\n'
            '        env:\n'
            '          EXPOSED: ${{ secrets.RD_KEY_PASSWORD }}\n'+mark,1)
        with self.assertRaises(q.ReleaseRefused):
            q.require_release_workflow_contract(mutated)

    def test_fork_signer_must_differ_from_verified_official(self):
        release='a'*64
        q.require_distinct_official_signer(release, 'b'*64)
        for value in ('', 'bad', 'A'*64, 'a'*64):
            with self.subTest(value=value[:8] or '<empty>'),self.assertRaises(q.ReleaseRefused):
                q.require_distinct_official_signer(release,value)

    def test_compiled_manifest_identity_and_exported_gate(self):
        pkg=q.RELEASE_IDENTITIES['standalone']; good=manifest_fixture(pkg)
        q.verify_manifest_identity(good,pkg)
        for changed in (good.replace(pkg+'.tv','org.videolan.vlc.tv'),good.replace('(type 0x12)0x0','(type 0x12)0xffffffff'),good.replace('android.permission.BIND_JOB_SERVICE','android.permission.INTERNET'),good.replace(pkg+'.MEDIA','org.videolan.vlc.MEDIA'),good.replace('android.permission.REQUEST_INSTALL_PACKAGES','android.permission.INTERNET')):
            with self.assertRaises(q.ReleaseRefused):q.verify_manifest_identity(changed,pkg)

    def test_expected_abi_version_order(self):
        values=[q.expected_version_code('0.7.6',abi) for abi in q.ABIS]
        self.assertEqual(len(set(values)),4)
        self.assertGreater(q.expected_version_code('0.7.6','arm64-v8a'),q.expected_version_code('0.7.5','arm64-v8a'))

    def test_manifest_package_and_certificate_gates_for_both_identities(self):
        cert='c'*64
        for identity,pkg in q.RELEASE_IDENTITIES.items():
            with TemporaryDirectory() as d:
                folder=Path(d)
                for abi in q.ABIS:
                    (folder/f'VLC-Redesign-{identity}-0.7.6-{abi}.apk').write_bytes(b'example-'+abi.encode())
                def fake_run(argv):
                    if 'xmltree' in argv:return manifest_fixture(pkg)
                    apk=Path(argv[-1]); abi=next(x for x in q.ABIS if apk.name.endswith('-'+x+'.apk'))
                    if 'aapt' in Path(argv[0]).name:
                        return (f"package: name='{pkg}' versionCode='{q.expected_version_code('0.7.6',abi)}' versionName='0.7.6'\n"
                                "sdkVersion:'21'\ntargetSdkVersion:'36'\n"+f"native-code: '{abi}'\n")
                    return ("Verified using v1 scheme (JAR signing): true\n"
                            "Verified using v2 scheme (APK Signature Scheme v2): true\n"
                            f"Signer #1 certificate SHA-256 digest: {cert}\n")
                with patch.object(q,'_run',side_effect=fake_run):
                    receipts=q.verify_release_apks(folder,'aapt','apksigner',cert,identity)
                    self.assertEqual(len(receipts),4)
                    self.assertEqual({r['application_id'] for r in receipts},{pkg})
                    self.assertEqual({r['release_identity'] for r in receipts},{identity})
                    with self.assertRaises(q.ReleaseRefused):
                        q.verify_release_apks(folder,'aapt','apksigner','d'*64,identity)
                    # Try to deceive the verifier by checking the other identity's APKs.
                    other='original' if identity=='standalone' else 'standalone'
                    with self.assertRaises(q.ReleaseRefused):
                        q.verify_release_apks(folder,'aapt','apksigner',cert,other)

if __name__=='__main__':
    unittest.main()
