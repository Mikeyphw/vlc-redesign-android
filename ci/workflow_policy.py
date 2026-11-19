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
                 ':application:app:testDebugUnitTest :application:app:assembleDebug',
                 'docker pull "$VLC_IMAGE"', 'sha256:'):
        must_have(source, code, 'source-built patched Maven workflow')
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
            source.index('gradle --no-daemon', source.index('  android-debug:'))):
        raise ContractFailure('Gradle is not gated on a verified local Maven AAR')
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
