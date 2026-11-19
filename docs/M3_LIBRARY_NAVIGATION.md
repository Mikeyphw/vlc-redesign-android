# VLC Android M3 — Library, navigation and search behavior

This milestone extends the existing KuchiSofts/VideoLAN Home, Videos, Audio, Playlists and Search flows. It deliberately does **not** replace MediaLibrary providers, alter database schemas, add a second UI framework, or change LibVLC playback contracts. M2 design-token and AMOLED resources are preserved unchanged.

## Changes and regression rationale

- **Navigation:** Save a stable page name (`rd_nav_page`) alongside legacy `KEY_FRAGMENT_ID`, migrate transparently by reading the stable value first, fall back to the validated legacy value, and reject stale/disabled TV pages. Honor `EXTRA_TARGET` in saved activity state. Distinct fragment tags and state-safe `putFragment` avoid misidentifying screens after process recreation.
- **Videos:** Persist the selected Videos/Video Playlists subtab via `rd_video_current_tab`; do not override Android state when rotating an existing Video browser.
- **Search:** Always initialize adapters, even for in-app search launches. Cancel the previous search job and compare a monotonically increasing generation and current text before applying results. Clear previous rows when a query changes or becomes empty. Distinguish loading, no results, and idle states. Save/restore search text on configuration changes. Reset recycled search-result placeholder artwork.
- **Playlists:** The no-playlist state uses the existing `EMPTY` presentation instead of incorrectly showing no search results; existing loading/filtered/favorites states remain.
- **Home:** Expose title plus audio subtitle in the accessibility label, keep decorative cover hidden from accessibility, and permit two lines of title/subtitle at large font sizes.

## Testing and release acceptance

Native Devtool validation runs complete `ci/tests`, workflow and MediaLibrary contracts, and shell syntax checks. The new test module includes negative mutations for accidental removal of navigation persistence and stale-search guards. Hosted Android CI must compile Kotlin, run JVM tests and produce the actual APK at the exact PR HEAD; no local Termux Android/Gradle execution. Android phone/tablet smoke tests are separate release evidence and must be recorded explicitly:

1. Launch each Home/Video/Audio/Playlists page; switch tabs, rotate, background/resume, force-stop/reopen. Verify stable highlighted page, no lost detail/media provider, video subtab retained.
2. Search rapidly for A then B; clear, type again, rotate while search pending, rescan library. No A results under B, no old artwork, accurate loading and empty state. Repeat with voice/API ACTION_SEARCH and in-app search.
3. Check empty library, unavailable storage permission, no playlists, favorites-only and filtered-empty states; grant permission, rescan, sort and filter in Video/Audio/Playlists, and confirm saved preferences.
4. Font scaling 1.0/1.5/2.0, RTL locale, TalkBack focus and keyboard/D-pad navigation on phone/tablet and TV; verify card labels, touch targets, sidebar/bottom navigation and contrast in light, dark, AMOLED and system accents.
5. Test playback navigation return and floating player continuity; no MediaSession, MediaLibrary schema, engine or casting implementation changes in this milestone.

## Unverified until hosted/device evidence

No Android SDK, Gradle, emulator, APK install or screenshots are run by the bootstrap in Termux. The Python source-contract suite is not a substitute for functional device, screenshot or accessibility validation.
