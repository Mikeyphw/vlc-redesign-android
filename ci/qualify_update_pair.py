#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Read-only aggregate gate for the two protected staging matrix jobs."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from release_qualify import RELEASE_IDENTITIES, REPOSITORY, PR_WORKFLOW_ID, HEX40, HEX64, require, ReleaseRefused, ABIS, expected_version_code
from update_manifest import paths, manifest_bytes, sha256


def qualify(root: Path, output: Path, *, head: str, run: int, attempt: int, channel: str):
    require(HEX40.fullmatch(head) is not None and run>0 and attempt>0, 'invalid source receipt')
    require(channel in ('stable','beta'), 'invalid channel')
    require(root.is_dir() and not root.is_symlink() and not output.exists(), 'invalid staging paths')
    entries = sorted(root.iterdir())
    expected_dirs = {f'vlc-signed-staging-{i}-{head}' for i in RELEASE_IDENTITIES}
    require({p.name for p in entries}==expected_dirs and all(p.is_dir() and not p.is_symlink() for p in entries), 'both staging identities are required')
    qualified = {}; all_files = {}
    for identity in sorted(RELEASE_IDENTITIES):
        folder=root/f'vlc-signed-staging-{identity}-{head}'
        files={p.name:p for p in folder.rglob('*') if p.is_file()}
        require(not any(p.is_symlink() for p in folder.rglob('*')), 'symlink in stage')
        require(len(files)==len([p for p in folder.rglob('*') if p.is_file()]), 'duplicate staged filename')
        receipt=json.loads(files[f'{identity}-release-provenance.json'].read_text('utf-8'))
        require(receipt.get('schema')=='vlc-redesign-release-staging.v3' and receipt.get('repository')==REPOSITORY and receipt.get('branch')=='main' and receipt.get('commit')==head and receipt.get('source_ci_workflow_id')==PR_WORKFLOW_ID and receipt.get('source_ci_run_id')==run and receipt.get('source_ci_attempt')==attempt and receipt.get('release_identity')==identity and receipt.get('application_id')==RELEASE_IDENTITIES[identity] and receipt.get('official_vlc_update_compatibility')=='NOT_QUALIFIED' and receipt.get('release_status')=='SIGNED_STAGING_ONLY_NOT_PUBLISHED_OR_DEVICE_QUALIFIED', 'stage provenance mismatch')
        apks=receipt['apks']; require(len(apks)==4 and {a['abi'] for a in apks}==set(ABIS), 'incomplete ABI set')
        mpath=files[f'update-{identity}.json']; sig=files[f'update-{identity}.sig']; cer=files[f'update-{identity}.cer']
        manifest=json.loads(mpath.read_bytes()); cert=manifest['signingCertificateSha256']; version=manifest['versionName']
        require(isinstance(cert,str) and HEX64.fullmatch(cert) is not None and isinstance(version,str), 'invalid certificate or version')
        # All APKs are in one artifact upload path, not the report path; verify actual bytes individually.
        apkdir=files[apks[0]['apk']].parent
        require(all(files[a['apk']].parent==apkdir for a in apks), 'unexpected APK layout')
        require(mpath.read_bytes()==manifest_bytes(apks,apkdir,identity=identity,head=head,cert=cert,channel=channel,notes=manifest['notes']), 'manifest metadata mismatch')
        subprocess.run(['java',str(Path(__file__).with_name('UpdateManifestSigner.java')),'verify',str(mpath),str(sig),str(cer),cert],check=True,timeout=90)
        names={a['apk'] for a in apks}|{f'update-{identity}.{s}' for s in ('json','sig','cer')}|{f'{identity}-{n}' for n in ('release-provenance.json','sbom.spdx.json','RELEASE_ACCEPTANCE.md','SHA256SUMS')}
        require(set(files)==names, 'unexpected or missing staged files')
        sums=files[f'{identity}-SHA256SUMS']; seen=set()
        for line in sums.read_text('utf-8').splitlines():
            match=re.fullmatch(r'([0-9a-f]{64})  ([A-Za-z0-9_.-]+)',line)
            require(match is not None,'invalid SHA256SUMS entry')
            digest,name=match.groups();require(name in names-{sums.name} and name not in seen and sha256(files[name])==digest,'checksum mismatch');seen.add(name)
        require(seen==names-{sums.name}, 'incomplete SHA256SUMS')
        require(not (set(all_files)&names),'ambiguous asset names')
        all_files.update(files); qualified[identity]={'version':version,'signer':cert,'notes':manifest['notes'],'media_lock_sha256':receipt['media_lock_sha256'],'apks':len(apks)}
    require(qualified['standalone']==qualified['original'],'release editions disagree on version, signing identity, notes or media source')
    output.mkdir(parents=True)
    for name,path in sorted(all_files.items()):shutil.copyfile(path,output/name)
    result={'schema':'vlc-redesign-update-pair.v1','repository':REPOSITORY,'commit':head,'source_ci_run_id':run,'source_ci_attempt':attempt,'channel':channel,'version':qualified['standalone']['version'],'signer':qualified['standalone']['signer'],'identities':sorted(qualified),'apk_count':8,'status':'SIGNED_STAGING_ONLY_NOT_PUBLISHED_OR_DEVICE_QUALIFIED'}
    (output/'release-pair.json').write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
    (output/'SHA256SUMS').write_text(''.join(f'{sha256(p)}  {p.name}\n' for p in sorted(output.iterdir())))
    print('VLC_M9_M10_PAIRED_STAGING_VERIFIED',head,channel,'8 APKs')
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--head',required=True);p.add_argument('--run-id',type=int,required=True);p.add_argument('--attempt',type=int,required=True);p.add_argument('--channel',required=True,choices=('stable','beta'));a=p.parse_args()
    try:
        qualify(a.root,a.output,head=a.head,run=a.run_id,attempt=a.attempt,channel=a.channel);return 0
    except (OSError,KeyError,ValueError,TypeError,subprocess.SubprocessError) as e:
        print('VLC_RELEASE_PAIR_REFUSED:',type(e).__name__,str(e) if isinstance(e,ReleaseRefused) else '',file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
