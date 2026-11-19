#!/usr/bin/env python3
"""Source-bound KuchiSofts medialibrary pipeline, including cache and AAR gates.

Pure-stdlib checker/packer; compilers are *only* run by pinned VideoLAN CI
containers on hosted Linux. The exact source lock and patched native ELFs are
verified on build, cache restore, Maven assembly and before Android Gradle.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import sys
import tempfile
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / 'ci/medialibrary.lock.json'
ABIS = {'armeabi-v7a': (1, 40), 'arm64-v8a': (2, 183), 'x86': (1, 3), 'x86_64': (2, 62)}
GROUP_PATH = 'org/videolan/android/medialibrary-all'
SHA256 = re.compile(r'[0-9a-f]{64}\Z')
GIT_BLOB = re.compile(r'[0-9a-f]{40}\Z')
# Independently reviewed KuchiSofts 0.7.5 source/blob identities. Any source
# upgrade must change BOTH this contract and the source lock in one reviewed PR.
TRUSTED_MEDIALIBRARY_COMMIT = '8d573499ae79298f772e23bfc46dabf486843c25'
TRUSTED_LIBVLCJNI_COMMIT = '0b8dc65efb203c86a0476bc337ddd99ecf1c0ef6'
TRUSTED_IMAGES = {
    'armeabi-v7a': 'registry.videolan.org/vlc-debian-android-3.0:20260701183656',
    'arm64-v8a': 'registry.videolan.org/vlc-debian-android:20260611225331',
    'x86': 'registry.videolan.org/vlc-debian-android-3.0:20260701183656',
    'x86_64': 'registry.videolan.org/vlc-debian-android:20260611225331',
}
TRUSTED_PATCH_BLOBS = {
    'buildsystem/patches/medialibrary/0001-MetadataAnalyzer-a-cover-stored-as-a-video-track-doe.patch':
        'c268473185113a34b7837aa88b342f53ad299902',
    'buildsystem/patches/libvlcpp/0001-MediaPlayer-always-use-set_time-set_position-fast-ar.patch':
        'ab5ab0ced05481d552222f63e3be7691819a8735',
}


class MediaContractError(ValueError):
    pass


def refuse(message: str) -> None:
    raise MediaContractError(message)


def sha(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def json_bytes(item: dict) -> bytes:
    return (json.dumps(item, indent=2, sort_keys=True, ensure_ascii=True) + '\n').encode('utf-8')


def source_file(path: str, root: Path = ROOT) -> Path:
    if not path or path.startswith('/') or '\\' in path or '..' in Path(path).parts:
        refuse('unsafe source path')
    file = root / path
    if not file.is_file() or file.is_symlink() or not file.resolve().is_relative_to(root.resolve()):
        refuse('source file missing, symlinked or outside repository: ' + path)
    return file


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def load_lock(root: Path = ROOT) -> dict:
    raw = json.loads(source_file('ci/medialibrary.lock.json', root).read_text('utf-8'))
    required = {'schema', 'group', 'module', 'official_version', 'patched_version',
                'medialibrary_commit', 'libvlcjni_commit', 'images', 'patches'}
    if not isinstance(raw, dict) or set(raw) != required or raw['schema'] != 1:
        refuse('unrecognized medialibrary source-lock schema')
    if (raw['group'] != 'org.videolan.android' or raw['module'] != 'medialibrary-all'
            or raw['official_version'] != '0.13.24' or raw['patched_version'] != '0.13.24-rd1'):
        refuse('MediaLibrary Maven identity drift')
    for key in ('medialibrary_commit', 'libvlcjni_commit'):
        if not isinstance(raw[key], str) or not GIT_BLOB.fullmatch(raw[key]):
            refuse('source commit pin invalid: ' + key)
    if (raw['medialibrary_commit'] != TRUSTED_MEDIALIBRARY_COMMIT
            or raw['libvlcjni_commit'] != TRUSTED_LIBVLCJNI_COMMIT
            or raw['images'] != TRUSTED_IMAGES or raw['patches'] != TRUSTED_PATCH_BLOBS):
        refuse('KuchiSofts independently reviewed source/image/patch identity drift')
    for abi, name in raw['images'].items():
        if not isinstance(name, str) or not re.fullmatch(r'registry\.videolan\.org/vlc-debian-android(?:-3\.0)?:\d{14}', name):
            refuse('unrecognized VideoLAN compiler image for ' + abi)
        if (abi in ('armeabi-v7a', 'x86')) != ('-3.0:' in name):
            refuse('wrong VideoLAN compiler image family for ' + abi)
    for path, blob in raw['patches'].items():
        if not GIT_BLOB.fullmatch(str(blob)):
            refuse('patch blob not a Git SHA-1')
        if git_blob(source_file(path, root).read_bytes()) != blob:
            refuse('KuchiSofts patch drift: ' + path)
    return raw


def check_source(root: Path = ROOT) -> dict:
    lock = load_lock(root)
    compile_ml = source_file('buildsystem/compile-medialibrary.sh', root).read_text('utf-8')
    compile_all = source_file('buildsystem/compile.sh', root).read_text('utf-8')
    root_gradle = source_file('build.gradle', root).read_text('utf-8')
    main_gradle = source_file('application/vlc-android/build.gradle', root).read_text('utf-8')
    if not re.search(r'^MEDIALIBRARY_HASH=' + lock['medialibrary_commit'] + r'\s*$', compile_ml, re.M):
        refuse('KuchiSofts MediaLibrary base pin changed')
    if 'git clone http://code.videolan.org/videolan/medialibrary.git' not in compile_ml:
        refuse('KuchiSofts source clone contract changed; requalify TLS rewrite')
    if 'git config --global url."https://code.videolan.org/".insteadOf "http://code.videolan.org/"' not in source_file('ci/build_medialibrary_abi.sh', root).read_text('utf-8'):
        refuse('VideoLAN checkout TLS rewrite missing')
    if not re.search(r'\bLIBVLCJNI_TESTED_HASH=' + lock['libvlcjni_commit'] + r'\b', compile_all):
        refuse('VideoLAN libvlcjni base commit changed')
    if "medialibraryVersion = (vlcMajorVersion == 3 ? '0.13.24-rd1'" not in root_gradle:
        refuse('upstream app MediaLibrary dependency changed')
    if '"org.videolan.android:medialibrary-all:$rootProject.ext.medialibraryVersion"' not in main_gradle:
        refuse('app no longer uses declared patched MediaLibrary dependency')
    if 'System.getenv(\'RD_MAVEN\')' not in root_gradle:
        refuse('upstream Gradle local Maven repository integration removed')
    return lock


def safe_digest(value: str) -> str:
    if not isinstance(value, str) or not SHA256.fullmatch(value):
        refuse('invalid SHA-256 digest')
    return value


def docker_digest(value: str, image: str) -> str:
    if not isinstance(value, str) or not value.startswith(image.split(':')[0] + '@sha256:'):
        refuse('Docker digest must come from the declared VideoLAN registry image')
    safe_digest(value.split('@sha256:', 1)[1])
    return value


def verify_elf(blob: bytes, abi: str) -> None:
    expected_class, machine = ABIS[abi]
    if len(blob) < 64 or blob[:4] != b'\x7fELF' or blob[4] != expected_class or blob[5] != 1:
        refuse('native library is not ELF for ' + abi)
    if struct.unpack_from('<H', blob, 18)[0] != machine or struct.unpack_from('<H', blob, 16)[0] != 3:
        refuse('native ELF architecture/type mismatch: ' + abi)
    if len(blob) > 150 * 1024 * 1024:
        refuse('native ELF exceeds per-ABI size budget')


def inputs_digest(lock: dict) -> str:
    # Stable across unrelated UI edits, but changes with every reviewed source pin.
    return sha(json_bytes(lock))


def abi_location(cache: Path, abi: str) -> Path:
    if abi not in ABIS:
        refuse('unsupported Android ABI')
    return cache / ('mla-' + abi)


def make_receipt(abi: str, *, image: str, native: bytes, lock: dict) -> dict:
    return {'schema': 1, 'abi': abi, 'compiler_image': lock['images'][abi],
            'compiler_digest': docker_digest(image, lock['images'][abi]),
            'inputs_sha256': inputs_digest(lock), 'medialibrary_commit': lock['medialibrary_commit'],
            'libvlcjni_commit': lock['libvlcjni_commit'],
            'library_sha256': sha(native), 'library_bytes': len(native),
            'patches': lock['patches']}


def validate_abi(cache: Path, abi: str, *, compiler_digest: str | None = None,
                 root: Path = ROOT) -> dict:
    lock = check_source(root)
    directory = abi_location(cache, abi)
    native_path = directory / 'libmla.so'
    receipt_path = directory / 'receipt.json'
    if (not native_path.is_file() or native_path.is_symlink() or not receipt_path.is_file()
            or receipt_path.is_symlink() or not directory.is_dir() or directory.is_symlink()):
        refuse('missing or symlinked native library/receipt: ' + abi)
    data = native_path.read_bytes()
    verify_elf(data, abi)
    receipt = json.loads(receipt_path.read_text('utf-8'))
    if not isinstance(receipt, dict):
        refuse('invalid ABI receipt')
    expected = make_receipt(abi, image=receipt.get('compiler_digest'), native=data, lock=lock)
    if receipt != expected or (compiler_digest is not None and receipt['compiler_digest'] != compiler_digest):
        refuse('ABI receipt/cache digest or source mismatch: ' + abi)
    return receipt


def collect_abi(cache: Path, abi: str, native: Path, image: str, root: Path = ROOT) -> dict:
    lock = check_source(root)
    native = native.resolve(strict=True)
    data = native.read_bytes()
    verify_elf(data, abi)
    out = abi_location(cache, abi)
    if out.exists():
        refuse('cannot overwrite previously cached ABI payload')
    receipt = make_receipt(abi, image=image, native=data, lock=lock)
    out.mkdir(parents=True, mode=0o700)
    (out / 'libmla.so').write_bytes(data)
    (out / 'receipt.json').write_bytes(json_bytes(receipt))
    validate_abi(cache, abi, compiler_digest=image, root=root)
    return receipt


def base_checksum_text(text: str) -> str:
    digest = text.strip().split()[0] if text.strip() else ''
    return safe_digest(digest.lower())


def maven_urls(version: str) -> tuple[str, str]:
    base = f'https://repo.maven.apache.org/maven2/{GROUP_PATH}/{version}/medialibrary-all-{version}'
    return base + '.aar', base + '.pom'


def fetch_official(url: str, *, timeout: int = 90) -> bytes:
    if not url.startswith('https://repo.maven.apache.org/maven2/' + GROUP_PATH + '/0.13.24/'):
        refuse('untrusted or unexpected Maven Central URL')
    req = urllib.request.Request(url, headers={'User-Agent': 'vlc-patched-medialibrary-source-gate/1'})
    with urllib.request.urlopen(req, timeout=timeout) as result:
        if result.geturl() != url:
            refuse('Maven Central redirected to another source')
        data = result.read(80 * 1024 * 1024 + 1)
    if len(data) > 80 * 1024 * 1024 or not data:
        refuse('empty or oversized Maven Central artifact')
    return data


def official_files(root: Path = ROOT) -> dict[str, bytes]:
    lock = check_source(root)
    urls = dict(zip(('aar', 'pom'), maven_urls(lock['official_version'])))
    result = {}
    for suffix, url in urls.items():
        binary = fetch_official(url)
        # Maven Central's cryptographic sidecars are authoritative for the
        # versioned Java/AAR baseline. Never downgrade to MD5/SHA-1.
        try:
            signed_digest = base_checksum_text(fetch_official(url + '.sha256').decode('utf-8'))
            if sha(binary) != signed_digest:
                refuse('Maven Central sidecar SHA-256 mismatch: ' + suffix)
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
            digest512 = fetch_official(url + '.sha512').decode('utf-8').strip().split()[0].lower()
            if not re.fullmatch(r'[0-9a-f]{128}\Z', digest512) or hashlib.sha512(binary).hexdigest() != digest512:
                refuse('Maven Central sidecar SHA-512 mismatch: ' + suffix)
        result[suffix] = binary
    return result


def read_official(root: Path) -> dict[str, bytes]:
    record = root / 'official-manifest.json'
    if not record.is_file() or record.is_symlink():
        refuse('missing verified Maven Central baseline receipt')
    manifest = json.loads(record.read_text('utf-8'))
    if set(manifest) != {'schema', 'source', 'files_sha256'} or manifest['schema'] != 1 or manifest['source'] != 'repo.maven.apache.org':
        refuse('official Maven baseline receipt invalid')
    result = {}
    for suffix in ('aar', 'pom'):
        name = 'medialibrary-all-0.13.24.' + suffix
        candidate = root / name
        if not candidate.is_file() or candidate.is_symlink():
            refuse('official Maven baseline is missing or symlinked')
        data = candidate.read_bytes()
        if sha(data) != manifest['files_sha256'].get(name):
            refuse('official Maven baseline checksum drift')
        result[suffix] = data
    if set(manifest['files_sha256']) != {'medialibrary-all-0.13.24.aar', 'medialibrary-all-0.13.24.pom'}:
        refuse('official baseline has unreviewed entries')
    return result


def pom_reversion(blob: bytes, source: str, target: str) -> bytes:
    root = ET.fromstring(blob)
    if root.tag.startswith('{'):
        ns = root.tag.split('}', 1)[0][1:]
        ET.register_namespace('', ns)
        child = lambda tag: root.find('{' + ns + '}' + tag)
    else:
        child = root.find
    group, artifact, version = (child(k) for k in ('groupId', 'artifactId', 'version'))
    if group is None or artifact is None or version is None or (group.text, artifact.text, version.text) != (
            'org.videolan.android', 'medialibrary-all', source):
        refuse('official POM group, module or version mismatches immutable source')
    version.text = target
    return ET.tostring(root, encoding='utf-8', xml_declaration=True) + b'\n'


def assemble_aar(original: bytes, libraries: dict[str, bytes]) -> bytes:
    import io
    if set(libraries) != set(ABIS):
        refuse('every native Android ABI is required')
    with zipfile.ZipFile(io.BytesIO(original)) as base:
        infos = base.infolist()
        names = [info.filename for info in infos]
        if len(names) != len(set(names)) or base.testzip() is not None or len(names) > 20000:
            refuse('duplicate or corrupt official AAR members')
        replaced = set()
        entries = {}
        for info in infos:
            name = info.filename
            if (name.startswith('/') or '\\' in name or '..' in name.split('/')
                    or (info.external_attr >> 16) & 0o170000 == 0o120000):
                refuse('official AAR contains unsafe/symlink member')
            if info.is_dir():
                continue  # ZIP directory records are optional; preserve all files unchanged.
            data = base.read(info)
            for abi in ABIS:
                target = f'jni/{abi}/libmla.so'
                if name == target:
                    replaced.add(abi)
                    verify_elf(libraries[abi], abi)
                    data = libraries[abi]
            entries[name] = data
        if replaced != set(ABIS):
            refuse('official AAR did not contain exactly four expected libmla.so slots')
        if 'classes.jar' not in entries or 'AndroidManifest.xml' not in entries:
            refuse('official AAR missing its Java classes/manifest')
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as dest:
        for name, data in sorted(entries.items()):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            dest.writestr(info, data)
    return stream.getvalue()


def receipt_dir(maven: Path, lock: dict) -> Path:
    return maven / GROUP_PATH / lock['patched_version']


def package_maven(native_cache: Path, output: Path, official: dict[str, bytes],
                  root: Path = ROOT) -> dict:
    lock = check_source(root)
    libs = {abi: (abi_location(native_cache, abi) / 'libmla.so').read_bytes() for abi in ABIS}
    receipts = {abi: validate_abi(native_cache, abi, root=root) for abi in ABIS}
    if set(official) != {'aar', 'pom'}:
        refuse('missing official baseline AAR or POM')
    patched_aar = assemble_aar(official['aar'], libs)
    patched_pom = pom_reversion(official['pom'], lock['official_version'], lock['patched_version'])
    location = receipt_dir(output, lock)
    if location.exists():
        refuse('cannot overwrite an existing packaged Maven artifact')
    location.mkdir(parents=True)
    prefix = 'medialibrary-all-' + lock['patched_version']
    result = {prefix + '.aar': patched_aar, prefix + '.pom': patched_pom}
    meta = {'schema': 1, 'coordinate': lock['group'] + ':' + lock['module'] + ':' + lock['patched_version'],
            'source_lock_sha256': inputs_digest(lock),
            'base_aar_sha256': sha(official['aar']), 'base_pom_sha256': sha(official['pom']),
            'files_sha256': {name: sha(data) for name, data in result.items()},
            'abi_receipts': receipts}
    for name, data in result.items():
        (location / name).write_bytes(data)
    (location / 'provenance.json').write_bytes(json_bytes(meta))
    verify_maven(native_cache, output, root=root)
    return meta


def verify_maven(native_cache: Path, output: Path, *, root: Path = ROOT) -> dict:
    lock = check_source(root)
    location = receipt_dir(output, lock)
    prefix = 'medialibrary-all-' + lock['patched_version']
    aar_file, pom_file, receipt_file = (location / (prefix + suffix) for suffix in ('.aar', '.pom', ''))
    receipt_file = location / 'provenance.json'
    for f in (aar_file, pom_file, receipt_file):
        if not f.is_file() or f.is_symlink():
            refuse('missing/unsafe cached Maven package entry: ' + f.name)
    receipt = json.loads(receipt_file.read_text('utf-8'))
    if (receipt.get('schema') != 1 or receipt.get('coordinate') != lock['group'] + ':' + lock['module'] + ':' + lock['patched_version']
            or receipt.get('source_lock_sha256') != inputs_digest(lock)):
        refuse('Maven cached artifact source lock mismatch')
    if not all(SHA256.fullmatch(str(receipt.get(k, ''))) for k in ('base_aar_sha256', 'base_pom_sha256')):
        refuse('unverified official baseline digests')
    actual_files = {f.name: sha(f.read_bytes()) for f in (aar_file, pom_file)}
    if receipt.get('files_sha256') != actual_files:
        refuse('Maven cached artifact checksum mismatch')
    receipts = {abi: validate_abi(native_cache, abi, root=root) for abi in ABIS}
    if receipt.get('abi_receipts') != receipts:
        refuse('cached native source receipts no longer match Maven package')
    import io
    with zipfile.ZipFile(io.BytesIO(aar_file.read_bytes())) as z:
        if z.testzip():
            refuse('cached AAR is corrupt')
        for abi in ABIS:
            payload = z.read('jni/' + abi + '/libmla.so')
            if sha(payload) != receipts[abi]['library_sha256']:
                refuse('cached patched library does not match source ABI ' + abi)
        if 'classes.jar' not in z.namelist():
            refuse('cached AAR lacks Java classes')
    pom_reversion(pom_file.read_bytes(), lock['patched_version'], lock['patched_version'])
    return receipt


def cache_key(native_cache: Path, official_sha: str, root: Path = ROOT) -> str:
    lock = check_source(root)
    safe_digest(official_sha)
    receipts = {abi: validate_abi(native_cache, abi, root=root) for abi in ABIS}
    return 'vlc-patched-media-v1-' + sha(json_bytes({
        'inputs': inputs_digest(lock), 'base_aar_sha256': official_sha,
        'abis': receipts,
    }))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['source', 'collect-abi', 'verify-abi', 'fetch-official',
                                    'package', 'verify-maven', 'cache-key'])
    p.add_argument('--abi', choices=sorted(ABIS))
    p.add_argument('--native', type=Path)
    p.add_argument('--image-digest')
    p.add_argument('--native-cache', type=Path, default=Path('ci/_cache/medialibrary'))
    p.add_argument('--maven-repo', type=Path, default=Path('ci/_maven/repository'))
    p.add_argument('--official-dir', type=Path, default=Path('ci/_maven/official'))
    ns = p.parse_args(argv)
    try:
        if ns.mode == 'source':
            obj = {'source': 'verified', 'inputs_sha256': inputs_digest(check_source())}
        elif ns.mode == 'collect-abi':
            if not ns.abi or not ns.native or not ns.image_digest:
                refuse('collect-abi requires ABI, binary and compiler digest')
            obj = collect_abi(ns.native_cache, ns.abi, ns.native, ns.image_digest)
        elif ns.mode == 'verify-abi':
            if not ns.abi:
                refuse('verify-abi requires ABI')
            obj = validate_abi(ns.native_cache, ns.abi, compiler_digest=ns.image_digest)
        elif ns.mode == 'fetch-official':
            official = official_files()
            ns.official_dir.mkdir(parents=True, exist_ok=True)
            if any((ns.official_dir / ('medialibrary-all-0.13.24.' + suffix)).exists() for suffix in ('aar', 'pom')):
                refuse('official files already exist; refuse replacement')
            for suffix, binary in official.items():
                (ns.official_dir / ('medialibrary-all-0.13.24.' + suffix)).write_bytes(binary)
            obj = {'schema': 1, 'source': 'repo.maven.apache.org',
                   'files_sha256': {'medialibrary-all-0.13.24.' + name: sha(binary)
                                    for name, binary in official.items()}}
            (ns.official_dir / 'official-manifest.json').write_bytes(json_bytes(obj))
        elif ns.mode == 'package':
            official = read_official(ns.official_dir)
            obj = package_maven(ns.native_cache, ns.maven_repo, official)
        elif ns.mode == 'verify-maven':
            obj = verify_maven(ns.native_cache, ns.maven_repo)
        else:
            official = read_official(ns.official_dir)
            obj = {'cache_key': cache_key(ns.native_cache, sha(official['aar']))}
        print(json.dumps(obj, sort_keys=True))
        return 0
    except (MediaContractError, OSError, ValueError, KeyError, zipfile.BadZipFile, ET.ParseError) as exc:
        print('VLC_MEDIALIBRARY_REFUSED: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
