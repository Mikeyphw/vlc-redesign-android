# Hosted Android CI, patched MediaLibrary and upstream integration

## Source of truth

This repository directly forks KuchiSofts' VLC Redesign. The Android app
currently requires `org.videolan.android:medialibrary-all:0.13.24-rd1`, which
includes a KuchiSofts native-library change to recognize embedded album covers.
Using VideoLAN's unpatched `0.13.24` as the application's resolved dependency
is **not** acceptable.

`.github/workflows/vlc-pr.yml` now builds this dependency **on hosted Linux**.
Neither a private Maven host nor `VLC_RD_MAVEN_BASE_URL` is needed. The sources,
patches, images and versions are recorded in `ci/medialibrary.lock.json`, with
a source contract in `ci/medialibrary.py`. KuchiSofts' existing
`buildsystem/compile.sh` and `buildsystem/compile-medialibrary.sh` remain
unaltered; an HTTPS Git rewrite applies only inside ephemeral build containers.

## Job DAG

1. **Native source contracts** execute the current upstream-merge tests,
   workflow/security checks and the exact MediaLibrary source-lock gate.
2. **Patched MediaLibrary native** builds each of the four Android ABIs in
   parallel using the VideoLAN container image documented for that ABI.
   The GitHub job pulls the image, records the actual OCI digest and looks up a
   source/hash/image-digest-keyed cache. On a miss, the container uses the
   original KuchiSofts compile scripts to build LibVLC, then the patched
   MediaLibrary JNI library; the checkout must be a one-patch descendant of
   VideoLAN's recorded MediaLibrary commit. The native output must be a valid
   shared ELF object of exactly the expected ABI. Cache hits and misses run
   the same digest/source/ELF verifier.
3. **Verified patched Maven AAR** downloads the four verified native job
   artifacts. It downloads the official **versioned** VideoLAN `0.13.24` AAR
   and POM from `repo.maven.apache.org`, checking Maven Central's SHA-256
   (or SHA-512) sidecars. It keeps the original Java classes, manifest and other native
   contents, replaces **only** the four `jni/<abi>/libmla.so` files, and
   updates the POM's version to `0.13.24-rd1`. The AAR's entries are sorted
   with stable ZIP timestamps. Each ABI digest and compiler OCI identity is
   recorded in a `provenance.json` receipt. A content-keyed package cache is
   restored only when all source receipts and the official base checksum
   match, and verified on both cache paths.
4. **Android hosted debug APK + JVM tests** downloads that Maven repository
   and the four native receipts, verifies every ABI again, and only then
   starts Java/Android/Gradle setup. `RD_MAVEN` is the job's local
   `ci/_maven/repository` folder. Gradle 9.6.0 builds and tests the actual
   Android app against KuchiSofts' patched coordinate; unsigned debug APKs
   become hosted artifacts only on a successful build.

The above stages are required and cannot silently be skipped. No Android
Gradle or native VLC compilation runs in Termux. A failed compiler image pull,
source checkout, cache checksum, patch application, AAR assembly, Maven
resolution, Gradle test or APK packaging is **CI failure**, not acceptance.

## Reproducibility boundary

The lock records both VideoLAN source commits, KuchiSofts patch Git blobs,
all four compiler image tags, the exact Maven coordinates and the full
integrity of cache inputs. Each build records the **resolved OCI image
content digest**, not just the readable tag. Cache keys include that digest.
The deterministic packaging step preserves all unrelated official AAR files.

This provides source-bound, independently verifiable *rebuildability*, but
not a claim of byte-for-byte deterministic compilation from C/C++ across
fresh builds: native timestamps, compiler environment and upstream toolchain
behavior may affect ELF bytes. The compiler OCI digests currently resolve at
CI runtime and are attested in the receipts; freezing a reviewed digest in
source is an additional release-hardening task. This build also depends on
explicit public VideoLAN source and Maven Central availability, not a
mystery KuchiSofts-controlled binary host. Publishing a signed release
requires an independent artifact provenance review and signed-APK/device
qualification.

To update upstream versions, review the new VideoLAN source commit,
KuchiSofts patch application, compiler image and official Maven baseline;
update `ci/medialibrary.lock.json` and tests together. Never silently
substitute the unpatched MediaLibrary.

## Local source tests (without Android toolchain)

```sh
python3 -B -m unittest discover -s ci/tests -p 'test_*.py' -v
python3 -B ci/workflow_policy.py
python3 -B ci/medialibrary.py source
```

The portable tests include synthetic JNI ELF/AAR fixtures and adversarial
missing-ABI, wrong-architecture, duplicate-ZIP, POM/version, mutated-cache,
wrong-OCI-digest and patch/source-drift cases. These tests do not pretend
that a local Android native build occurred.

## Required CI, rules and releases

`config/delivery-required-ci.json` requires **VLC Android PR qualification**
(numeric workflow ID `422964106`) for actual `pull_request` runs. Native
Devtool validates this exact committed policy and the hosted run at the
resulting PR HEAD. A skipped or failing native or Android job is not a green
workflow. The original M0/M1 session created before this policy existed
remains historically `REQUIRED_CI_SKIPPED_NO_POLICY`. Do not reapply an
already committed ZIPAPP; continue the durable session or build a new
source-bound feature package.

Branch protection/rulesets, Android device testing, signing and production
release approvals are separate gates. `main` was unprotected during the
initial foundation audit; check current hosted branch rules before claiming
formal protected-branch qualification. No auto-merge or force-push is enabled.

## Direct upstream mergeability

The separate daily `vlc-upstream.yml` job monitors KuchiSofts main using a
read-only Git merge simulation. This change affects only CI-owned files and
does not change Android playback or redesign code. The video engine and
MediaLibrary source remain upstream-owned.
