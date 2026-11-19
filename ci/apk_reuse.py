#!/usr/bin/env python3
"""Fail-closed content-addressed APK reuse; current JVM tests are never cached.

This is an artifact gate, not a build replacement, signing system, or attestation.
It stores only checked debug APK bytes and a source/toolchain/Maven receipt.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ABI = 'debug'
SCHEMA = 1
ENVIRONMENT = {'os': 'ubuntu-24.04', 'jdk': 'temurin-17', 'gradle': '9.6.0',
               'platform': 'android-36', 'build_tools': '36.0.0', 'ndk': '21.4.7075529',
               'tests': ':application:app:testDebugUnitTest', 'variant': 'assembleDebug'}
MAVEN_REL = 'org/videolan/android/medialibrary-all/0.13.24-rd1/medialibrary-all-0.13.24-rd1.aar'
POM_REL = MAVEN_REL[:-4]+'.pom'
PROVENANCE_REL = MAVEN_REL.rsplit('/',1)[0]+'/provenance.json'
REPO_NAME = 'Mikeyphw/vlc-redesign-android'
SHA = re.compile(r'[0-9a-f]{64}\Z')


class ReuseError(ValueError):
    pass


def refuse(message: str) -> None:
    raise ReuseError(message)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(data: dict) -> bytes:
    return (json.dumps(data, sort_keys=True, separators=(',', ':'), ensure_ascii=True)+'\n').encode()


def relevant_source(path: str) -> bool:
    # Git metadata, CI, and ordinary docs never enter the APK. Any unrecognized
    # file is conservatively included. Test/build inputs are always included.
    if path in ('UPSTREAM.md', 'COPYING') or path.startswith(('ci/', 'docs/', '.github/')):
        return False
    return not (path == 'README.md' or path == '.gitignore')


def fingerprint_tree(blob: bytes) -> str:
    records = []
    for entry in blob.split(b'\0'):
        if not entry:
            continue
        try:
            left, raw_path = entry.split(b'\t', 1)
            mode, kind, oid = left.decode('ascii').split(' ')
            path = raw_path.decode('utf-8', 'strict')
        except (ValueError, UnicodeError) as exc:
            raise ReuseError('unsafe git tree entry') from exc
        if ('\x00' in path or path.startswith('/') or '\\' in path
                or '..' in Path(path).parts or mode not in ('100644', '100755', '120000', '160000')
                or kind not in ('blob', 'commit') or not re.fullmatch(r'[0-9a-f]{40,64}', oid)):
            refuse('invalid tracked source object')
        if relevant_source(path):
            records.append((path, mode, kind, oid))
    if not records:
        refuse('no tracked Android build inputs found')
    return digest(canonical({'schema': SCHEMA, 'source': sorted(records)}))


def source_fingerprint(root: Path) -> str:
    output = subprocess.run(['git', '-C', str(root), 'ls-tree', '-r', '-z', 'HEAD'],
                            capture_output=True, check=True, timeout=30).stdout
    return fingerprint_tree(output)


def regular(path: Path) -> bytes:
    if not path.is_file() or path.is_symlink():
        refuse('missing or symlinked artifact: '+str(path))
    return path.read_bytes()


def inputs(root: Path, maven: Path, runner_image: str) -> dict:
    if not re.fullmatch(r'[A-Za-z0-9_.-]{3,80}', runner_image or ''):
        refuse('missing or unsafe GitHub runner image version')
    aar = regular(maven / MAVEN_REL)
    if not (1024 < len(aar) < 100 * 1024 * 1024):
        refuse('missing or incorrect patched Maven AAR')
    with zipfile.ZipFile(maven/MAVEN_REL) as z:
        if z.testzip() is not None or 'classes.jar' not in z.namelist():
            refuse('corrupt or missing Maven AAR Java contents')
    # Gradle resolves the POM's dependency graph as well as the AAR bytes.
    # Binding only the AAR would let a different POM reuse an incompatible APK.
    pom = regular(maven / POM_REL)
    provenance = regular(maven / PROVENANCE_REL)
    if not pom or not provenance:
        refuse('Maven POM or source receipt unavailable')
    return {'schema': SCHEMA, 'repository': REPO_NAME, 'source_tree_sha256': source_fingerprint(root),
            'patched_aar_sha256': digest(aar), 'patched_pom_sha256': digest(pom),
            'maven_receipt_sha256': digest(provenance),
            'runner_image': runner_image, 'toolchain': ENVIRONMENT}


def cache_identity(root: Path, maven: Path, runner_image: str) -> dict:
    data = inputs(root, maven, runner_image)
    return {'key': 'vlc-debug-apk-v1-' + digest(canonical(data)), 'inputs': data}


def verify_apk(blob: bytes) -> None:
    if not blob or len(blob) > 250 * 1024 * 1024:
        refuse('empty or oversized cached debug APK')
    import io
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            names = z.namelist()
            if (len(names) != len(set(names)) or z.testzip() is not None
                    or 'AndroidManifest.xml' not in names
                    or not any(re.fullmatch(r'classes\d*\.dex', n) for n in names)):
                refuse('debug APK archive missing Android manifest, DEX or integrity')
    except zipfile.BadZipFile as exc:
        raise ReuseError('debug APK is not a ZIP archive') from exc


def receipt_file(cache: Path) -> Path:
    return cache / 'receipt.json'


def verify(cache: Path, identity: dict) -> dict:
    if cache.is_symlink() or not cache.is_dir():
        refuse('APK cache directory missing or symlinked')
    cache=cache.resolve(strict=True)
    meta=json.loads(regular(receipt_file(cache)).decode('utf-8'))
    if (not isinstance(meta, dict) or set(meta) != {'schema','inputs','cache_key','apk_files_sha256','jvm_tests'}
            or meta['schema'] != SCHEMA or meta['inputs'] != identity['inputs']
            or meta['cache_key'] != identity['key'] or meta['jvm_tests'] != 'passed'):
        refuse('APK receipt cannot qualify current build source, toolchain, Maven and tests')
    files=meta['apk_files_sha256']
    if not isinstance(files, dict) or not files or len(files)>12:
        refuse('missing or excessive APK list')
    present=set(p.name for p in cache.iterdir())
    if present != set(files) | {'receipt.json'}:
        refuse('unexpected or missing file in restored APK cache')
    for name, claimed in files.items():
        if not re.fullmatch(r'[A-Za-z0-9._-]+\.apk', name) or not SHA.fullmatch(str(claimed)):
            refuse('unsafe APK filename or receipt digest')
        data=regular(cache/name)
        if digest(data) != claimed:
            refuse('cached APK SHA256 mismatch')
        verify_apk(data)
    return meta


def seal(cache: Path, apk_dir: Path, identity: dict) -> dict:
    if cache.exists() or cache.is_symlink():
        refuse('refuse overwriting an existing cached APK package')
    sources=sorted(p for p in apk_dir.rglob('*.apk') if p.is_file() and not p.is_symlink())
    if not sources or len(sources)>12:
        refuse('no build APKs or unexpectedly many APK outputs')
    cache.mkdir(parents=True, mode=0o700)
    checks={}
    for path in sources:
        if path.name in checks:
            refuse('duplicate APK basename')
        blob=regular(path)
        verify_apk(blob)
        checks[path.name]=digest(blob)
        (cache/path.name).write_bytes(blob)
    meta={'schema': SCHEMA,'inputs': identity['inputs'],'cache_key': identity['key'],
          'apk_files_sha256': checks,'jvm_tests':'passed'}
    receipt_file(cache).write_bytes(canonical(meta))
    verify(cache, identity)
    return meta


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['key', 'seal', 'verify'])
    p.add_argument('--root',type=Path,default=ROOT)
    p.add_argument('--maven',type=Path,default=Path('ci/_maven/repository'))
    p.add_argument('--cache',type=Path,default=Path('ci/_cache/debug-apk'))
    p.add_argument('--apk-dir',type=Path,default=Path('application/app/build/outputs/apk/debug'))
    p.add_argument('--runner-image',required=True)
    a=p.parse_args()
    try:
        identity=cache_identity(a.root,a.maven,a.runner_image)
        data=identity if a.mode=='key' else verify(a.cache,identity) if a.mode=='verify' else seal(a.cache,a.apk_dir,identity)
        print(json.dumps(data,sort_keys=True))
        return 0
    except (ReuseError,OSError,ValueError,subprocess.CalledProcessError,subprocess.TimeoutExpired,zipfile.BadZipFile) as exc:
        print('VLC_APK_REUSE_REFUSED: '+str(exc),file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())
