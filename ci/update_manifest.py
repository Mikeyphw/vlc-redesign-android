#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Exact-byte, APK-signer-bound update metadata; never publishes releases."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import shutil
import sys
from release_qualify import ABIS, RELEASE_IDENTITIES, REPOSITORY, HEX40, HEX64, require, verify_release_apks, expected_version_code, ReleaseRefused

MAX_APK_BYTES = 512 * 1024 * 1024
MAX_MANIFEST_BYTES = 262144


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def manifest_bytes(apks: list[dict], root: Path, *, identity: str, head: str, cert: str, channel: str, notes: str) -> bytes:
    require(identity in RELEASE_IDENTITIES and bool(HEX40.fullmatch(head)), 'unknown source or identity')
    require(channel in ('stable', 'beta') and bool(HEX64.fullmatch(cert)), 'channel or certificate invalid')
    require(len(apks) == len(ABIS) and {a.get('abi') for a in apks} == set(ABIS), 'expected exactly four unique ABI APK receipts')
    versions = {a.get('version_name') for a in apks}
    require(len(versions) == 1, 'mixed release versions')
    version = next(iter(versions))
    require(isinstance(version, str) and bool(re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', version)), 'invalid release version')
    require(isinstance(notes, str) and len(notes.encode()) <= 65536, 'release notes too large')
    assets = []
    for a in sorted(apks, key=lambda a:a['abi']):
        abi = a['abi']; file = f'VLC-Redesign-{identity}-{version}-{abi}.apk'
        p = root / file
        require(a.get('apk') == file and a.get('release_identity') == identity and a.get('application_id') == RELEASE_IDENTITIES[identity], 'APK edition mismatch')
        require(a.get('signer_sha256') == cert and a.get('min_sdk') == 21 and a.get('target_sdk') == 36, 'APK signer or SDK mismatch')
        require(a.get('version_code') == expected_version_code(version, abi), 'APK version mismatch')
        require(p.is_file() and not p.is_symlink() and 0 < p.stat().st_size <= MAX_APK_BYTES, 'APK absent or size invalid')
        digest = sha256(p)
        require(digest == a.get('sha256'), 'APK bytes changed after qualification')
        assets.append(dict(abi=abi,file=file,versionCode=a['version_code'],sha256=digest,size=p.stat().st_size,minSdk=a['min_sdk']))
    payload = dict(schema=1, repository=REPOSITORY, edition=identity, packageName=RELEASE_IDENTITIES[identity],
                   channel=channel, versionName=version, sourceCommit=head, signingCertificateSha256=cert, notes=notes, assets=assets)
    encoded = (json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8')
    require(len(encoded) <= MAX_MANIFEST_BYTES, 'manifest too large')
    return encoded


def paths(out: Path, identity: str) -> tuple[Path, Path, Path]:
    return tuple(out / f'update-{identity}.{suffix}' for suffix in ('json','sig','cer'))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=('sign','verify','stage'))
    p.add_argument('--apk-dir', type=Path, required=True)
    p.add_argument('--out-dir', type=Path, required=True)
    p.add_argument('--identity', choices=sorted(RELEASE_IDENTITIES), required=True)
    p.add_argument('--head', required=True)
    p.add_argument('--cert', required=True)
    p.add_argument('--channel', choices=('stable','beta'), required=True)
    p.add_argument('--notes', type=Path, required=True)
    p.add_argument('--staging-dir', type=Path)
    a = p.parse_args()
    try:
        require(os.environ.get('GITHUB_SHA') == a.head and os.environ.get('GITHUB_REPOSITORY') == REPOSITORY and os.environ.get('GITHUB_REF') == 'refs/heads/main', 'runner source identity drift')
        tools = Path(os.environ.get('ANDROID_HOME','')) / 'build-tools/36.0.0'
        apks = verify_release_apks(a.apk_dir, str(tools/'aapt'), str(tools/'apksigner'), a.cert, a.identity)
        body = manifest_bytes(apks, a.apk_dir, identity=a.identity, head=a.head, cert=a.cert, channel=a.channel, notes=a.notes.read_text('utf-8'))
        files = paths(a.out_dir, a.identity)
        if a.command == 'sign':
            a.out_dir.mkdir(parents=True,exist_ok=False)
            with files[0].open('xb') as f: f.write(body)
        else:
            require(all(f.is_file() and not f.is_symlink() for f in files), 'manifest artifacts missing')
            require(files[0].read_bytes() == body, 'signed manifest does not match requalified APK receipts')
        subprocess.run(['java', str(Path(__file__).with_name('UpdateManifestSigner.java')), 'sign' if a.command == 'sign' else 'verify', *map(str,files),a.cert],check=True,timeout=90)
        if a.command == 'stage':
            stage = a.staging_dir
            require(stage is not None and stage.is_dir() and not stage.is_symlink(), 'missing verified staging directory')
            provenance = json.loads((stage/'release-provenance.json').read_text('utf-8'))
            require(provenance.get('commit') == a.head and provenance.get('release_identity') == a.identity and provenance.get('apks') == apks, 'staged receipts do not match signed manifest')
            for file in files:
                require(not (stage/file.name).exists(), 'manifest destination already exists')
                shutil.copyfile(file, stage/file.name)
            for name in ('release-provenance.json', 'sbom.spdx.json', 'RELEASE_ACCEPTANCE.md'):
                path = stage/name
                dest = stage/f'{a.identity}-{name}'
                require(path.is_file() and not path.is_symlink() and not dest.exists(), 'missing or conflicting release report')
                path.rename(dest)
            sums = [f'{sha256(p)}  {p.name}' for p in sorted(stage.iterdir()) if p.is_file() and p.name != 'SHA256SUMS']
            sums.extend(f"{a['sha256']}  {a['apk']}" for a in apks)
            (stage/'SHA256SUMS').rename(stage/f'{a.identity}-SHA256SUMS')
            (stage/f'{a.identity}-SHA256SUMS').write_text('\n'.join(sums)+'\n',encoding='utf-8')
        print('UPDATE_MANIFEST_'+a.command.upper()+'_PASS', flush=True)
        return 0
    except (ReleaseRefused, OSError, ValueError, subprocess.SubprocessError) as e:
        print('UPDATE_MANIFEST_REFUSED: '+type(e).__name__, file=sys.stderr)
        return 2

if __name__=='__main__':
    raise SystemExit(main())
