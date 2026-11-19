# VLC Redesign Android — source ownership and architecture

## Existing source layout (verified 2026-11-18)

- `application/vlc-android/src/org/videolan/vlc/gui`: activities, HomeFragment, navigation, preferences, player delegates, existing `Rd*` enhancements.
- `application/vlc-android/res/layout`: Android Views and redesign-compatible XML layouts.
- `application/vlc-android/res/values`: `rd_*`, `redesign_*` style/identifier/dimension files and upstream tokens.
- `application/app`: application build, APK variants, packaging and signing configuration.
- `application/resources`: strings/localizations and shared resources.
- `buildsystem/redesign/MEDIALIBRARY.md`: exact modified MediaLibrary dependency and source patches.

The UI is predominantly Kotlin/Android Views/XML, with layout variants for tablet/TV. Do **not** introduce a second app architecture or rewrite the main Kotlin namespace for branding. Later visual milestones should create independently owned UI helpers and only integrate through the smallest stable upstream seams.

## Mergeability invariants

1. Parent's history is retained through a **genuine GitHub fork**, and its `main` is only a reviewed integration target.
2. Track KuchiSofts as one direct upstream; do not merge VideoLAN independently.
3. Avoid mass formatting, Gradle version repins, playback engine edits and unreviewed resource renames.
4. CI must validate conflicts (including negative cases), source/credit integrity and hosted Android build separately.
5. Branch protections, signed APKs, device smoke and final distribution are separate evidence; do not infer them from source-only tests.

## First milestone constraints

M0 + M1 introduces only source-bound documentation, a mergeability simulator and hosted CI. It intentionally **does not change app ID or media libraries**, because those require complete manifest/provider/runtime integration tests. The hosted Android build job is designed to **fail closed** until an HTTPS Maven endpoint for the patched `0.13.24-rd1` dependency is configured. This is a known acceptance blocker, not an intentional skipped pass.
