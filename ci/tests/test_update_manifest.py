# SPDX-License-Identifier: GPL-2.0-or-later
import hashlib, json, os, shutil, subprocess, tempfile, unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import update_manifest as u
from release_qualify import ReleaseRefused, REPOSITORY, PR_WORKFLOW_ID
from qualify_update_pair import qualify

class UpdateManifestTests(unittest.TestCase):
    def create(self, folder, identity='standalone', cert='a'*64):
        receipts=[]
        for abi in u.ABIS:
            name=f'VLC-Redesign-{identity}-0.7.6-{abi}.apk'
            p=folder/name; p.write_bytes(('fake-apk-test-only-'+abi).encode())
            receipts.append(dict(apk=name,release_identity=identity,application_id=u.RELEASE_IDENTITIES[identity],abi=abi,signer_sha256=cert,min_sdk=21,target_sdk=36,version_name='0.7.6',version_code=u.expected_version_code('0.7.6',abi),sha256=u.sha256(p)))
        return receipts
    def build(self, folder, receipts, identity='standalone', cert='a'*64, channel='stable'):
        return u.manifest_bytes(receipts, folder, identity=identity,head='b'*40,cert=cert,channel=channel,notes='Fixes and updates')
    def test_both_identities_deterministic_and_distinct(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for id in u.RELEASE_IDENTITIES:
                d=root/id;d.mkdir();r=self.create(d,id);data=self.build(d,r,id)
                self.assertEqual(data,self.build(d,list(reversed(r)),id))
                m=json.loads(data);self.assertEqual(m['packageName'],u.RELEASE_IDENTITIES[id]);self.assertEqual(len(m['assets']),4)
                self.assertEqual({a['abi'] for a in m['assets']},set(u.ABIS))
    def test_wrong_package_signer_abi_version_digest_and_channel(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);r=self.create(root)
            for key,value in [('application_id','org.videolan.vlc'),('signer_sha256','b'*64),('abi','mips'),('version_code',1),('sha256','b'*64),('apk','../bad.apk')]:
                bad=[dict(x) for x in r];bad[0][key]=value
                with self.subTest(key=key),self.assertRaises(ReleaseRefused):self.build(root,bad)
            with self.assertRaises(ReleaseRefused):self.build(root,r,channel='untrusted')
            with self.assertRaises(ReleaseRefused):self.build(root,r[:-1])
            (root/r[0]['apk']).write_bytes(b'tampered')
            with self.assertRaises(ReleaseRefused):self.build(root,r)
    @unittest.skipUnless(shutil.which('java') and shutil.which('keytool'),'requires JDK')
    def test_real_detached_signature_and_tamper_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);ks=root/'test.p12'; cert=root/'expected.cer'; password='fixture-only-test-password'
            subprocess.run(['keytool','-genkeypair','-alias','test','-keyalg','RSA','-keysize','2048','-dname','CN=Test Fixture','-validity','2','-storetype','PKCS12','-keystore',str(ks),'-storepass',password,'-keypass',password],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            subprocess.run(['keytool','-exportcert','-alias','test','-keystore',str(ks),'-storepass',password,'-file',str(cert)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            digest=hashlib.sha256(cert.read_bytes()).hexdigest()
            r=self.create(root,cert=digest); files=u.paths(root,'standalone');files[0].write_bytes(self.build(root,r,cert=digest))
            env=dict(os.environ,RD_KEYSTORE_FILE=str(ks),RD_KEYSTORE_PASSWORD=password,RD_KEY_PASSWORD=password,RD_KEY_ALIAS='test')
            cmd=['java',str(Path(u.__file__).with_name('UpdateManifestSigner.java'))]
            def invoke(action, expected=digest):return subprocess.run([*cmd,action,*map(str,files),expected],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60)
            self.assertEqual(invoke('sign').returncode,0)
            self.assertEqual(invoke('verify').returncode,0)
            self.assertNotEqual(invoke('verify','b'*64).returncode,0)
            files[0].write_bytes(files[0].read_bytes()+b' ')
            self.assertNotEqual(invoke('verify').returncode,0)
            self.assertNotEqual(invoke('sign').returncode,0) # no overwrite of earlier signature

    @unittest.skipUnless(shutil.which('java') and shutil.which('keytool'),'requires JDK')
    def test_complete_signed_pair_rejects_missing_tampered_and_mixed_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); stage=root/'staging';stage.mkdir();ks=root/'fixture.p12';cert=root/'expected.cer';password='fixture-only-test-password'
            subprocess.run(['keytool','-genkeypair','-alias','test','-keyalg','EC','-dname','CN=Pair Fixture','-validity','2','-storetype','PKCS12','-keystore',str(ks),'-storepass',password,'-keypass',password],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            subprocess.run(['keytool','-exportcert','-alias','test','-keystore',str(ks),'-storepass',password,'-file',str(cert)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            signer=hashlib.sha256(cert.read_bytes()).hexdigest();head='b'*40
            env=dict(os.environ,RD_KEYSTORE_FILE=str(ks),RD_KEYSTORE_PASSWORD=password,RD_KEY_PASSWORD=password,RD_KEY_ALIAS='test')
            for identity,pkg in u.RELEASE_IDENTITIES.items():
                d=stage/f'vlc-signed-staging-{identity}-{head}';d.mkdir();receipts=self.create(d,identity,signer)
                files=u.paths(d,identity);files[0].write_bytes(self.build(d,receipts,identity,signer))
                subprocess.run(['java',str(Path(u.__file__).with_name('UpdateManifestSigner.java')),'sign',*map(str,files),signer],env=env,check=True,capture_output=True,timeout=60)
                record=dict(schema='vlc-redesign-release-staging.v2',repository=REPOSITORY,branch='main',commit=head,source_ci_workflow_id=PR_WORKFLOW_ID,source_ci_run_id=42,source_ci_attempt=1,release_identity=identity,application_id=pkg,official_vlc_update_compatible=False,release_status='SIGNED_STAGING_ONLY_NOT_PUBLISHED_OR_DEVICE_QUALIFIED',apks=receipts,media_lock_sha256='a'*64)
                (d/f'{identity}-release-provenance.json').write_text(json.dumps(record));(d/f'{identity}-sbom.spdx.json').write_text('{}');(d/f'{identity}-RELEASE_ACCEPTANCE.md').write_text('Fixture only')
                (d/f'{identity}-SHA256SUMS').write_text(''.join(f'{u.sha256(p)}  {p.name}\n' for p in sorted(d.iterdir())))
            result=qualify(stage,root/'out',head=head,run=42,attempt=1,channel='stable');self.assertEqual(result['apk_count'],8)
            self.assertEqual(len(list((root/'out').glob('*.apk'))),8)
            with self.assertRaises(ReleaseRefused):qualify(stage,root/'wrong-run',head=head,run=43,attempt=1,channel='stable')
            d=stage/f'vlc-signed-staging-original-{head}';apk=next(d.glob('*.apk'));data=apk.read_bytes();apk.write_bytes(b'tampered')
            with self.assertRaises(ReleaseRefused):qualify(stage,root/'tampered',head=head,run=42,attempt=1,channel='stable')
            apk.write_bytes(data);shutil.move(str(d),str(root/'missing'))
            with self.assertRaises(ReleaseRefused):qualify(stage,root/'missing-edition',head=head,run=42,attempt=1,channel='stable')

if __name__=='__main__':unittest.main()
