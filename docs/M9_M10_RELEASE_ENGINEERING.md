# M9 + M10: paired distribution and in-app update

This fork builds a matched release for four ABIs (`armeabi-v7a`, `arm64-v8a`, `x86`, `x86_64`) under each of two Android identities. The default development package remains `com.mikeyphw.vlcredesign.debug`. Production standalone is `com.mikeyphw.vlcredesign`; the opt-in original-ID edition is `org.videolan.vlc`. Neither is official VLC. The original-ID edition cannot coexist with official VLC, and Android rejects a differently signed in-place update. Never automatically uninstall, migrate or downgrade another app. KuchiSofts' separate package remains distinct.

## Release procedure

Follow the protected environment and exact-main CI requirements in [M7](M7_RELEASE_SECURITY.md). Only the four fork signing secrets and `RD_RELEASE_CERT_SHA256` are required. No official VLC APK or certificate fingerprint is required. Staging provenance v3 reports official-update compatibility as `NOT_QUALIFIED`, not a verified comparison. Dispatch the manual `vlc-release.yml` workflow with the qualified source CI run ID and stable or beta channel. Both identity matrix jobs must succeed, followed by `qualify-pair`. Download the final paired staging artifact only. Verify the outer and per-identity SHA256SUMS, the two manifest signatures, signer fingerprint and all eight real APKs (`apksigner`, `aapt`). Review SPDX and source receipts. No automatic publication. After device QA and explicit release approval, create a draft GitHub Release in this repository with these unchanged assets (all eight APKs, signed manifest JSON/signature/certificate pairs, reports and checksums). Use `v0.7.6` (stable) or `v0.7.6-beta` (GitHub prerelease), as appropriate; do not publish a stable tag carrying a beta manifest. Use strictly increasing numeric versions for subsequent updates. Keep the APK key backed up; no key rotation is implemented.

### Protected signing and dependency inventory

The signed APK assembly, update-manifest signing, and resolved `signedReleaseRuntimeClasspath` inventory execute inside the same protected Bash step for each edition. Gradle configures `signedRelease` even when resolving dependencies; all four explicit signing inputs and the temporary keystore must remain available until the inventory completes. The EXIT trap removes the private keystore on success or failure. Manifest-signing or dependency-resolution failure prevents subsequent APK/SBOM qualification and artifact staging. The following verification and upload steps receive no signing secrets.

## In-app updates

Open **Settings > General > Software updates**, or **About > Check for updates**. Automatic checks run daily when enabled and can notify if permission is granted; manually check any time. Choose Stable or Beta. The device never selects a different installed package/ABI or non-increasing version code. Downloads are explicit, can be paused/resumed/canceled, and persist in private storage; Wi-Fi-only uses the selected Wi-Fi network rather than silently falling back to mobile data. Update metadata is fetched only from the fork's release assets, verified against the installed APK signing certificate; before installation, verify the complete APK size/digest, package, version and signer. Android's native PackageInstaller owns user approval and installation status. If Android denies unknown-source permission, grant it in Settings only if desired; then explicitly retry installation. No root, Shizuku, embedded credential, or silent installation.

## Acceptance (not established by source tests)

Record exact release and device identity for every row:

| Gate | Evidence required |
|---|---|
| All eight APKs | Actual signer, ABI, manifest authorities, min/target SDK, version and integrity receipts |
| Edition coexistence | Install standalone and fork original-ID together; official-ID conflict must be rejected without data deletion |
| Two signed versions | Upgrade each edition with same signer, retain settings/playback history, verify installed version next launch |
| Update channels | Stable rejects prereleases; beta sees only newer compatible versions; skipped/downgrade versions rejected |
| Download lifecycle | Offline, interrupted, pause/resume/cancel, process death, Wi-Fi loss, storage exhaustion, tampered/truncated APK |
| Installer lifecycle | Permission denied/granted, confirmation cancellation, process death before confirmation, failed or uncertain install, success and re-open |
| UI | Phone and TV remote, TalkBack, light/dark, rotation, English/Portuguese |
| Upstream | Review a candidate merge against current KuchiSofts, run all required checks on exact candidate head; no automatic merging |

The updater lives in `org.videolan.vlc.rd.updater`; existing upstream integration is limited to package/resource binding, manifest, startup scheduler, Settings/About entry points and replacement of the old update checker. The playback engine and media database are untouched. On future upstream merges retain these integration anchors and the release policy tests. See [M7](M7_RELEASE_SECURITY.md) for provenance limits. A staged release is not a published release or device acceptance.

## Native validation portability (R1)

The Gradle retry policy tests execute only mock commands. Their executable shebangs use the active Python interpreter, not Linux-only `/usr/bin/env` or `/bin/sh`; Termux fixtures use internal storage. The failed R0 transaction is retained as evidence, not replayed. R1 is a new exact-base overlay; all policy assertions remain required.

### M9-F03 — exact Gradle command admission

Gradle exposes task-specific arguments in `startParameter.taskNames`. Original-ID configuration accepts only `:application:app:assembleSignedRelease` or `:application:app:dependencies --configuration signedReleaseRuntimeClasspath` as exact vectors. Bare dependency inspection, extra tasks and other configurations are refused. M9-F02 keeps the signing inputs live through inventory. The required Android hosted CI job exercises both identities against the real Gradle project with an ephemeral test keystore, tests dry-run assembly and negative commands, and removes the fixture. No production signing inputs are used by PR CI. Real production signing and pair acceptance remain separately gated.
