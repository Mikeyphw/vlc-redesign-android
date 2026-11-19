#!/usr/bin/env python3
"""Source-bound LibVLCJNI Gradle project bootstrap for hosted Android CI.

The native jobs use KuchiSofts' VideoLAN scripts. App Gradle still includes the
':libvlcjni:libvlc' subproject even when native libraries and patched Maven
artifacts are restored from verified caches. Reconstruct only its pinned source
checkout; never rebuild native code, rewrite user branches or fabricate stubs.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys

from medialibrary import load_lock

ROOT = Path(__file__).resolve().parents[1]
SOURCE_URL = 'https://code.videolan.org/videolan/libvlcjni.git'
SOURCE_BRANCH = 'libvlcjni-3.x'
HEX40 = re.compile(r'[a-f0-9]{40}\Z')


class PreparationError(ValueError):
    pass


def refuse(message: str) -> None:
    raise PreparationError(message)


def locked_commit(root: Path) -> str:
    pin = load_lock(root)['libvlcjni_commit']
    compile_sh = (root / 'buildsystem/compile.sh').read_text('utf-8')
    if not isinstance(pin, str) or not HEX40.fullmatch(pin):
        refuse('invalid locked LibVLCJNI commit')
    # Native compilation and APK Gradle must consume the SAME independently
    # locked VideoLAN revision, not floating branch HEAD or a stub project.
    if not re.search(r'(?m)^\s*LIBVLCJNI_TESTED_HASH=' + pin + r'\s*$', compile_sh):
        refuse('KuchiSofts compile.sh LibVLCJNI pin disagrees with CI source lock')
    settings = (root / 'settings.gradle').read_text('utf-8')
    if not re.search(r"(?m)^\s*include\s+.*':libvlcjni:libvlc'.*':medialibrary'", settings):
        refuse('Android Gradle project inclusion changed; requalify source bootstrap')
    medialib = root / 'medialibrary/build.gradle'
    if not medialib.is_file() or medialib.is_symlink():
        refuse('checked-out MediaLibrary Gradle project missing or unsafe')
    return pin


def git(root: Path, *args: str, timeout: int = 40) -> str:
    cmd = ['git', '-C', str(root), *args]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True,
                            timeout=timeout, env={**os.environ, 'GIT_TERMINAL_PROMPT': '0'})
    return result.stdout.strip()


def checkout_path(root: Path) -> Path:
    # Never operate on or overwrite a path outside the runner's checked-out
    # source. The destination must not be a symlink (including a dangling one).
    if root.is_symlink() or not root.is_dir():
        refuse('invalid Android source checkout root')
    return root / 'libvlcjni'


def verify(root: Path) -> dict:
    pin = locked_commit(root)
    checkout = checkout_path(root)
    if checkout.is_symlink() or not checkout.is_dir():
        refuse('pinned LibVLCJNI source checkout missing or symlinked')
    if (checkout / '.git').is_symlink() or not (checkout / '.git').is_dir():
        refuse('LibVLCJNI Git metadata missing or symlinked')
    project = checkout / 'libvlc/build.gradle'
    if not project.is_file() or project.is_symlink():
        refuse('real LibVLCJNI Gradle project missing; refuse dummy directory')
    if git(checkout, 'rev-parse', '--show-toplevel') != str(checkout.resolve()):
        refuse('LibVLCJNI Git worktree boundary mismatch')
    if git(checkout, 'remote', 'get-url', 'origin') != SOURCE_URL:
        refuse('LibVLCJNI upstream source origin mismatch')
    if git(checkout, 'rev-parse', 'HEAD') != pin:
        refuse('LibVLCJNI checkout is not locked to tested source commit')
    if git(checkout, 'status', '--porcelain=v1', '--untracked-files=no'):
        refuse('tracked LibVLCJNI source changed since pinned checkout')
    return {'libvlcjni_commit': pin, 'origin': SOURCE_URL, 'project': 'libvlcjni/libvlc'}


def prepare(root: Path) -> dict:
    pin = locked_commit(root)
    dest = checkout_path(root)
    if dest.exists() or dest.is_symlink():
        refuse('LibVLCJNI destination already exists; refuse replacing unrelated contents')
    # This is an ephemeral hosted-CI dependency checkout, never a Devtool
    # delivery/target repository mutation. Follow KuchiSofts' tested branch
    # and exact commit, using a trusted HTTPS remote without Git credentials.
    subprocess.run(['git', 'clone', '--single-branch', '--no-tags', '--branch', SOURCE_BRANCH,
                    SOURCE_URL, str(dest)], check=True, timeout=900,
                   env={**os.environ, 'GIT_TERMINAL_PROMPT': '0'})
    git(dest, '-c', 'advice.detachedHead=false', 'checkout', '--detach', pin, timeout=120)
    return verify(root)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'verify'))
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        root = args.root.resolve(strict=True)
        receipt = prepare(root) if args.action == 'prepare' else verify(root)
        import json
        print('VLC_ANDROID_GRADLE_SOURCE_VERIFIED ' + json.dumps(receipt, sort_keys=True))
        return 0
    except (PreparationError, OSError, ValueError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired) as exc:
        print('VLC_ANDROID_GRADLE_SOURCE_REFUSED: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
