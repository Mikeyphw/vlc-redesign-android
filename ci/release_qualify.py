#!/usr/bin/env python3
"""M7: read-only CI provenance and signed-APK release qualification.

No secrets are stored in source, artifacts or reports. Publication is a separately
reviewed, manual action. This file is NOT a Devtool transaction/overlay engine.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.error
import urllib.request
from zipfile import ZipFile

REPOSITORY = 'Mikeyphw/vlc-redesign-android'
PR_WORKFLOW_ID = 422964106
REQUIRED_CI_JOBS = frozenset((
    'Native source contracts',
    'Patched MediaLibrary native (armeabi-v7a)',
    'Patched MediaLibrary native (arm64-v8a)',
    'Patched MediaLibrary native (x86)',
    'Patched MediaLibrary native (x86_64)',
    'Verified patched Maven AAR (four ABIs)',
    'Android hosted debug APK + JVM tests',
))
ABIS = {'armeabi-v7a': 5, 'arm64-v8a': 6, 'x86': 7, 'x86_64': 8}
HEX40 = re.compile(r'[0-9a-f]{40}\Z')
HEX64 = re.compile(r'[0-9a-f]{64}\Z')
API = f'https://api.github.com/repos/{REPOSITORY}'


class ReleaseRefused(ValueError):
    pass


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ReleaseRefused(reason)


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()


def require_release_workflow_contract(text: str) -> None:
    """Reject privileged events, signing in PR jobs and unreviewed release DAGs.

    Only the explicit separate manual staged-release workflow is permitted.
    A workflow syntax mistake must fail the PR source contract, not go unnoticed.
    """
    require(bool(text), 'M7 separate release workflow absent')
    require(bool(re.search(r'(?m)^name: VLC staged signed release qualification\s*$', text)), 'release workflow identity drift')
    require(bool(re.search(r'(?m)^on:\s*\n  workflow_dispatch:\s*\n', text)), 'release must be manual dispatch')
    on_block = text.split('\non:', 1)[-1].split('\npermissions:', 1)[0]
    require(not re.search(r'(?m)^\s+(pull_request|pull_request_target|push|schedule|workflow_run|repository_dispatch):', on_block),
            'unexpected privileged/automatic release trigger')
    require('permissions:\n  contents: read\n  actions: read' in text, 'release token must be read-only')
    require(not re.search(r'(?m)^\s+(contents|actions|id-token|pull-requests|issues|workflows): write\b', text),
            'release workflow elevated token permissions')
    for item in ('verify-source:', 'release-staging:', 'needs: verify-source', 'environment: vlc-release',
                 'persist-credentials: false', 'ci/release_qualify.py source',
                 'ci/release_qualify.py signing-env', 'ci/release_qualify.py apks',
                 'ci/prepare_android_gradle.py prepare', 'ci/prepare_android_gradle.py verify',
                 'ci/medialibrary.py verify-maven', 'assembleSignedRelease',
                 'run-id: ${{ inputs.source_ci_run_id }}',
                 'github-token: ${{ github.token }}',
                 'name: patched-medialibrary-maven', 'pattern: mla-*',
                 'RD_RELEASE_KEYSTORE_B64: ${{ secrets.RD_RELEASE_KEYSTORE_B64 }}',
                 'RD_RELEASE_CERT_SHA256: ${{ vars.RD_RELEASE_CERT_SHA256 }}',
                 'if-no-files-found: error', 'actions/upload-artifact@v4'):
        require(item in text, 'release workflow required guard missing: '+item)
    # Ensure signing is limited to the environment-protected job.
    before, after = text.split('\n  release-staging:', 1)
    require('secrets.' not in before and 'environment: vlc-release' in after,
            'signing secrets escaped the environment-protected job')
    require('secrets.' not in after.split('      - name: Check signed APKs', 1)[-1],
            'signing secrets must not be used by later artifact/verification steps')
    require('continue-on-error:' not in text and '|| true' not in text,
            'release qualification bypass is forbidden')


def _api_json(path: str, token: str) -> dict:
    require(bool(token), 'GITHUB_TOKEN missing for read-only provenance')
    require(path.startswith('/'), 'invalid API path')
    req = urllib.request.Request(API + path, headers={
        'Authorization': 'Bearer ' + token,
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'vlc-redesign-m7-qualifier/1',
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            data = response.read(3_000_000)
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ReleaseRefused('GitHub provenance lookup failed') from exc
    require(len(data) < 3_000_000, 'oversized API response')
    try:
        decoded = json.loads(data)
    except (ValueError, UnicodeError) as exc:
        raise ReleaseRefused('invalid GitHub API JSON') from exc
    require(isinstance(decoded, dict), 'unexpected GitHub API response')
    return decoded


def validate_source_run(run: dict, jobs: dict, main: dict, *, head: str, run_id: int, repo: str, ref: str) -> dict:
    """Pure verifier, including exact run attempt and all non-skipped required jobs."""
    require(repo == REPOSITORY and ref == 'refs/heads/main', 'release only from original fork main')
    require(bool(HEX40.fullmatch(head)), 'expected Git commit SHA malformed')
    require((main.get('object') or {}).get('sha') == head, 'remote main has moved')
    require(run.get('id') == run_id and run.get('workflow_id') == PR_WORKFLOW_ID,
            'release source CI run identity mismatch')
    require(run.get('event') == 'workflow_dispatch' and run.get('head_branch') == 'main',
            'source CI must be dispatched on main, not taken from a PR')
    require(run.get('head_sha') == head and (run.get('repository') or {}).get('full_name') == REPOSITORY,
            'source CI repository/commit does not match release')
    require(run.get('status') == 'completed' and run.get('conclusion') == 'success',
            'source CI run incomplete or unsuccessful')
    attempt = run.get('run_attempt')
    require(type(attempt) is int and attempt >= 1, 'source CI attempt invalid')
    items = jobs.get('jobs')
    require(type(items) is list and jobs.get('total_count') == len(items) and len(items) <= 100,
            'source CI job inventory incomplete/paginated')
    names = [j.get('name') for j in items]
    require(set(names) >= REQUIRED_CI_JOBS and all(names.count(n) == 1 for n in REQUIRED_CI_JOBS),
            'source CI missing or duplicated mandatory job')
    require(all(j.get('status') == 'completed' and j.get('conclusion') == 'success'
                and j.get('run_attempt') == attempt for j in items),
            'source CI skipped/neutral/failed or from another run attempt')
    return {'repository': REPOSITORY, 'head_sha': head, 'ci_run_id': run_id,
            'ci_attempt': attempt, 'required_jobs': sorted(REQUIRED_CI_JOBS)}


def check_source(args: argparse.Namespace) -> dict:
    token = os.environ.get('GITHUB_TOKEN', '')
    require(isinstance(args.run_id, int) and 0 < args.run_id < 10**18, 'invalid CI run id')
    require(args.head == os.environ.get('GITHUB_SHA') and args.ref == os.environ.get('GITHUB_REF'),
            'release arguments do not match GitHub runner context')
    require(os.environ.get('GITHUB_REPOSITORY') == REPOSITORY, 'runner repository mismatch')
    run = _api_json(f'/actions/runs/{args.run_id}', token)
    attempt = run.get('run_attempt')
    require(type(attempt) is int and 0 < attempt <= 1000, 'invalid current CI attempt')
    jobs = _api_json(f'/actions/runs/{args.run_id}/attempts/{attempt}/jobs?per_page=100', token)
    main = _api_json('/git/ref/heads/main', token)
    result = validate_source_run(run, jobs, main, head=args.head, run_id=args.run_id,
                                 repo=os.environ.get('GITHUB_REPOSITORY', ''), ref=args.ref)
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as receipt:
            receipt.write('ci_attempt='+str(result['ci_attempt'])+'\n')
    print('VLC_M7_EXACT_MAIN_CI_PASS '+json.dumps(result, sort_keys=True))
    return result


def check_signing_env(env: dict[str, str]) -> None:
    for name in ('RD_RELEASE_KEYSTORE_B64', 'RD_KEYSTORE_PASSWORD', 'RD_KEY_ALIAS',
                 'RD_KEY_PASSWORD', 'RD_RELEASE_CERT_SHA256'):
        require(bool(env.get(name, '').strip()), 'required private signing input missing: '+name)
    fingerprint = env['RD_RELEASE_CERT_SHA256'].lower().replace(':', '').strip()
    require(bool(HEX64.fullmatch(fingerprint)), 'approved certificate SHA-256 is malformed')
    try:
        decoded = base64.b64decode(env['RD_RELEASE_KEYSTORE_B64'], validate=True)
    except ValueError as exc:
        raise ReleaseRefused('invalid base64-encoded signing keystore') from exc
    require(1024 <= len(decoded) <= 2_000_000, 'keystore size outside safe bounds')
    del decoded


def _run(argv: list[str]) -> str:
    proc = subprocess.run(argv, capture_output=True, text=True, check=False, timeout=40)
    if proc.returncode:
        raise ReleaseRefused('artifact inspection failed: '+Path(argv[0]).name)
    return proc.stdout + '\n' + proc.stderr


def parse_badging(text: str) -> dict:
    pkg = re.search(r"(?m)^package: name='([^']+)' versionCode='(\d+)' versionName='([^']+)'", text)
    min_sdk = re.search(r"(?m)^sdkVersion:'(\d+)'", text)
    target = re.search(r"(?m)^targetSdkVersion:'(\d+)'", text)
    native = re.search(r"(?m)^native-code:(.*)$", text)
    require(all((pkg, min_sdk, target, native)), 'APK badging fields missing')
    return {'package': pkg.group(1), 'version_code': int(pkg.group(2)),
            'version_name': pkg.group(3), 'min_sdk': int(min_sdk.group(1)),
            'target_sdk': int(target.group(1)), 'abis': re.findall(r"'([^']+)'", native.group(1))}


def parse_signer(text: str) -> str:
    x = re.findall(r'(?mi)^Signer #\d+ certificate SHA-256 digest:\s*([0-9a-f: ]+)\s*$', text)
    require(len(x) == 1, 'APK must have exactly one signing certificate')
    digest = x[0].replace(':', '').replace(' ', '').lower()
    require(bool(HEX64.fullmatch(digest)), 'certificate digest malformed')
    for scheme in ('v1 scheme', 'v2 scheme'):
        require(bool(re.search(r'(?mi)^Verified using '+scheme+r'[^:]*:\s*true\s*$',text)),
                'required APK signature scheme is not verified: '+scheme)
    return digest


def expected_version_code(name: str, abi: str) -> int:
    version = re.fullmatch(r'(\d+)\.(\d+)\.(\d+)', name)
    require(bool(version), 'release version is not semantic three-component version')
    major, minor, patch = map(int, version.groups())
    require(major <= 10 and minor < 100 and patch < 100,
            'release version incompatible with upstream version code scheme')
    return 10_000_000 + 3_100_000 + 10 * (major * 10_000 + minor * 100 + patch) + ABIS[abi]


def parse_dependencies(text: str) -> list[dict]:
    require('signedReleaseRuntimeClasspath' in text and 'FAILED' not in text
            and 'Could not resolve' not in text, 'dependency resolution incomplete')
    packages = {}
    for raw in text.splitlines():
        match = re.search(r'([\w.-]+):([\w.-]+):([\w.+-]+)(?:\s+->\s+([\w.+-]+))?', raw)
        if match and ('---' in raw or ' (c)' in raw):
            group, name, original, resolved = match.groups()
            version = resolved or original
            if version and version[0].isdigit():
                packages[(group, name, version)] = {
                    'SPDXID': 'SPDXRef-dep-'+hashlib.sha256(f'{group}:{name}:{version}'.encode()).hexdigest()[:20],
                    'name': f'{group}:{name}', 'versionInfo': version,
                    'downloadLocation': 'NOASSERTION', 'filesAnalyzed': False,
                    'licenseConcluded': 'NOASSERTION', 'licenseDeclared': 'NOASSERTION',
                    'copyrightText': 'NOASSERTION'}
    require(len(packages) >= 10, 'resolved dependency inventory unexpectedly empty/incomplete')
    return [packages[k] for k in sorted(packages)]


def verify_release_apks(root: Path, aapt: str, apksigner: str, expected_cert: str) -> list[dict]:
    require(root.is_dir() and not root.is_symlink(), 'missing signedRelease APK directory')
    files = sorted(root.glob('*.apk'))
    require(len(files) == 4 and all(p.is_file() and not p.is_symlink() for p in files),
            'expected exactly four regular ABI signed APKs')
    expected_cert = expected_cert.lower().replace(':', '')
    require(bool(HEX64.fullmatch(expected_cert)), 'configured release signer fingerprint invalid')
    versions = set()
    found = set()
    receipts = []
    for apk in files:
        match = re.fullmatch(r'VLC-Android-(\d+\.\d+\.\d+)-(armeabi-v7a|arm64-v8a|x86|x86_64)\.apk',apk.name)
        require(bool(match), 'unexpected APK output filename')
        ver, abi = match.groups()
        require(abi not in found, 'duplicate ABI APK')
        found.add(abi)
        metadata = parse_badging(_run([aapt, 'dump', 'badging', str(apk)]))
        require(metadata['package'] == 'com.mikeyphw.vlcredesign', 'release application ID drift')
        require(metadata['version_name'] == ver, 'APK versionName mismatch')
        require(metadata['version_code'] == expected_version_code(ver, abi), 'non-monotonic or incorrect ABI versionCode')
        require(metadata['min_sdk'] == 21 and metadata['target_sdk'] == 36, 'SDK support drift')
        require(metadata['abis'] == [abi], 'split APK native code does not match filename ABI')
        signer = parse_signer(_run([apksigner, 'verify', '--min-sdk-version', '21',
                                   '--verbose', '--print-certs', str(apk)]))
        require(signer == expected_cert, 'signing certificate differs from approved fingerprint')
        sha = hashlib.sha256(apk.read_bytes()).hexdigest()
        versions.add(ver)
        receipts.append({'apk': apk.name, 'sha256': sha, 'abi': abi, 'signer_sha256': signer,
                         'version_name': ver, 'version_code': metadata['version_code'],
                         'min_sdk': metadata['min_sdk'], 'target_sdk': metadata['target_sdk']})
    require(found == set(ABIS) and len(versions) == 1, 'not all release ABIs share one version')
    return receipts


def write_reports(args: argparse.Namespace) -> None:
    head = args.head
    require(bool(HEX40.fullmatch(head)) and args.ref == 'refs/heads/main', 'reports must bind main HEAD')
    require(os.environ.get('GITHUB_SHA') == head and os.environ.get('GITHUB_REPOSITORY') == REPOSITORY,
            'report runner identity drift')
    tools = Path(os.environ.get('ANDROID_HOME', ''))/'build-tools/36.0.0'
    require(tools.is_dir(), 'expected Android 36.0.0 tools not installed')
    packages = parse_dependencies(Path(args.dependencies).read_text('utf-8'))
    apks = verify_release_apks(Path(args.apk_dir), str(tools/'aapt'), str(tools/'apksigner'), args.cert)
    root = Path.cwd()
    lock = root/'ci/medialibrary.lock.json'
    require(lock.is_file() and not lock.is_symlink(), 'native source lock missing')
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=False)
    ci_run = int(args.run_id)
    provenance = {'schema': 'vlc-redesign-release-staging.v1', 'repository': REPOSITORY,
                  'commit': head, 'branch': 'main', 'source_ci_workflow_id': PR_WORKFLOW_ID,
                  'source_ci_run_id': ci_run, 'source_ci_attempt': int(args.ci_attempt),
                  'media_lock_sha256': hashlib.sha256(lock.read_bytes()).hexdigest(),
                  'release_status': 'SIGNED_STAGING_ONLY_NOT_PUBLISHED_OR_DEVICE_QUALIFIED',
                  'apks': apks}
    (out/'release-provenance.json').write_text(json.dumps(provenance, sort_keys=True, indent=2)+'\n')
    files = [{'SPDXID': 'SPDXRef-file-'+receipt['abi'].replace('_','-'),
              'fileName': './'+receipt['apk'],
              'checksums': [{'algorithm': 'SHA256', 'checksumValue': receipt['sha256']}],
              'licenseConcluded': 'NOASSERTION', 'licenseInfoInFiles': ['NOASSERTION'],
              'copyrightText': 'NOASSERTION'} for receipt in apks]
    sbom = {'spdxVersion': 'SPDX-2.3', 'dataLicense': 'CC0-1.0', 'SPDXID': 'SPDXRef-DOCUMENT',
            'name': 'vlc-redesign-android-staged-release-'+head[:12],
            'documentNamespace': f'https://github.com/{REPOSITORY}/commit/{head}/release-sbom/{ci_run}/{hashlib.sha256(json.dumps(apks, sort_keys=True).encode()).hexdigest()[:20]}',
            'creationInfo': {'creators': ['Tool: VLC-M7-release-qualify-1.0'],
                             'created': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')},
            'packages': packages, 'files': files,
            'relationships': [{'spdxElementId': 'SPDXRef-DOCUMENT',
                               'relatedSpdxElement': pkg['SPDXID'],
                               'relationshipType': 'DESCRIBES'} for pkg in packages]}
    (out/'sbom.spdx.json').write_text(json.dumps(sbom, sort_keys=True, indent=2)+'\n')
    (out/'RELEASE_ACCEPTANCE.md').write_text(
        '# Staged release — approval required\n\n'
        f'- Source: `{REPOSITORY}` `main` at `{head}`\n'
        f'- Prerequisite read-only CI: run `{ci_run}`, attempt `{args.ci_attempt}`\n'
        f'- Signed APKs: {len(apks)} ABI-specific packages; certificate `{apks[0]["signer_sha256"]}`\n'
        '- Status: **staging only**; no GitHub Release, production rollout or device acceptance.\n'
        '- SBOM records resolved Gradle dependencies and APKs; license/vulnerability review is still mandatory.\n'
        '- Verify installer identity and update compatibility on physical phone/TV, rollback and recovery,\n'
        '  signed artifact download digests, accessibility, casting, DRM and version monotonicity.\n'
        '- Publish only after a separate explicit release approval and the device-install matrix is signed off.\n')
    manifest = []
    for p in sorted(out.iterdir()):
        manifest.append(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name)
    for receipt in apks:
        manifest.append(receipt['sha256']+'  '+receipt['apk'])
    (out/'SHA256SUMS').write_text('\n'.join(manifest)+'\n')
    print('VLC_M7_SIGNED_STAGING_VERIFIED head='+head+' apks='+str(len(apks))+
          ' dependencies='+str(len(packages))+' certificate_sha256='+apks[0]['signer_sha256'])


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    src=sub.add_parser('source')
    src.add_argument('--head',required=True)
    src.add_argument('--ref',required=True)
    src.add_argument('--run-id',type=int,required=True)
    sub.add_parser('signing-env')
    a=sub.add_parser('apks')
    a.add_argument('--head',required=True)
    a.add_argument('--ref',required=True)
    a.add_argument('--run-id',type=int,required=True)
    a.add_argument('--ci-attempt',type=int,required=True)
    a.add_argument('--dependencies',required=True)
    a.add_argument('--apk-dir',required=True)
    a.add_argument('--cert',required=True)
    a.add_argument('--out-dir',required=True)
    args=p.parse_args()
    try:
        if args.command=='source': check_source(args)
        elif args.command=='signing-env': check_signing_env(dict(os.environ));print('VLC_M7_SIGNING_INPUTS_PRESENT (secrets omitted)')
        elif args.command=='apks': write_reports(args)
        else: raise ReleaseRefused('unknown operation')
        return 0
    except (ReleaseRefused,OSError,ValueError,subprocess.TimeoutExpired) as exc:
        print('VLC_M7_RELEASE_REFUSED: '+str(exc),file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())
