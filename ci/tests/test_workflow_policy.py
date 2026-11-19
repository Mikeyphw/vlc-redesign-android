"""Current source-bound CI qualification, caches, DAG and negative security gates."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'ci'))
import workflow_policy as wp
import medialibrary as ml
from test_medialibrary_pipeline import TempMediaFixture


def source_files() -> dict[str,str]:
    return {p.name:p.read_text('utf-8') for p in (ROOT/'.github/workflows').glob('*.yml')}


class CIContracts(unittest.TestCase):
    def setUp(self):
        self.f = TempMediaFixture()
        for file, contents in source_files().items():
            self.f.write('.github/workflows/'+file,contents)
        self.f.write('config/delivery-required-ci.json', (ROOT/'config/delivery-required-ci.json').read_bytes())
        self.f.write('ci/verify_android_sdk.py', (ROOT/'ci/verify_android_sdk.py').read_bytes())
        self.guard = mock.patch.object(wp, 'ROOT', self.f.root)
        self.lock_pins = mock.patch.object(ml,'TRUSTED_PATCH_BLOBS',self.f.lock['patches'])
        self.lock_pins.start()
        self.guard.start()

    def tearDown(self):
        self.guard.stop()
        self.lock_pins.stop()
        self.f.close()

    def files(self):
        return source_files()

    def test_real_workflow_and_required_policy(self):
        wp.require_workflow_contract(self.files())
        wp.require_policy(json.loads((ROOT/'config/delivery-required-ci.json').read_text()))
        wp.check_repository(self.f.root)

    def test_guard_never_matches_itself(self):
        source = self.files()['vlc-pr.yml']
        wp.require_workflow_safe(source,filename='vlc-pr.yml')
        self.assertIn('python3 -B ci/workflow_policy.py',source)

    def test_privileged_event_blocked(self):
        for snippet in ('on:\n  pull_request_target:\n','on: [pull_request_target]',
                        "on: {'pull_request_target': {}}",'# pull_request_target:\n'):
            with self.subTest(snippet=snippet),self.assertRaises(wp.ContractFailure):
                wp.require_workflow_safe(snippet,filename='hostile.yml')

    def test_privileged_permissions_blocked(self):
        for snippet in ('permissions: write-all\n','permissions:\n  contents: write\n',
                        'permissions: {contents: write}\n', 'permissions:\n  id-token: write\n'):
            with self.subTest(snippet=snippet),self.assertRaises(wp.ContractFailure):
                wp.require_workflow_safe(snippet,filename='hostile.yml')

    def test_unapproved_workflow_identity_blocked(self):
        policy = json.loads((ROOT/'config/delivery-required-ci.json').read_text())
        for field,bad in (('workflow_id',1),('name','spoofed workflow')):
            invalid=copy.deepcopy(policy)
            invalid['required_workflows'][0][field]=bad
            with self.assertRaises(wp.ContractFailure):wp.require_policy(invalid)
        self.assertEqual(wp.WORKFLOW_ID,422964106)

    def test_required_policy_repository_event_and_types(self):
        policy=json.loads((ROOT/'config/delivery-required-ci.json').read_text())
        for field,bad in (('repository','KuchiSofts/vlc-redesign-android'),('base_branch','other'),
                          ('event','push'),('release_qualification','passed'),('schema_version',True)):
            wrong=copy.deepcopy(policy);wrong[field]=bad
            with self.subTest(field=field),self.assertRaises(wp.ContractFailure):wp.require_policy(wrong)
        wrong=copy.deepcopy(policy);wrong['required_workflows'][0]['workflow_id']='422964106'
        with self.assertRaises(wp.ContractFailure):wp.require_policy(wrong)

    def test_native_abi_matrix_missing_member_blocked(self):
        files=self.files();files['vlc-pr.yml']=files['vlc-pr.yml'].replace('          - abi: x86_64\n','          - abi: other\n')
        with self.assertRaises(wp.ContractFailure):wp.require_workflow_contract(files)

    def test_mismatched_videolan_compiler_image_blocked(self):
        files=self.files();files['vlc-pr.yml']=files['vlc-pr.yml'].replace('registry.videolan.org/vlc-debian-android:20260611225331',
                        'registry.example.test/broken:latest')
        with self.assertRaises(wp.ContractFailure):wp.require_workflow_contract(files)

    def test_gradle_version_must_match_agp_compatibility(self):
        files=self.files();files['vlc-pr.yml']=files['vlc-pr.yml'].replace("gradle-version: '9.6.0'", "gradle-version: '9.4.0'")
        with self.assertRaises(wp.ContractFailure):wp.require_workflow_contract(files)

    def test_source_native_package_android_dag_cannot_be_skipped(self):
        for before,after in (('needs: source-contracts','needs: other-job'),
                             ('needs: media-native','needs: unknown'),
                             ('needs: [source-contracts, media-package]','needs: source-contracts')):
            files=self.files();files['vlc-pr.yml']=files['vlc-pr.yml'].replace(before,after)
            with self.subTest(before=before),self.assertRaises(wp.ContractFailure):wp.require_workflow_contract(files)

    def test_cache_verification_cannot_be_removed(self):
        for name in ('verify-abi','verify-maven','fetch-official','collect-abi','cache-key'):
            files=self.files();files['vlc-pr.yml']=files['vlc-pr.yml'].replace('ci/medialibrary.py '+name,'ci/medialibrary.py bypass-'+name)
            with self.subTest(name=name),self.assertRaises(wp.ContractFailure):wp.require_workflow_contract(files)

    def test_external_maven_url_fallback_forbidden(self):
        files=self.files();files['vlc-pr.yml']+='\n# VLC_RD_MAVEN_BASE_URL\n'
        with self.assertRaises(wp.ContractFailure):wp.require_workflow_contract(files)
        files=self.files();files['vlc-pr.yml']=files['vlc-pr.yml'].replace('ci/_maven/repository', 'https://evil.example/maven')
        with self.assertRaises(wp.ContractFailure):wp.require_workflow_contract(files)

    def test_unconditional_bypass_forbidden(self):
        files=self.files();files['vlc-pr.yml']+='\n# continue-on-error: true\n'
        with self.assertRaises(wp.ContractFailure):wp.require_workflow_contract(files)
        files=self.files();files['vlc-pr.yml']+='\n# || true\n'
        with self.assertRaises(wp.ContractFailure):wp.require_workflow_contract(files)

    def test_required_android_apk_build_cannot_be_substituted(self):
        files=self.files();files['vlc-pr.yml']=files['vlc-pr.yml'].replace(':application:app:assembleDebug',':application:app:help')
        with self.assertRaises(wp.ContractFailure):wp.require_workflow_contract(files)

    def test_docker_image_digest_check_required(self):
        files=self.files();files['vlc-pr.yml']=files['vlc-pr.yml'].replace('docker pull "$VLC_IMAGE"','echo no-container-pull')
        with self.assertRaises(wp.ContractFailure):wp.require_workflow_contract(files)

    def test_docker_execution_uses_runner_uid_gid_and_isolated_home(self):
        source=self.files()['vlc-pr.yml']
        self.assertIn('--user "$(id -u):$(id -g)"', source)
        self.assertIn('--env HOME=/tmp/vlc-ci-home', source)
        self.assertIn('--mount "type=bind,src=$GITHUB_WORKSPACE,dst=/workspace"', source)

    def test_removing_container_user_or_home_breaks_native_contract(self):
        for required in ('--user "$(id -u):$(id -g)"', '--env HOME=/tmp/vlc-ci-home',
                         '--mount "type=bind,src=$GITHUB_WORKSPACE,dst=/workspace"'):
            files=self.files()
            self.assertIn(required,files['vlc-pr.yml'])
            files['vlc-pr.yml']=files['vlc-pr.yml'].replace(required, '# identity removed',1)
            with self.subTest(required=required),self.assertRaises(wp.ContractFailure):
                wp.require_workflow_contract(files)

    def test_native_workspace_guards_are_required(self):
        script=self.f.root/'ci/build_medialibrary_abi.sh'
        original=script.read_text('utf-8')
        for required in ('stat -c %u /workspace', 'stat -c %g /workspace',
                         '[ ! -w /workspace ]', '[ ! -w /workspace/.git ]',
                         'mkdir -p "$HOME"', '[ ! -w "$HOME" ]'):
            self.assertIn(required,original)
            script.write_text(original.replace(required, '# denied guard removed',1))
            with self.subTest(required=required),self.assertRaises(wp.ContractFailure):
                wp.check_repository(self.f.root)
            script.write_text(original)

    def test_wrong_default_oci_user_without_workspace_uid_refused(self):
        files=self.files()
        files['vlc-pr.yml']=files['vlc-pr.yml'].replace('--user "$(id -u):$(id -g)"', '--user 0:0',1)
        with self.assertRaises(wp.ContractFailure): wp.require_workflow_contract(files)

    def test_runner_sdk_and_isolated_wrapper_contract(self):
        from subprocess import run
        source=self.f.root/'ci/build_medialibrary_abi.sh'
        result=run(['bash','-n',str(source)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        wp.check_repository(self.f.root)
        text=source.read_text('utf-8')
        self.assertIn('python3 -B ci/verify_android_sdk.py --sdk "$base_sdk"',text)
        self.assertIn('gradle-wrapper-bootstrap',text)
        self.assertIn('compile-medialibrary.sh -a "$ABI" --release',text)
        self.assertNotIn('sdk="$HOME/android-sdk"',text)
        self.assertNotIn('compile.sh -a "$ABI" -t -ml --release -b',text)

    def test_removing_runner_sdk_mounts_is_refused(self):
        workflow=self.files()['vlc-pr.yml']
        for token in ('android-actions/setup-android@v3',
                      "cmdline-tools/16.0", "cmdline-tools/latest",
                      "cmdline-tools-version: '12266719'",
                      'Pkg\\.Revision[[:space:]]',
                      '"$official_sdkmanager" --sdk_root="$sdk_root"',
                      '--mount "type=bind,src=$native_platform,dst=/sdk/android-sdk-linux/platforms/android-36,readonly"',
                      '--mount "type=bind,src=$native_tools,dst=/sdk/android-sdk-linux/build-tools/36.0.0,readonly"'):
            with self.subTest(token=token):
                files=self.files()
                files['vlc-pr.yml']=workflow.replace(token,'# removed runner SDK gate',1)
                with self.assertRaises(wp.ContractFailure):
                    wp.require_workflow_contract(files)

    def test_removing_native_readonly_guards_is_refused(self):
        script=self.f.root/'ci/build_medialibrary_abi.sh'
        original=script.read_text('utf-8')
        for token in ('VLC_NATIVE_SDK_PATH_MISMATCH',
                      'python3 -B ci/verify_android_sdk.py --sdk "$base_sdk"',
                      '[ -w "$base_sdk/platforms/android-36" ]',
                      'VLC_NATIVE_SDK_MOUNTS_NOT_READONLY',
                      'gradle --no-daemon --project-dir "$bootstrap" wrapper',
                      '--gradle-distribution-sha256-sum bbaeb2fef8710818cf0e261201dab964c572f92b942812df0c3620d62a529a01',
                      'export GRADLE_PATH_VERSION=9.6.0',
                      './buildsystem/compile-medialibrary.sh -a "$ABI" --release'):
            self.assertIn(token,original)
            script.write_text(original.replace(token,'# removed native guard',1))
            with self.subTest(token=token),self.assertRaises(wp.ContractFailure):
                wp.check_repository(self.f.root)
            script.write_text(original)

    def test_image_local_sdk_installation_is_refused(self):
        script=self.f.root/'ci/build_medialibrary_abi.sh'
        original=script.read_text('utf-8')
        script.write_text(original+'\nsdkmanager --sdk_root=/tmp/replacement "platforms;android-36"\n')
        with self.assertRaises(wp.ContractFailure): wp.check_repository(self.f.root)
        script.write_text(original)

    def test_runner_sdk_gate_cannot_be_moved_after_compile(self):
        files=self.files()
        source=files['vlc-pr.yml']
        source=source.replace('Install and verify official runner SDK 36', 'Runner install deferred',1)
        files['vlc-pr.yml']=source
        with self.assertRaises(wp.ContractFailure): wp.require_workflow_contract(files)

    def test_unrelated_gradle_publication_reintroduced_is_refused(self):
        script=self.f.root/'ci/build_medialibrary_abi.sh'
        original=script.read_text('utf-8')
        script.write_text(original+'\n./buildsystem/compile.sh -a "$ABI" -t -ml --release -b\n')
        with self.assertRaises(wp.ContractFailure): wp.check_repository(self.f.root)
        script.write_text(original)

    def test_unsafe_root_or_chown_native_escalation_refused(self):
        script=self.f.root/'ci/build_medialibrary_abi.sh'
        original=script.read_text('utf-8')
        for token in ('sudo chmod -R 777 /workspace','chown -R 0:0 /workspace'):
            script.write_text(original+'\n'+token+'\n')
            with self.subTest(token=token),self.assertRaises(wp.ContractFailure):
                wp.check_repository(self.f.root)
        script.write_text(original)

    def test_no_hidden_static_only_or_skipped_checks(self):
        files=self.files();files['vlc-pr.yml']+='\n      - name: Inert\n        if: false\n'
        with self.assertRaises(wp.ContractFailure):wp.require_workflow_contract(files)


if __name__ == '__main__':
    unittest.main()
