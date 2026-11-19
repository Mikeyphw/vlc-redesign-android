# VLC Android hosted CI and upstream compatibility

## Build source and scope

Our repository is a genuine fork of `KuchiSofts/vlc-redesign-android`, not
VideoLAN's original. The KuchiSofts source at
`8712d406647bcd68d9afa940436777a98b932524` supplies its actual GitLab
build template at `buildsystem/gitlab/.gitlab-ci.yml`, and its native scripts at
`buildsystem/compile.sh` and `buildsystem/compile-medialibrary.sh`.
There is no KuchiSofts GitHub Actions workflow to invoke. This GitHub Actions
adaptation **reuses those checked-in native compiler scripts**; it does not
reimplement MediaLibrary's source patches or native compilation.

The upstream GitLab build image for 64-bit builds is tagged differently from
the one in KuchiSofts' `buildsystem/redesign/MEDIALIBRARY.md`. We deliberately
retain the *documented patched MediaLibrary* image/ABI lock in
`ci/medialibrary.lock.json` until a separate compatibility audit justifies
changing it. Never silently repin the image or substitute stock MediaLibrary.

## Required GitHub Actions DAG

`vlc-pr.yml` runs these gates in order: source contracts; four independently
verified VideoLAN native builds; checksum-verified patched Maven AAR assembly;
then Android unit tests and actual debug compilation. All four native ABIs
(`armeabi-v7a`, `arm64-v8a`, `x86`, `x86_64`) are required. Cache restores are
verified against source lock, OCI digest, ELF machine type and SHA-256 receipts.
The final AAR retains VideoLAN's official classes and other resources while
replacing only KuchiSofts-patched `libmla.so`, version `0.13.24-rd1`.

To run local source contracts:

```sh
python3 -B -m unittest discover -s ci/tests -p 'test_*.py' -v
python3 -B ci/workflow_policy.py
python3 -B ci/medialibrary.py source
```

## Official Android SDK 36 on the hosted runner

