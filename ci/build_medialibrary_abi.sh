#!/usr/bin/env bash
# Runs *inside* KuchiSofts' selected VideoLAN Android builder image on hosted CI.
# The canonical VideoLAN compile scripts own toolchain setup and native compilation.
set -euo pipefail
ABI="${1:-}"
case "$ABI" in armeabi-v7a|arm64-v8a|x86|x86_64) ;; *) echo 'Invalid ABI' >&2; exit 2;; esac
cd /workspace
: "${ANDROID_SDK:?VideoLAN container lacks ANDROID_SDK}"
: "${ANDROID_NDK:?VideoLAN container lacks ANDROID_NDK}"
test -d "$ANDROID_SDK" && test -d "$ANDROID_NDK"
python3 -B ci/medialibrary.py source
# Existing upstream script uses an HTTP clone URL. Git's supported URL rewrite
# ensures that its *unaltered* source and exact commit pin are fetched over TLS.
git config --global url."https://code.videolan.org/".insteadOf "http://code.videolan.org/"
git config --global user.name "VLC Hosted CI"
git config --global user.email "vlc-hosted-ci@users.noreply.github.com"
./buildsystem/compile.sh -a "$ABI" -t -l --release
./buildsystem/compile.sh -a "$ABI" -t -ml --release -b
# Reject an unexpected upstream checkout or missing KuchiSofts patch commit.
base="$(python3 -B -c 'import json; print(json.load(open("ci/medialibrary.lock.json"))["medialibrary_commit"])')"
commit="$(git -C medialibrary/medialibrary rev-parse HEAD)"
test "$(git -C medialibrary/medialibrary rev-list --count "$base..$commit")" = 1 || {
  echo 'Expected exactly one KuchiSofts MediaLibrary patch commit' >&2; exit 3;
}
git -C medialibrary/medialibrary merge-base --is-ancestor "$base" "$commit"
test -s "medialibrary/jni/libs/$ABI/libmla.so"
