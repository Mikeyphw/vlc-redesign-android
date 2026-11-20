# VLC Redesign for Android: building a release

## Version

- `redesignVersionName` (root `build.gradle`) is the app's version: About, What's new and the APK name
  (`VLC-Android-<version>-<abi>.apk`). It follows the desktop's VLC Redesign version.
- `versionCode` comes from `redesignVersionName` (from 0.5.5): `3100000 + 10 * (major * 10000 + minor * 100 +
  patch)`, so 0.5.5 = `3105050`; each APK adds `10000000` and its ABI digit (arm64-v8a = `13105056`). Nothing to
  raise by hand, and it only grows with the version whatever upstream's base. (Up to 0.5.4 the code was upstream's
  3.7.2 = `30702xx` with a release counter in the tens digit: 0.5.4 = `3070290`, its last step; every new code is
  above it, so 0.5.5 installs over 0.5.4.)

## M7 signing and release qualification — Mikeyphw fork

This fork uses **`com.mikeyphw.vlcredesign`**, not upstream KuchiSofts'
`org.kuchisofts.vlcredesign`. Android treats them as different apps; no data
migration or cross-app upgrades are promised. Android package source namespaces
remain inherited from VideoLAN. Keep VideoLAN/KuchiSofts/Juxtopposed credits.

`assembleSignedRelease` requires **all four** environment-only inputs
`RD_KEYSTORE_FILE`, `RD_KEYSTORE_PASSWORD`, `RD_KEY_ALIAS`, `RD_KEY_PASSWORD`
with a readable private keystore and **never** falls back to upstream
`keyStoreFile` / `storealias` / `storepwd` Gradle properties. The complete
four-split build is performed only in the protected, manually dispatched
`vlc-release.yml` workflow with a vetted GitHub `vlc-release` environment.

A fresh successful read-only `vlc-pr.yml` **workflow_dispatch** run must be
qualified on the **exact merged main SHA** before release secrets can be used.
All seven required jobs, four ABI receipts and the patched Maven artifact
are checked. The hosted staged release verifies four signed APKs, approved
certificate SHA-256, package IDs, version codes, min/target SDK, and ABI
metadata. It uploads SHA-256 receipts and an SPDX dependency inventory;
**it does not automatically publish a GitHub Release**.

Production signing, independent device install/upgrade tests, SBOM/license
and vulnerability review, provenance review and manual release approval are
separate acceptance stages. Full instructions and limitations:
[docs/M7_RELEASE_SECURITY.md](../../docs/M7_RELEASE_SECURITY.md).

## What the release check expects (desktop `extras/juxtopposed/release/release-check.py`)

- The designer credit: "Juxtopposed" is named in a string the app shows (`application/*strings*.xml`, About).
- The version: `redesignVersionName` equals the desktop's release (About shows "Version 0.4.0 for Android
  <ABI> - based on VLC <libvlc>").
- The What's new card (`res/values/rd_whats_new.xml`) lists the release's changes.
- Nothing private: no owner name, paths, hosts or e-mail in the APK, the strings or the commit messages; no key,
  no IPTV playlist (`*.private.*`) and no Azure material in the repository.
- Upstream: how far `redesign` is behind VideoLAN's master, merged and built before the release.
- coverage.md and parity.md (in the shots folder) describe the release's state; the items that need the real
  phone and tablet are listed there.