Hosted run [44452089433](https://github.com/Mikeyphw/vlc-redesign-android/actions/runs/44452089433)
proved a different command named `sdkmanager` was being selected **inside**
the VideoLAN image: `/usr/bin/sdkmanager` from Python `sdkmanager==0.6.11`
ignored the requested `--sdk_root` and attempted to write under read-only
`/sdk/android-sdk-linux` in all four ABI jobs. This is a host/container tool
selection failure, not a MediaLibrary source/compiler failure.

When a verified native ABI cache is absent, CI now uses `actions/setup-java`
and `android-actions/setup-android` **on the GitHub-hosted Ubuntu runner**.
It pins the `setup-android@v3` command-line tools input to `12266719`
(version 16.0), verifies the SDK manager package revision, and selects the
official `$ANDROID_HOME/cmdline-tools/16.0/bin/sdkmanager` or its verified
preinstalled `latest` equivalent to install
`platforms;android-36` and `build-tools;36.0.0` under the runner's SDK root.
`ci/verify_android_sdk.py` verifies the SDK's platform API level, build-tools
revision, nonempty `android.jar` and executable `aapt2`, rejecting missing,
wrong-version, empty, symlinked, and escaped components.

Only the two verified SDK directories are mounted **read-only** into the
corresponding paths under `/sdk/android-sdk-linux` in KuchiSofts' VideoLAN
compiler container. The image's NDK, toolchains and remaining SDK content
are retained; no SDK manager runs inside the image. Existing UID/GID-bound
workspace permissions, isolated `HOME`, HTTPS source fetch, exact patch/commit
pins, and OCI image digest checks remain enforced. No `sudo`, root-owned
workspace conversion, or `chmod -R` workaround is used.

The native container script checks the mounted SDK layout again and refuses
writable SDK mounts or a changed VideoLAN base SDK path. GitHub Actions SDK
installation happens only on a cache miss; a cache hit is still independently
validated in the subsequent source/ABI digest checks. A cache hit is never
sufficient evidence of a successful native build.

## Native LibVLC and patched MediaLibrary build

The image runs KuchiSofts' `buildsystem/compile.sh -a <ABI> -t -l --release`,
followed by its `buildsystem/compile-medialibrary.sh -a <ABI> --release`.
This second script is exactly the one `compile.sh` calls for `-ml` builds;
using it directly avoids invoking the unrelated Gradle publication step.
For `compile.sh` wrapper setup only, CI creates a real Gradle 9.6 wrapper
from an isolated minimal project, checks its distribution SHA-256 against
KuchiSofts' locked value, then runs the upstream LibVLC compile script.
No Android playback code or upstream media patch is modified.

## Governance and acceptance

`config/delivery-required-ci.json` registers the actual PR workflow ID
`422964106`. A required native/Android job that fails, is cancelled or is
skipped makes the whole workflow unqualified. The read-only daily upstream
merge simulation continues independently and does not modify Git refs.
The canonical Devtool launcher must validate and commit against the exact
feature HEAD and PR #1; a successful native commit is followed by durable
session `status`/`deliver`/`ci`, **not an overlay reapply**.

Current local tests cover the SDK verifier, workflow ordering, four ABI
identity checks, tampered-cache rejection, unsafe permission changes,
incorrect Maven sources, and source ancestry. Local tests and static workflow
parsing **do not establish hosted compilation, device evidence, or release**.
The actual four-ABI build, patched Maven archive, Android Gradle test/build,
PR HEAD checks, and Devtool required-CI qualification must pass on GitHub.
`main` branch protection and any approved signed release are independent
acceptance requirements; no release or device qualification is claimed here.

## Hosted SDK package correction (19 November 2026)

The source-bound PR run [44456258948](https://github.com/Mikeyphw/vlc-redesign-android/actions/runs/44456258948)
passed Native source contracts but all four native jobs failed in
`android-actions/setup-android@v3` before the explicit SDK 36 installer.
The action's default package list `tools platform-tools` requests the retired
Android SDK `tools` package, which Google's repository no longer provides.
Both setup-android invocations now explicitly select only `platform-tools`
with the independently reviewed `12266719` command-line-tools revision.
The existing following steps still install and inspect platform 36 and Build
Tools 36.0.0; the Android job still provisions NDK 21.4.7075529.
Current workflow negative tests reject any missing, unpinned, or obsolete
setup-android package configuration, and source/ABI/cache/Maven/Gradle gates
remain required. This does not establish a hosted build pass.

## Incremental source-built artifacts (19 November 2026)

Hosted run [44518789481](https://github.com/Mikeyphw/vlc-redesign-android/actions/runs/44518789481)
verified all four KuchiSofts-patched MediaLibrary ELF builds and uploaded their
source/image/patch/SHA-256 receipts, but Maven Central baseline retrieval failed
with HTTP 404 after all four native receipts passed. The original script
incorrectly assumed that Maven Central publishes `.sha256` or `.sha512`
**sidecar files for every AAR and POM**. Both may return 404 even when the
versioned AAR and POM exist. The source-bound fetcher now differentiates the
exact failing URL, verifies a published SHA-256 or SHA-512 sidecar when present,
and otherwise accepts **only** the exact official TLS endpoint plus valid
AAR/POM contents and computes the local SHA-256 for subsequent cache/package
verification. It never downgrades to MD5 or SHA-1. A missing AAR or POM, bad
structure, changed origin/redirect, checksum mismatch, or non-404 HTTP error
still fails. A TLS-only baseline is **not** an independently signed publisher
attestation; signed-release qualification requires separately approved trust.

Native cache identity is now based on the pinned source/patch blobs, compiler
script, official SDK verifier and resolved VideoLAN image digest—not the Python
Maven packager. Existing `mla-v1-*` native caches from the successful four-ABI
run can be recovered via an image-scoped prefix. **Every recovered binary is
verified** against the current patch/source lock, actual OCI digest, ELF type,
and recorded SHA-256 *before* native compilation is skipped. Missing caches
trigger compilation. Older source-lock receipts are rejected and replaced by
a fresh compile; corrupted receipts/ELFs for the current lock fail closed.
The original ABI cache receipt schema and verification are unchanged. The
Maven cache still depends on both original upstream AAR contents and native
receipts, and is verified before Android compilation.

The new `ci/apk_reuse.py` forms an APK cache key from Git-tracked Android/build
inputs (excluding only CI/docs metadata), the **verified patched Maven AAR, POM and provenance SHA-256
digests**, current GitHub runner image revision and pinned Android/JDK/Gradle
versions. On an exact hit, it revalidates APK ZIP contents, manifest/DEX, strict
file inventory and SHA-256 against its source/toolchain receipt. **JVM unit
and regression tests still execute on every PR run, even on an APK cache hit.**
Only `assembleDebug` is skipped when an identical, successfully JVM-tested
APK exists; cache misses assemble and seal the actual APK. A corrupted cache is
never treated as successful and never silently overrides current source.
This cache contains only debug binaries, not release signing keys or production
artifacts; there is no approved signing/release substitution.

The first new hosted run may still need to build its APK because no successful
APK cache exists yet. Subsequent CI/docs-only commits can reuse that debug APK
when the tracked build inputs, patched AAR, runner image and toolchain match.
Unpinned external dependency resolution remains a separate release-qualification
risk and is not represented as reproducible byte-for-byte compilation.

## Hosted Gradle source bootstrap after incremental cache success (19 November 2026)

The first incremental hosted run
[44527779747](https://github.com/Mikeyphw/vlc-redesign-android/actions/runs/44527779747)
passed source contracts, **all four cached and independently validated native
ELFs**, and the complete patched Maven AAR packaging/verification. The Android
JVM job then failed at configuration: root `settings.gradle` includes the
`:libvlcjni:libvlc` project, but the app checkout lacked `libvlcjni/libvlc`.
This is an external source-project prerequisite, **not a reason to rebuild
LibVLC, MediaLibrary or the cached AAR**.

The Android job now uses `ci/prepare_android_gradle.py` before its cache-key,
JVM and APK stages. It clones exactly KuchiSofts' tested
`https://code.videolan.org/videolan/libvlcjni.git` `libvlcjni-3.x` branch,
checks out the **exact source-lock commit**
`0b8dc65efb203c86a0476bc337ddd99ecf1c0ef6` on detached HEAD, and
verifies origin, Git root, commit, tracked cleanliness, actual
`libvlcjni/libvlc/build.gradle`, and the existing root MediaLibrary Gradle
project. The source lock is cross-checked with the untouched upstream
`buildsystem/compile.sh`. No placeholder projects, native compilation,
reset/rebase/force-push, or SDK permission hacks are introduced. Current JVM
tests remain mandatory and cache hits may skip only identical APK assembly.

Source and workflow contract tests include negative cases for wrong remote or
commit, symlinked/fake directories, dirty tracked source, omitted preparation,
removed verification, and broken source-lock agreement. Hosted Gradle/API
acceptance and the first verified debug APK **are still pending**.
