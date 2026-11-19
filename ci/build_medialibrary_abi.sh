#!/usr/bin/env bash
# Runs *inside* KuchiSofts' selected VideoLAN Android builder image on hosted CI.
# The canonical VideoLAN compile scripts own toolchain setup and native compilation.
set -euo pipefail
ABI="${1:-}"
case "$ABI" in armeabi-v7a|arm64-v8a|x86|x86_64) ;; *) echo 'Invalid ABI' >&2; exit 2;; esac
cd /workspace
# GitHub checkouts are bind-mounted with their runner UID/GID. Refuse
# privileged/chown-based workarounds or silent read-only native builds.
if [ "$(id -u)" != "$(stat -c %u /workspace)" ] || [ "$(id -g)" != "$(stat -c %g /workspace)" ]; then
    echo 'VLC_NATIVE_WORKSPACE_IDENTITY_MISMATCH: container user must match workspace owner' >&2
    exit 3
fi
if [ ! -w /workspace ] || [ ! -w /workspace/.git ]; then
    echo 'VLC_NATIVE_WORKSPACE_NOT_WRITABLE: checked-out source/metadata must be writable' >&2
    exit 3
fi
if [ "${HOME:-}" != /tmp/vlc-ci-home ]; then
    echo 'VLC_NATIVE_HOME_INVALID: expected isolated ephemeral home' >&2
    exit 3
fi
mkdir -p "$HOME"
if [ ! -w "$HOME" ]; then
    echo 'VLC_NATIVE_HOME_NOT_WRITABLE' >&2
    exit 3
fi
: "${ANDROID_SDK:?VideoLAN container lacks ANDROID_SDK}"
: "${ANDROID_NDK:?VideoLAN container lacks ANDROID_NDK}"
test -d "$ANDROID_SDK" && test -d "$ANDROID_NDK"
python3 -B ci/medialibrary.py source
# Existing upstream script uses an HTTP clone URL. Git's supported URL rewrite
# ensures that its *unaltered* source and exact commit pin are fetched over TLS.
git config --global url."https://code.videolan.org/".insteadOf "http://code.videolan.org/"
git config --global user.name "VLC Hosted CI"
git config --global user.email "vlc-hosted-ci@users.noreply.github.com"

# VideoLAN's OCI image provides a pinned native NDK and a read-only SDK.
# Never modify the base image or run the compiler as root. Compose a writable
# SDK under the isolated HOME; link *unchanged* base toolchains and install
# only missing API 36 / build-tools into writable, separate directories.
base_sdk="$(realpath -e "$ANDROID_SDK")"
case "$base_sdk" in /sdk/*) ;; *) echo 'VLC_NATIVE_SDK_UNTRUSTED: expected bundled VideoLAN SDK' >&2; exit 3;; esac
sdk="$HOME/android-sdk"
test ! -e "$sdk" || { echo 'VLC_NATIVE_SDK_OVERLAY_ALREADY_EXISTS' >&2; exit 3; }
mkdir -p "$sdk/platforms" "$sdk/build-tools" "$sdk/licenses"
for entry in "$base_sdk"/*; do
    [ -e "$entry" ] || continue
    name="${entry##*/}"
    case "$name" in platforms|build-tools|licenses) continue ;; esac
    ln -s "$entry" "$sdk/$name"
done
if [ -d "$base_sdk/licenses" ]; then
    cp -a "$base_sdk/licenses/." "$sdk/licenses/"
fi
for category in platforms build-tools; do
    [ -d "$base_sdk/$category" ] || continue
    for entry in "$base_sdk/$category"/*; do
        [ -d "$entry" ] || continue
        name="${entry##*/}"
        # A partial target version must never be a read-only symlink: sdkmanager
        # must be able to install/reinstall that version into the writable SDK.
        if [ "$category" = platforms ] && [ "$name" = android-36 ] && [ ! -f "$entry/android.jar" ]; then
            continue
        fi
        if [ "$category" = build-tools ] && [ "$name" = 36.0.0 ] && [ ! -f "$entry/aapt2" ]; then
            continue
        fi
        ln -s "$entry" "$sdk/$category/$name"
    done
done
sdkmanager="$(command -v sdkmanager || true)"
if [ -z "$sdkmanager" ]; then
    for candidate in "$base_sdk/cmdline-tools/latest/bin/sdkmanager" "$base_sdk/tools/bin/sdkmanager"; do
        if [ -x "$candidate" ]; then sdkmanager="$candidate"; break; fi
    done
