#!/usr/bin/env python3
"""Verify an installed official Android 36 platform and build-tools layout.

Runs on GitHub's runner and inside the VideoLAN compiler image. It never
installs packages, mutates the SDK, or invokes any SDK-manager implementation.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import re
import sys


class SDKLayoutError(ValueError):
    pass


def _regular(root: Path, child: str) -> Path:
    candidate = root / child
    if not candidate.is_file() or candidate.is_symlink():
        raise SDKLayoutError(f'missing/symlinked SDK component: {child}')
    if not candidate.resolve().is_relative_to(root.resolve()):
        raise SDKLayoutError(f'SDK component escapes root: {child}')
    if candidate.stat().st_size == 0:
        raise SDKLayoutError(f'empty SDK component: {child}')
    return candidate


def verify_sdk(path: Path) -> None:
    if not path.is_dir() or not path.resolve().is_dir():
        raise SDKLayoutError('Android SDK root is missing')
    for dir_name in ('platforms/android-36', 'build-tools/36.0.0'):
        directory = path / dir_name
        if not directory.is_dir() or directory.is_symlink() or not directory.resolve().is_relative_to(path.resolve()):
            raise SDKLayoutError('missing/symlinked SDK directory: ' + dir_name)
    platform = _regular(path, 'platforms/android-36/source.properties').read_text('utf-8')
    tools = _regular(path, 'build-tools/36.0.0/source.properties').read_text('utf-8')
    _regular(path, 'platforms/android-36/android.jar')
    aapt2 = _regular(path, 'build-tools/36.0.0/aapt2')
    if not re.search(r'(?m)^AndroidVersion\.ApiLevel\s*=\s*36\s*$', platform):
        raise SDKLayoutError('not Android platform 36')
    if not re.search(r'(?m)^Pkg\.Revision\s*=\s*36\.0\.0\s*$', tools):
        raise SDKLayoutError('not Build Tools 36.0.0')
    if not aapt2.stat().st_mode & 0o111:
        raise SDKLayoutError('aapt2 is not executable')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    args = parser.parse_args()
    try:
        verify_sdk(args.sdk)
    except (SDKLayoutError, OSError, UnicodeError, ValueError) as exc:
        print('VLC_SDK36_INVALID: ' + str(exc), file=sys.stderr)
        return 1
    print('VLC_SDK36_VERIFIED sdk=' + str(args.sdk))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
