# M7 — Independent signed-release qualification and maintenance

**Baseline:** `Mikeyphw/vlc-redesign-android` `main` @ `3b02ab51507d71a6c38274a621aa5ee6204049b9`, tree `3a144355511f62a4a4e957acd11a1bed8295bd7a`; merged M6 PR #6 head `e6b6e537eeb9ad3d5ead31ecdf33e73ed6b1db2b`. **Native launcher:** `Mikeyphw/devtool` 3.2.1 @ `6a670f9695a4461c2e75ac5df17bde25fc469077`.

## Independent identity

The user's fork owns **`com.mikeyphw.vlcredesign`**, replacing the upstream KuchiSofts application ID **`org.kuchisofts.vlcredesign`**. Android package IDs are update identities: this does **not** update a KuchiSofts installation in-place. Existing KuchiSofts users retain that app separately, and fork-specific data migration is **not** claimed. Existing Kotlin namespaces, VideoLAN upstream history, UI credits, and release semantics remain intact. Debug builds add `.debug`. The build uses the root app ID for the TV content-provider authority and other generated identities. Verify manifest authorities and exported components on actual APK before publication.

## Two independent hosted gates

1. Required **read-only PR CI** (`vlc-pr.yml`) keeps its 4 verified MediaLibrary ABIs, Maven AAR, JVM tests, debug APK, source locks and 7 success jobs. No release secret is available there.
2. **Manually dispatched release staging** (`vlc-release.yml`) requires a **fresh successful `workflow_dispatch` run of `vlc-pr.yml` on the exact merged `main` HEAD**, with the original workflow ID, completed success status, all seven job successes from one exact attempt, and unmodified source/main identity. Artifacts from that exact run must still be available (current retention: 2 days). These source gates run **before** requiring the protected `vlc-release` environment and are checked again after approval to reject a moved main branch.

The release job downloads exactly that run's `patched-medialibrary-maven` and four ABI receipts, verifies them with existing MediaLibrary provenance code, reconstructs the pinned LibVLCJNI Gradle project, installs the supported SDK and builds `:application:app:assembleSignedRelease` on a hosted Linux runner. M7 also fixes ABI-split detection for qualified Gradle task names so this task emits four ABI-targeted APKs rather than silently falling back to `all`. No SDK, Gradle, or Android build runs in Termux. There is **no PR `pull_request_target`, push, scheduled, or `workflow_run` signing trigger**. `GITHUB_TOKEN` is read-only (`contents: read`, `actions: read`); the workflow only uploads a staging artifact, and cannot automatically create GitHub Releases.

## Configure protected environment (mandatory, manual)

In GitHub repository Settings → Environments create **`vlc-release`**. Set required reviewers and restrict deployment branches to `main`. Add **environment-only** secrets:

- `RD_RELEASE_KEYSTORE_B64`: base64 of the authorized production keystore (`.jks` or `.keystore`), kept outside source and logs.
- `RD_KEYSTORE_PASSWORD`, `RD_KEY_ALIAS`, `RD_KEY_PASSWORD`: explicit, nonempty signing credentials. No fallback to upstream Gradle signing properties or Android debug key.
- Environment variable `RD_RELEASE_CERT_SHA256`: approved full 64-digit SHA-256 of the signing certificate (public fingerprint).

Do **not** place the key or passwords in repository variables, PR secrets, console arguments, logs, receipts or artifact names. Back up the key securely: a different signing key cannot update an existing installed package. Never run a release on an unreviewed fork. No protected environment is configured by this source-only change.

## Execute and independently accept

1. Merge an approved M7 PR after all source/Android PR CI jobs pass at its exact HEAD. Revisit direct-upstream KuchiSofts changes using the existing merge simulation; review ancestry, patch conflicts and security updates without automatic merges.
2. On merged `main`, dispatch **VLC Android PR qualification** (`vlc-pr.yml`) through the GitHub Actions UI or `gh workflow run vlc-pr.yml --ref main`. Confirm **all 7 jobs succeed** at the merged main SHA. Record run ID and attempt. Run within 2 days while source-bound native artifacts remain retained.
3. Dispatch **VLC staged signed release qualification** (`vlc-release.yml`) on `main`, providing `source_ci_run_id`. Approve protected environment only after checking the exact branch and SHA. Missing secrets, wrong certificate, stale CI, skipped jobs, wrong ABI/source lock, insufficient SDK, malformed version code, and unexpected package identity **block staging**.
4. Download the four staged signed APKs, `release-provenance.json`, `SHA256SUMS`, `sbom.spdx.json`, and `RELEASE_ACCEPTANCE.md`. Independently verify SHA-256 checksums, `apksigner verify --verbose --print-certs` for all four APKs, and `aapt dump badging` for `com.mikeyphw.vlcredesign`, four distinct ABI splits, minSdk 21, targetSdk 36, and versionCode/Name relationships. Both v1 and v2 schemes and the approved certificate fingerprint are required for Android 5.0 support.
5. Review SPDX dependency inventory and media source lock against licenses and current vulnerability advisories; this lightweight SBOM uses resolved Gradle dependencies plus signed APK file hashes and does **not** assert complete transitive source-file licensing or a zero-vulnerability result. Verify the credits (VideoLAN, KuchiSofts, Juxtopposed), changelog, signing-key continuity and all published source references.
6. **Device gate (not satisfied by CI):** install each ABI on compatible devices, verify upgrade of a previous `com.mikeyphw.vlcredesign` signed by the same certificate and increasing version code, data retention, fresh install, downgrade rejection, rollback/recovery, PiP, casting, playback, subtitles, background audio, Android TV remote/keyboard, TalkBack, RTL, landscape/foldable and offline media. No migration from the *different* `org.kuchisofts.vlcredesign` app is implied.
7. After manual release approval and device results are recorded, create a **draft** GitHub Release, upload only matching checksummed APKs, add a changelog separating **VideoLAN upstream**, **KuchiSofts redesign**, and **Mikeyphw custom changes**, then explicitly publish. The staging workflow does not publish or mutate releases.

## Runbook, provenance and limitations

- A failed source gate is never a release pass. A skipped signing job is never a release pass. The M7 PR hosted debug APK validates compile/test continuity, **not** production signature or device readiness.
- `release-provenance.json` is a source-bound, checked GitHub run/commit/ABI/checksum receipt; it is **not** a cryptographic SLSA attestation or reproducible-build proof. Independent rebuild comparison requires a second trusted builder and comparison of applicable deterministic inputs.
- The release tool refuses incomplete dependency graphs and certificates/ABIs with inconsistent metadata. Real installation, vulnerability analysis, app data continuity, app-store distribution, device startup/scroll performance and TV automation remain explicit acceptance tasks.
- Preserve the existing `ci/upstream_merge.py` read-only simulation. Review KuchiSofts main periodically (the scheduled job already runs daily), update genuinely obsolete checks when upstream changes and keep negative/security gates. Never automatically merge, reset, rebase, force-push or overwrite unrelated user work.
