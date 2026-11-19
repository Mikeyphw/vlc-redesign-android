#!/usr/bin/env python3
"""Current source-owned fail-closed GitHub Actions and native-Maven CI contracts.

No YAML dependencies or privileged GitHub Actions permission required.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys

REPOSITORY = 'Mikeyphw/vlc-redesign-android'
WORKFLOW_FILE = 'vlc-pr.yml'
WORKFLOW_NAME = 'VLC Android PR qualification'
WORKFLOW_ID = 422964106  # verified original PR workflow ID
GRADLE_MINIMUM = '9.6.0'
POLICY_PATH = Path('config/delivery-required-ci.json')
WORKFLOW_DIRECTORY = Path('.github/workflows')
ROOT = Path(__file__).resolve().parents[1]


class ContractFailure(ValueError):
    pass


def require_workflow_safe(text: str, *, filename: str) -> None:
    if re.search(r'(?<![A-Za-z0-9_])pull_request_target(?![A-Za-z0-9_])', text):
        raise ContractFailure(f'{filename}: privileged PR event forbidden')
    if re.search(r'(?m)^\s*permissions\s*:\s*(?:write-all|\{[^}]*\bwrite\b[^}]*\})', text):
        raise ContractFailure(f'{filename}: over-broad permissions forbidden')
    if re.search(r'(?m)^\s*(?:contents|actions|id-token|pull-requests|issues|packages|workflows|checks|statuses|deployments)\s*:\s*write\s*(?:#.*)?$', text):
        raise ContractFailure(f'{filename}: write-permission escalation forbidden')


def require_policy(policy: dict) -> None:
    fields = {'schema_version', 'repository', 'base_branch', 'event', 'release_qualification', 'required_workflows'}
    if not isinstance(policy, dict) or set(policy) != fields:
        raise ContractFailure('required-CI policy has missing/unknown fields')
    if (type(policy['schema_version']) is not int or policy['schema_version'] != 1
            or policy['repository'] != REPOSITORY or policy['base_branch'] != 'main'
            or policy['event'] != 'pull_request' or policy['release_qualification'] != 'separate'
            or policy['required_workflows'] != [{'name': WORKFLOW_NAME, 'workflow_id': WORKFLOW_ID}]):
        raise ContractFailure('required-CI policy identity drift')


def must_have(text: str, literal: str, label: str) -> None:
    if literal not in text:
        raise ContractFailure(label + ' missing: ' + literal)


def require_workflow_contract(contents: dict[str, str]) -> None:
    if WORKFLOW_FILE not in contents or 'vlc-upstream.yml' not in contents:
        raise ContractFailure('required PR/upstream workflows missing')
    for filename, source in sorted(contents.items()):
        require_workflow_safe(source, filename=filename)
    source = contents[WORKFLOW_FILE]
    if not re.search(r'(?m)^name:\s*VLC Android PR qualification\s*$', source):
        raise ContractFailure('required workflow name drift')
    if not re.search(r'(?m)^on:\s*\n\s+pull_request:\s*\n\s+branches:\s*\[main\]', source):
        raise ContractFailure('PR main-branch event no longer configured')
    if not re.search(r'(?m)^permissions:\s*\n\s+contents:\s*read\s*$', source):
        raise ContractFailure('PR workflow lacks explicit read-only permissions')
    for job in ('source-contracts', 'media-native', 'media-package', 'android-debug'):
        if not re.search(r'(?m)^  ' + re.escape(job) + r':\s*$', source):
            raise ContractFailure('required job missing: ' + job)
    for code in ('needs: source-contracts', 'needs: media-native',
                 'needs: [source-contracts, media-package]'):
        must_have(source, code, 'required DAG ordering')
    for code in ('python3 -B ci/workflow_policy.py', 'python3 -B ci/medialibrary.py source',
                 'ci/build_medialibrary_abi.sh', 'python3 -B ci/medialibrary.py collect-abi',
                 'python3 -B ci/medialibrary.py verify-abi', 'python3 -B ci/medialibrary.py fetch-official',
                 'python3 -B ci/medialibrary.py cache-key', 'python3 -B ci/medialibrary.py package',
                 'python3 -B ci/medialibrary.py verify-maven',
                 'actions/cache/restore@v4', 'actions/cache/save@v4',
                 'actions/upload-artifact@v4', 'actions/download-artifact@v4',
                 'if-no-files-found: error', "gradle-version: '9.6.0'",
                 'RD_MAVEN: ${{ github.workspace }}/ci/_maven/repository',
                 'bash ci/gradle_dependency_retry.sh test', 'bash ci/gradle_dependency_retry.sh assemble',
                 'docker pull "$VLC_IMAGE"', 'sha256:'):
        must_have(source, code, 'source-built patched Maven workflow')
    # setup-android@v3 defaults to `tools platform-tools`. Google removed
    # the legacy `tools` package: the action aborts before our SDK 36 step.
    # Both the native matrix and downstream Android job must override it,
    # and keep the pinned official command-line manager revision.
    actions=list(re.finditer(r'(?m)^      - uses: android-actions/setup-android@v3\s*$', source))
    if len(actions) != 2:
        raise ContractFailure('expected exactly two official setup-android action instances')
    for index, matched in enumerate(actions, 1):
        following=source[matched.end():]
        next_step=re.search(r'(?m)^      - (?:uses:|name:) ', following)
        segment=following[:next_step.start()] if next_step else following
        if not re.search(r"(?m)^          cmdline-tools-version: ['\"]12266719['\"]\s*$",segment):
            raise ContractFailure(f'setup-android instance {index} must pin official tools revision')
        package_lines=re.findall(r'(?m)^          packages: ([^\n#]+)$',segment)
        if len(package_lines)!=1 or package_lines[0].strip().strip("'\"")!='platform-tools':
            raise ContractFailure(f'setup-android instance {index} must select only platform-tools')
        if re.search(r"(?m)^          packages:.*(?:^|[ ,])tools(?:[ ,]|$)",segment):
            raise ContractFailure(f'setup-android instance {index} reintroduced retired tools package')
    # The checked-out repository must be writable *inside* each container.
    # A default OCI user can differ from the host runner and break native builds.
    native_segment = source.split('  media-native:',1)[1].split('  media-package:',1)[0]
    for required in ('--user "$(id -u):$(id -g)"',
                     '--env HOME=/tmp/vlc-ci-home',
                     '--mount "type=bind,src=$GITHUB_WORKSPACE,dst=/workspace"',
                     '--workdir /workspace "$VLC_IMAGE"',
                     '-euo pipefail ci/build_medialibrary_abi.sh "$VLC_ABI"'):
        if required not in native_segment:
            raise ContractFailure('native container workspace identity or mount contract missing: '+required)
    # Official Google SDK manager is used only on the hosted Ubuntu runner.
    # Cache hits still revalidate ABI ELF/source/digests, without SDK installs.
    for required in ('actions/setup-java@v4', 'android-actions/setup-android@v3',
                     'Install and verify official runner SDK 36',
                     "cmdline-tools/16.0", "cmdline-tools/latest",
                     "cmdline-tools-version: '12266719'",
                     'Pkg\\.Revision[[:space:]]',
                     '"$official_sdkmanager" --sdk_root="$sdk_root"',
                     'python3 -B ci/verify_android_sdk.py --sdk "$sdk_root"',
                     '--mount "type=bind,src=$native_platform,dst=/sdk/android-sdk-linux/platforms/android-36,readonly"',
                     '--mount "type=bind,src=$native_tools,dst=/sdk/android-sdk-linux/build-tools/36.0.0,readonly"'):
        if required not in native_segment:
            raise ContractFailure('official runner SDK / read-only OCI mount contract missing: '+required)
    if (native_segment.index('Restore content-keyed verified ABI cache') >=
            native_segment.index('Install and verify official runner SDK 36') or
            native_segment.index('Install and verify official runner SDK 36') >=
            native_segment.index('Compile patched native library using KuchiSofts sources')):
        raise ContractFailure('runner SDK installation must follow cache check and precede native compilation')
    setup_segment=native_segment.split('Restore content-keyed verified ABI cache',1)[1].split('Compile patched native library using KuchiSofts sources',1)[0]
    if setup_segment.count("if: steps.abi-reuse.outputs.reuse != 'true'") < 3:
        raise ContractFailure('runner SDK setup must not run on a verified ABI cache hit')
    # Native rebuild keys exclude the Python *verifier* and *Maven packager*:
    # those must rerun against a receipt, not force four C/C++ recompilations.
    if "hashFiles('ci/medialibrary.py'" in native_segment:
        raise ContractFailure('native compiler cache key depends on packaging implementation')
    if 'restore-keys: |' not in native_segment or 'mla-v1-${{ matrix.abi }}-${{ steps.image.outputs.digest_hex }}-' not in native_segment:
        raise ContractFailure('prior exact-image native caches cannot be recovered')
    for required in ('Qualify restored ABI before deciding whether to compile',
                     'id: abi-reuse',
                     'python3 -B ci/medialibrary.py verify-abi --abi "$VLC_ABI" --image-digest "$IMAGE_DIGEST"',
                     "if: steps.abi-reuse.outputs.reuse != 'true'",
                     "if: steps.abi-cache.outputs.cache-hit != 'true'"):
        if required not in native_segment:
            raise ContractFailure('unverified or nonincremental native cache: ' + required)
    if (native_segment.index('Qualify restored ABI before deciding whether to compile') >
            native_segment.index('Compile patched native library using KuchiSofts sources')):
        raise ContractFailure('native cached ELF must be verified before skipping compiler')
    if native_segment.count('python3 -B ci/verify_android_sdk.py --sdk "$sdk_root"') != 2:
        raise ContractFailure('runner SDK must be verified both after install and before mount')
    native_script=(ROOT/'ci/build_medialibrary_abi.sh').read_text('utf-8')
    for required in ('stat -c %u /workspace', 'stat -c %g /workspace',
                     '[ ! -w /workspace ]', '[ ! -w /workspace/.git ]',
                     '${HOME:-}', 'mkdir -p "$HOME"', '[ ! -w "$HOME" ]'):
        if required not in native_script:
            raise ContractFailure('native script workspace permission/home guard missing: '+required)
    # Native build uses KuchiSofts' original scripts, but must never invoke
    # the image's incompatible Python sdkmanager (0.6.11).
    for required in ('base_sdk="$(realpath -e "$ANDROID_SDK")"',
                     'VLC_NATIVE_SDK_PATH_MISMATCH',
                     'python3 -B ci/verify_android_sdk.py --sdk "$base_sdk"',
                     '[ -w "$base_sdk/platforms/android-36" ]',
                     '[ -w "$base_sdk/build-tools/36.0.0" ]',
                     'VLC_NATIVE_SDK_MOUNTS_NOT_READONLY',
                     'gradle --no-daemon --project-dir "$bootstrap" wrapper',
                     '--gradle-distribution-sha256-sum bbaeb2fef8710818cf0e261201dab964c572f92b942812df0c3620d62a529a01',
                     'distributionSha256Sum=bbaeb2fef8710818cf0e261201dab964c572f92b942812df0c3620d62a529a01',
                     'export GRADLE_PATH_VERSION=9.6.0',
                     './buildsystem/compile.sh -a "$ABI" -t -l --release',
                     './buildsystem/compile-medialibrary.sh -a "$ABI" --release'):
        if required not in native_script:
            raise ContractFailure('read-only SDK mount, checksum-pinned wrapper or native compiler guard missing: '+required)
    if ('sdkmanager --sdk_root' in native_script or 'sdk="$HOME/android-sdk"' in native_script
            or 'subprocess.run(cmd' in native_script):
        raise ContractFailure('obsolete image-local SDK installer reintroduced')
    sdk_verifier=ROOT/'ci/verify_android_sdk.py'
    if not sdk_verifier.is_file() or sdk_verifier.is_symlink():
        raise ContractFailure('SDK layout verifier missing or symlinked')
    for required in ('AndroidVersion\\.ApiLevel','Pkg\\.Revision',
                     'platforms/android-36/android.jar', 'build-tools/36.0.0/aapt2'):
        if required not in sdk_verifier.read_text('utf-8'):
            raise ContractFailure('installed SDK source/layout verifier incomplete: '+required)
    if './buildsystem/compile.sh -a "$ABI" -t -ml --release -b' in native_script:
        raise ContractFailure('native job must not execute unrelated MediaLibrary Gradle publication')
    if re.search(r'(?m)^\s*(?:chmod -R|chown|sudo |su )', native_script):
        raise ContractFailure('unsafe native SDK/workspace privilege escalation')
    # Only official documented VideoLAN images and four ABI outputs are accepted.
    from medialibrary import load_lock
    lock = load_lock(ROOT)
    matrix = source.split('  media-native:', 1)[1].split('  media-package:', 1)[0]
    for abi, image in lock['images'].items():
        if (matrix.count('abi: ' + abi + '\n') != 1 or
                matrix.count('image: ' + image + '\n') < 1):
            raise ContractFailure('missing ABI or VideoLAN source image ' + abi)
    if len(re.findall(r'(?m)^\s+- abi: ', matrix)) != 4:
        raise ContractFailure('native matrix must contain four ABIs')
    if not re.search(r'(?m)^\s+timeout-minutes:\s*2(?:10|40)\s*$', matrix):
        raise ContractFailure('native build lacks adequate bounded hosted timeout')
    if (source.count('python3 -B ci/medialibrary.py verify-maven') < 2 or
            source.index('python3 -B ci/medialibrary.py verify-maven', source.index('  android-debug:')) >
            source.index('bash ci/gradle_dependency_retry.sh test', source.index('  android-debug:'))):
        raise ContractFailure('Gradle is not gated on a verified local Maven AAR')
    # APK reuse can skip only assembly for identical source/toolchain/Maven
    # content. Unit tests and independent artifact verification remain required.
    android = source.split('  android-debug:',1)[1]
    required = ('Derive APK cache key from all non-CI tracked build inputs',
                'actions/cache/restore@v4', 'ci/apk_reuse.py key',
                'Validate cached APK before bypassing assembly',
                'ci/apk_reuse.py verify',
                'Run JVM unit tests against current source (never cached)',
                'Assemble Android debug APK only if inputs changed',
                'ci/apk_reuse.py seal',
                'Cache verified debug APK for identical source/toolchain inputs',
                'ci/_cache/debug-apk/*.apk',
                "if: steps.apk-cache.outputs.cache-hit == 'true'",
                "if: steps.apk-cache.outputs.cache-hit != 'true'")
    for code in required:
        if code not in android:
            raise ContractFailure('APK content-addressed reuse/test gate missing: ' + code)
    if not (android.index('Reject missing/tampered local patched MediaLibrary') <
            android.index('Derive APK cache key') <
            android.index('Validate cached APK before bypassing assembly') <
            android.index('Run JVM unit tests against current source') <
            android.index('Assemble Android debug APK only if inputs changed') <
            android.index('Qualify unchanged or newly built APK and checksums') <
            android.index('Upload unsigned debug APKs')):
        raise ContractFailure('APK source/cache/unit-test/build verification order unsafe')
    # A clean GitHub checkout does not contain the external LibVLCJNI Gradle
    # project required by root settings.gradle. Rebuild only the pinned source
    # checkout, not native artifacts, before Gradle JVM tests or APK assembly.
    prepare_name = 'Reconstruct exact upstream LibVLCJNI Gradle project (no native rebuild)'
    if android.count(prepare_name) != 1 or android.count('ci/prepare_android_gradle.py prepare') != 1:
        raise ContractFailure('exact LibVLCJNI source preparation step missing or duplicated')
    if android.count('ci/prepare_android_gradle.py verify') != 2:
        raise ContractFailure('LibVLCJNI source provenance not verified before JVM tests and APK assembly')
    if not (android.index('Install required Android SDK packages (hosted only)') <
            android.index(prepare_name) <
            android.index('Derive APK cache key') <
            android.index('Run JVM unit tests against current source') <
            android.index('Assemble Android debug APK only if inputs changed')):
        raise ContractFailure('LibVLCJNI checkout must precede all Gradle configuration and APK reuse')
    jvm_block = android.split('Run JVM unit tests against current source (never cached)', 1)[1].split('Assemble Android debug APK only if inputs changed', 1)[0]
    build_block = android.split('Assemble Android debug APK only if inputs changed', 1)[1].split('Qualify unchanged or newly built APK and checksums', 1)[0]
    for block in (jvm_block, build_block):
        if 'python3 -B ci/prepare_android_gradle.py verify' not in block or block.index('ci/prepare_android_gradle.py verify') > block.index('bash ci/gradle_dependency_retry.sh'):
            raise ContractFailure('Gradle invoked without source-locked LibVLCJNI project verification')
    # The Maven Central dependency resolver can yield transient, negative
    # classpath lookups. Retry only this diagnosed failure, never JVM tests or
    # compilation. Every attempt uses real Gradle CLI and native diagnostics.
    if (android.count('bash ci/gradle_dependency_retry.sh test') != 1
            or android.count('bash ci/gradle_dependency_retry.sh assemble') != 1):
        raise ContractFailure('bounded Gradle dependency resolver missing or duplicated')
    retry = ROOT / 'ci/gradle_dependency_retry.sh'
    if not retry.is_file() or retry.is_symlink():
        raise ContractFailure('source-owned Gradle retry script missing or symlinked')
    retry_text = retry.read_text('utf-8')
    for required in ('for attempt in 1 2 3', 'flags+=(--refresh-dependencies)',
                     "Could not resolve all artifacts for configuration 'classpath'.",
                     'Searched in the following locations:',
                     'https://repo.maven.apache.org/maven2/',
                     "grep -Eq '^> Task '",
                     'VLC_GRADLE_NON_CLASSPATH_FAILURE',
                     'VLC_GRADLE_REMOTE_CLASSPATH_UNAVAILABLE',
                     "test) task=':application:app:testDebugUnitTest'",
                     "assemble) task=':application:app:assembleDebug'",
                     'gradle "${flags[@]}" "$task" 2>&1 | tee "$log"'):
        if required not in retry_text:
            raise ContractFailure('Gradle fail-closed network retry guard missing: '+required)
    prep = ROOT / 'ci/prepare_android_gradle.py'
    if not prep.is_file() or prep.is_symlink():
        raise ContractFailure('source-bound LibVLCJNI checkout verifier missing or symlinked')
    prep_text = prep.read_text('utf-8')
    for required in ("SOURCE_URL = 'https://code.videolan.org/videolan/libvlcjni.git'",
                     "SOURCE_BRANCH = 'libvlcjni-3.x'", 'load_lock(root)',
                     "'--detach', pin", "'rev-parse', 'HEAD'", "'remote', 'get-url', 'origin'",
                     "'libvlc/build.gradle'", "'status', '--porcelain=v1', '--untracked-files=no'"):
        if required not in prep_text:
            raise ContractFailure('LibVLCJNI upstream provenance/source integrity guard missing: '+required)
    if "subprocess.run(['git', 'clone'" not in prep_text:
        raise ContractFailure('LibVLCJNI must be a real upstream Git checkout, not a stub')
    apk_gate = ROOT / 'ci/apk_reuse.py'
    if not apk_gate.is_file() or apk_gate.is_symlink():
        raise ContractFailure('source-owned APK provenance validator missing')
    for key in ('fingerprint_tree', 'source_fingerprint', 'verify_apk',
                'patched_aar_sha256', 'jvm_tests', 'APK SHA256 mismatch'):
        if key not in apk_gate.read_text('utf-8'):
            raise ContractFailure('APK validator missing required current-source proof: '+key)
    if ('VLC_RD_MAVEN_BASE_URL' in source or 'continue-on-error:' in source or '|| true' in source):
        raise ContractFailure('external Maven dependency or validation bypass returned')
    if re.search(r'(?m)^\s+if:\s*(?:false|always\(\))\s*$', source):
        raise ContractFailure('unconditional/disabled required job step not allowed')


def check_repository(root: Path) -> None:
    wdir = root / WORKFLOW_DIRECTORY
    if not wdir.is_dir() or wdir.is_symlink():
        raise ContractFailure('workflow directory missing/symlinked')
    paths = sorted((*wdir.glob('*.yml'), *wdir.glob('*.yaml')))
    if not paths or any(not p.is_file() or p.is_symlink() for p in paths):
        raise ContractFailure('unsafe/missing workflow files')
    # Verify lock from repository root, not caller's arbitrary current directory.
    from medialibrary import check_source
    check_source(root)
    # require_workflow_contract uses current dir for lock; caller must use the actual repository.
    require_workflow_contract({p.name: p.read_text('utf-8') for p in paths})
    file = root / POLICY_PATH
    if not file.is_file() or file.is_symlink():
        raise ContractFailure('required CI policy missing or symlinked')
    require_policy(json.loads(file.read_text('utf-8')))


def main() -> int:
    try:
        check_repository(Path.cwd())
    except (ContractFailure, OSError, ValueError, KeyError) as exc:
        print('VLC_CI_CONTRACT_FAIL: ' + str(exc), file=sys.stderr)
        return 1
    print('VLC_CI_CONTRACT_PASS workflow_id=' + str(WORKFLOW_ID) + ' hosted_gradle=' + GRADLE_MINIMUM)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
