# Native Devtool delivery — VLC Android

For code changes use only the latest verified compatible native Devtool
Launcher v3.2+ on `Mikeyphw/devtool/main`. Every artifact is pinned to the
genuine `Mikeyphw/vlc-redesign-android` fork, the named feature branch, exact
commit/tree/preimage blobs, and the checksummed proposed payload. Devtool
owns preflight, source-bound scaffold, native artifact/executable validation,
atomic apply/commit, durable session, approved push and existing-PR delivery.
The bootstrap is not a separate patching or transaction engine.

This consolidated hosted SDK correction is for existing PR #1 and the feature
branch `feature/vlc-m0-m1-upstream-foundation-20261118`, starting at commit
`beb2610a8b03a99c83f0885f094876e2f64a6229` and tree
`65e0e1930aa59f9adf2b5114d97268e20a5d369a`. It refuses any source,
branch, local worktree or remote ref drift. Never reset/rebase/force-push,
merge automatically, overwrite unrelated changes, or regenerate an already
created immutable package. On a successful apply, use the **new** durable
session for `status`, `deliver` and `ci`; do not repeat `apply`.

Terminal delivery disables Textual/full-screen hosts through supported
Devtool controls. Never copy commands/logs automatically to the clipboard.
Keep native stdout/stderr visible and machine receipts parseable; do not
suppress diagnostics. All Android, Gradle, NDK, LibVLC, and MediaLibrary builds
run on GitHub-hosted Linux, never on Termux.

The previous CI run `44452089433` failed in all four ABIs while an image-local
Python `sdkmanager` attempted to write SDK 36 into a read-only directory.
The new workflow installs SDK 36 with Google's official tools on the runner
and mounts the verified packages read-only into the original VideoLAN image.
KuchiSofts' original source pins, patches, native build scripts, four ABI
ELF/cache/packaging checks, Maven integrity and Android compile remain required.
Existing tests were **updated** for this runtime instead of preserving obsolete
SDK-overlay gates. New tests reject invalid runner SDK layouts and missing
read-only mounts. See `docs/CI.md` for the current architecture and validation.

Native hook success is local/source evidence only. Hosted PR SHA and job
statuses, upstream compatibility, signed APK/release and device acceptance
remain separate and must never be inferred from a local pass.

## SDK tools-package qualification follow-up

The previous native delivery committed at
`dba308c44495d8dc278bebeb23b4e3059ecff65d`; its hosted run
`44456258948` failed because `setup-android@v3` attempted to install the
retired `tools` SDK package. This new follow-up retains the existing
`config/delivery-required-ci.json` and all previous source/ABI/Maven tests,
while setting an explicit current package list in both Android setup actions.
The historical failed session is not upgraded. Rebuild a fresh native
source-bound artifact on the exact current PR head and qualify its new CI run.

## Incremental APK/native artifact reuse milestone

This consolidated follow-up is source-bound to PR #1 HEAD
`2c3aa8e1477f5865579804dbe75ee018025d0129`, tree
`cabddbf5c2250e582f7f2a0a87f5292ef6adfefa`. It adds
`ci/apk_reuse.py` and `ci/tests/test_apk_reuse.py`, updates the existing native
workflow/policy/MediaLibrary package/tests, and refreshes the CI documentation.
Earlier overlapping native CI contract tests are updated for current behavior;
no security, origin, regression, negative or required-CI gate is deleted.

The historical PR run `44518789481` qualified four native ABIs but failed
on the official baseline HTTP 404, so it did not build an APK or qualify
required CI. Native caches may be reused *only* after new source-bound ABI
verification; JVM tests cannot be skipped by an APK cache. The new Devtool
launcher requires source/origin/HEAD/tree/preimage/blob/payload verification,
native executable tests and the actual current hosted CI. A failed hosted job
is not a pass; resume the new durable session instead of reapplying.

## Incremental Android Gradle checkout correction

After incremental delivery HEAD `bd817867230ef8119d98e0db8582b431e44754fd`,
run `44527779747` successfully reused and verified all four native ELF
caches and the patched Maven AAR, but failed before JVM tests because the
external `:libvlcjni:libvlc` project was absent from the clean runner
checkout. This consolidated follow-up adds a source-locked, verified
LibVLCJNI-only checkout before Android Gradle; source-lock negative tests,
workflow gates and documentation are updated rather than bypassed. It does
not invalidate otherwise verified native/Maven caches or claim a completed
APK. New Devtool delivery must bind the actual target origin, named feature
branch, starting HEAD/tree/blobs, current approved launcher runtime and exact
payload. The prior committed native session is historical; resume the newly
created session after commit rather than reapply.

## Bounded official Maven classpath retry correction

At PR HEAD `41d64e93a659d28d12f42bb84b8ef134820c5d34`, GitHub Actions
run `44532070848` attempt 1 failed to locate JetBrains annotations 13.0;
attempt 2 failed to locate Kotlin stdlib 2.2.10. A requested controlled
rerun was carried out by the operator using `gh` after the connected GitHub
integration returned 403. The source/ABI/Maven jobs passed both attempts.
This follow-up only adds a bounded remote classpath retry for the existing
Gradle test/build steps, with `--refresh-dependencies` and fail-closed guards,
new negative cases and current CI documentation. No Kotlin/AGP/Gradle
versions, project source, ABI caches or release policy are changed.
Local validation is not hosted qualification; a native committed apply must
be followed by fresh required-CI checks at the resulting PR HEAD.