fi
if [ ! -f "$sdk/platforms/android-36/android.jar" ] || [ ! -f "$sdk/build-tools/36.0.0/aapt2" ]; then
    [ -x "$sdkmanager" ] || { echo 'VLC_NATIVE_SDKMANAGER_UNAVAILABLE' >&2; exit 3; }
    # Bounded yes-input, propagated exit code, no shell pipefail/SIGPIPE false
    # failures. The prebuilt source image remains immutable.
    python3 -B - "$sdkmanager" "$sdk" <<'SDKINSTALL'
import subprocess, sys
cmd=[sys.argv[1], '--sdk_root='+sys.argv[2], 'platforms;android-36', 'build-tools;36.0.0']
subprocess.run(cmd, input='y\n'*80, text=True, check=True, timeout=1200)
SDKINSTALL
fi
[ -f "$sdk/platforms/android-36/android.jar" ] && [ -f "$sdk/build-tools/36.0.0/aapt2" ] && [ -w "$sdk" ] || {
    echo 'VLC_NATIVE_SDK36_UNAVAILABLE: verified writable Android SDK is required' >&2; exit 3;
}
export ANDROID_SDK="$sdk" ANDROID_HOME="$sdk" ANDROID_SDK_ROOT="$sdk"
# The native source build does not publish an Android library. Upstream's
# compile.sh calls `gradle wrapper` in the full multi-project build, where
# Vanniktech publication evaluation fails before native compilation. Generate
# the *genuine* checksum-pinned Gradle 9.6 wrapper from an isolated project.
bootstrap="$HOME/gradle-wrapper-bootstrap"
mkdir -p "$bootstrap"
printf "rootProject.name = 'vlc-native-wrapper-bootstrap'\n" > "$bootstrap/settings.gradle"
printf '%s\n' '// Isolated native CI wrapper generator; no Android project evaluation' > "$bootstrap/build.gradle"
command -v gradle >/dev/null || { echo 'VLC_NATIVE_GRADLE_UNAVAILABLE' >&2; exit 3; }
gradle --no-daemon --project-dir "$bootstrap" wrapper \
    --gradle-version 9.6.0 --distribution-type bin \
    --gradle-distribution-sha256-sum bbaeb2fef8710818cf0e261201dab964c572f92b942812df0c3620d62a529a01
[ -s "$bootstrap/gradle/wrapper/gradle-wrapper.jar" ] && [ -s "$bootstrap/gradlew" ] || {
    echo 'VLC_NATIVE_GRADLE_WRAPPER_MISSING' >&2; exit 3;
}
grep -Fx 'distributionSha256Sum=bbaeb2fef8710818cf0e261201dab964c572f92b942812df0c3620d62a529a01' \
    "$bootstrap/gradle/wrapper/gradle-wrapper.properties" >/dev/null || {
    echo 'VLC_NATIVE_GRADLE_CHECKSUM_NOT_PINNED' >&2; exit 3;
}
test ! -e ./gradlew && test ! -e ./gradle || { echo 'VLC_NATIVE_UNEXPECTED_GRADLE_BOOTSTRAP' >&2; exit 3; }
mkdir -p ./gradle/wrapper
cp "$bootstrap/gradlew" ./gradlew
cp "$bootstrap/gradle/wrapper/gradle-wrapper.jar" ./gradle/wrapper/
cp "$bootstrap/gradle/wrapper/gradle-wrapper.properties" ./gradle/wrapper/
chmod u+x ./gradlew
# Upstream compile.sh's wrapper compatibility check uses GRADLE_PATH_VERSION;
# this is a verified, existing input, not a fabricated Devtool flag.
export GRADLE_PATH_VERSION=9.6.0
./gradlew --version | grep -F 'Gradle 9.6.0'

./buildsystem/compile.sh -a "$ABI" -t -l --release
# compile.sh -ml would launch an unrelated Maven publishing task. The exact
# KuchiSofts native compiler is the invoked subscript; CI assembles the patched
# AAR independently from the official classes and the resulting libmla.so.
./buildsystem/compile-medialibrary.sh -a "$ABI" --release
# Reject an unexpected upstream checkout or missing KuchiSofts patch commit.
base="$(python3 -B -c 'import json; print(json.load(open("ci/medialibrary.lock.json"))["medialibrary_commit"])')"
commit="$(git -C medialibrary/medialibrary rev-parse HEAD)"
test "$(git -C medialibrary/medialibrary rev-list --count "$base..$commit")" = 1 || {
  echo 'Expected exactly one KuchiSofts MediaLibrary patch commit' >&2; exit 3;
}
git -C medialibrary/medialibrary merge-base --is-ancestor "$base" "$commit"
test -s "medialibrary/jni/libs/$ABI/libmla.so"
