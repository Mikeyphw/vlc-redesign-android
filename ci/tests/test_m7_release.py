"""Current M7 release supply-chain and negative safety regression tests."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'ci'))
import release_qualify as rq


class ReleaseQualificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = (ROOT/'.github/workflows/vlc-release.yml').read_text('utf-8')

    def complete_run(self):
        run = dict(id=1234,workflow_id=rq.PR_WORKFLOW_ID,event='workflow_dispatch',head_branch='main',
                   head_sha='a'*40,repository={'full_name': rq.REPOSITORY},status='completed',
                   conclusion='success',run_attempt=2)
        jobs = {'total_count':len(rq.REQUIRED_CI_JOBS),
                'jobs':[{'name':n,'status':'completed','conclusion':'success','run_attempt':2}
                        for n in sorted(rq.REQUIRED_CI_JOBS)]}
        main={'object':{'sha':'a'*40}}
        return run,jobs,main

    def qualify(self, run, jobs, main, **overrides):
        args=dict(head='a'*40,run_id=1234,repo=rq.REPOSITORY,ref='refs/heads/main')
        args.update(overrides)
        return rq.validate_source_run(run,jobs,main,**args)

    def test_actual_release_workflow_fail_closed_contract(self):
        rq.require_release_workflow_contract(self.workflow)
        self.assertIn('environment: vlc-release',self.workflow)
        self.assertNotIn('pull_request_target:',self.workflow)

    def test_bad_trigger_or_permission_or_skip_rejected(self):
        for mutation in (
            self.workflow.replace('  workflow_dispatch:', '  pull_request:'),
            self.workflow.replace('  actions: read', '  actions: write'),
            self.workflow.replace('environment: vlc-release', 'environment: public'),
            self.workflow.replace('needs: verify-source', 'needs: android-debug'),
            self.workflow.replace('ci/release_qualify.py apks', 'echo skipped'),
            self.workflow.replace('assembleSignedRelease', 'assembleDebug'),
            self.workflow.replace('pattern: mla-*', 'pattern: any-*'),
            self.workflow.replace('if-no-files-found: error', 'if-no-files-found: warn'),
            self.workflow.replace('      - name: Verify source', '      - name: Verify source')+'\ncontinue-on-error: true\n',
        ):
            with self.subTest(snippet=mutation[:85]),self.assertRaises(rq.ReleaseRefused):
                rq.require_release_workflow_contract(mutation)

    def test_exact_main_run_all_jobs_pass(self):
        self.assertEqual(self.qualify(*self.complete_run())['ci_attempt'],2)

    def test_untrusted_source_run_or_wrong_branch_refused(self):
        for field,value in (('event','pull_request'),('head_branch','feature/fake'),('workflow_id',0),
                            ('head_sha','b'*40),('conclusion','neutral'),('status','in_progress'),
                            ('repository',{'full_name':'evil/owner'}),('run_attempt',None)):
            run,jobs,main=self.complete_run();run[field]=value
            with self.subTest(field=field),self.assertRaises(rq.ReleaseRefused):
                self.qualify(run,jobs,main)
        run,jobs,main=self.complete_run()
        with self.assertRaises(rq.ReleaseRefused):self.qualify(run,jobs,main,ref='refs/heads/feature')
        with self.assertRaises(rq.ReleaseRefused):self.qualify(run,jobs,main,repo='upstream/vlc')
        with self.assertRaises(rq.ReleaseRefused):self.qualify(run,jobs,main,head='b'*40)

    def test_skipped_or_missing_required_jobs_refused(self):
        for variant in ('skipped','neutral','failed','duplicated','missing','wrong_attempt','truncated'):
            run,jobs,main=self.complete_run()
            if variant in ('skipped','neutral','failed'):
                jobs['jobs'][0]['conclusion']=variant
            elif variant=='duplicated':
                jobs['jobs'] += [dict(jobs['jobs'][0])];jobs['total_count'] += 1
            elif variant=='missing':
                jobs['jobs'].pop();jobs['total_count'] -= 1
            elif variant=='wrong_attempt':
                jobs['jobs'][0]['run_attempt']=1
            elif variant=='truncated':
                jobs['total_count'] += 1
            with self.subTest(variant=variant),self.assertRaises(rq.ReleaseRefused):
                self.qualify(run,jobs,main)

    def test_stale_main_rejected(self):
        run,jobs,main=self.complete_run();main['object']['sha']='b'*40
        with self.assertRaises(rq.ReleaseRefused):self.qualify(run,jobs,main)

    def test_signing_variables_missing_and_invalid_refused(self):
        values=dict(RD_RELEASE_KEYSTORE_B64='AA'*2000,RD_KEYSTORE_PASSWORD='pass',RD_KEY_ALIAS='release',
                    RD_KEY_PASSWORD='pass',RD_RELEASE_CERT_SHA256='a'*64)
        values['RD_RELEASE_KEYSTORE_B64']='QQ=='*500 # malformed
        with self.assertRaises(rq.ReleaseRefused):rq.check_signing_env(values)
        import base64
        values['RD_RELEASE_KEYSTORE_B64']=base64.b64encode(b'K'*1200).decode()
        rq.check_signing_env(values)
        for name in values:
            invalid=dict(values);invalid[name]=''
            with self.subTest(name=name),self.assertRaises(rq.ReleaseRefused):
                rq.check_signing_env(invalid)

    def test_badging_and_version_code_invariants(self):
        txt=("package: name='com.mikeyphw.vlcredesign' versionCode='13107056' versionName='0.7.5'\n"
             "sdkVersion:'21'\ntargetSdkVersion:'36'\nnative-code: 'arm64-v8a'\n")
        meta=rq.parse_badging(txt)
        self.assertEqual(meta['abis'],['arm64-v8a'])
        self.assertEqual(meta['version_code'],rq.expected_version_code('0.7.5','arm64-v8a'))
        for raw in ('',txt.replace("native-code: 'arm64-v8a'",'')):
            with self.assertRaises(rq.ReleaseRefused):rq.parse_badging(raw)
        for v in ('oops','0.7.100','0.7.-1'):
            with self.assertRaises(rq.ReleaseRefused):rq.expected_version_code(v,'arm64-v8a')

    def test_signer_requires_v1_v2_and_single_approved_certificate(self):
        source=('Verified using v1 scheme (JAR signing): true\n'
                'Verified using v2 scheme (APK Signature Scheme v2): true\n'
                'Signer #1 certificate SHA-256 digest: '+'a'*64+'\n')
        self.assertEqual(rq.parse_signer(source),'a'*64)
        for broken in (source.replace('v2 scheme (APK Signature Scheme v2): true',
                                      'v2 scheme (APK Signature Scheme v2): false'),
                       source.replace('Signer #1','Signer #2')+source.splitlines()[-1]+'\n',
                       source.replace('a'*64,'bad'), ''):
            with self.assertRaises(rq.ReleaseRefused):rq.parse_signer(broken)

    def test_dependency_resolution_fail_closed(self):
        example='signedReleaseRuntimeClasspath\n'+''.join(
            f'+--- org.example:g{i}:1.0.0\n' for i in range(12))
        self.assertEqual(len(rq.parse_dependencies(example)),12)
        for bad in ('',example.replace('signedReleaseRuntimeClasspath','debugRuntimeClasspath'),
                    example+'\\--- org.bad:failed:1.0.0 FAILED\n'):
            with self.assertRaises(rq.ReleaseRefused):rq.parse_dependencies(bad)

    def test_distinct_app_id_and_release_build_fail_closed(self):
        gradle=(ROOT/'build.gradle').read_text('utf-8')
        app=(ROOT/'application/app/build.gradle').read_text('utf-8')
        self.assertIn('appId = "com.mikeyphw.vlcredesign"',gradle)
        self.assertIn('rdSignedReleaseRequested',app)
        self.assertIn('throw new GradleException(',app)
        self.assertNotIn("project.hasProperty('keyStoreFile')",app)
        self.assertIn('signingConfig = signingConfigs.release',app)
        self.assertEqual(app.count('applicationId rootProject.ext.appId'),1)
        self.assertIn("task.tokenize(':').last().toLowerCase(java.util.Locale.ROOT)",app)
        self.assertNotIn('it.toLowerCase() ==~ /assemble.*Release/',app)

    def test_release_is_separate_from_original_pr_ci_contract(self):
        pr=(ROOT/'.github/workflows/vlc-pr.yml').read_text('utf-8')
        self.assertIn('pull_request:',pr)
        self.assertNotIn('RD_RELEASE_KEYSTORE_B64',pr)
        self.assertNotIn('assembleSignedRelease',pr)
        self.assertNotIn('environment: vlc-release',pr)


if __name__ == '__main__':unittest.main()
