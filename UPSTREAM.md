# Upstream policy — VLC Redesign Android

## Authority and lineage

This project is based on [KuchiSofts/vlc-redesign-android](https://github.com/KuchiSofts/vlc-redesign-android), a derivative of VideoLAN's VLC for Android. Preserve the original Git ancestry, GNU GPL source notices, KuchiSofts credits, and Juxtopposed design attribution. This repository is not affiliated with, endorsed by, or an official distribution from VideoLAN or KuchiSofts.

- Direct upstream: `https://github.com/KuchiSofts/vlc-redesign-android.git` (routine merge source).
- Historical/root upstream: `https://code.videolan.org/videolan/vlc-android` (monitor only; **do not double-merge** unrelated histories).
- Fork main: reviewed integration base, not an automatically rewritten mirror.
- Feature branches: short-lived, source-bound changes, with the native Devtool launcher.
- Sync simulations: read-only `git merge-tree --write-tree` from exact fork/upstream SHAs. No automatic merge, force-push, reset, rebase, or mutation of user worktrees.

## Conflict policy

Keep upstream Kotlin source names and package namespaces intact; prefer additive `Rd*` components and `rd_*`/`redesign_*` resources. Any changes to app identity or existing upstream source must be targeted and documented. Avoid touching LibVLC/MediaLibrary implementation unless required by a tested compatibility issue. When source paths conflict, report paths and fix the actual integration conflict on a reviewed branch; never drop tests to make CI green.

The read-only workflow runs daily or on demand on `main`. It only creates GitHub CI evidence. If an upstream advance is mergeable, a human-reviewed **new native Devtool integration delivery** is still required; a clean `merge-tree` result is not a build or device qualification.

## Baseline and limitations

Roadmap audit on 2026-11-18 observed KuchiSofts `main` HEAD `8712d406647bcd68d9afa940436777a98b932524`, tree `9027b1aab19ec0786fbceba023075e9fbe7d7920` (app version 0.7.5). These values are historical audit evidence, **not a license to silently repin a built immutable package**. Every overlay must be reverified and exact-bound by Devtool before apply.

The parent app ID is `org.kuchisofts.vlcredesign`, **not a release identity for this fork**. M0/M1 is not a distributable release. Before a signed public build, introduce a distinct verified application ID, provider-authority tests, versioning and signing identity in a separate, source-bound, reviewed change. Do not publish builds under the parent ID with a different signature.
