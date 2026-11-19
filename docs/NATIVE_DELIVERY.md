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
