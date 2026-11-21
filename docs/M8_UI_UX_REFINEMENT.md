# M8 — UI/UX refinement, upstream-syncable

Baseline: `Mikeyphw/vlc-redesign-android` `main` at `3b02ab51507d71a6c38274a621aa5ee6204049b9`. M7 remains a distinct draft PR, not part of M8's payload. The new M8 branch targets `main`, without merging M7 into this branch or altering release/signing files.

## Implemented source changes

- **First-run and empty-library UX:** onboarding explains that checking a folder, rather than merely browsing it, enables scanning. Empty Home shows a localized action to open the existing storage picker (`SecondaryActivity.STORAGE_BROWSER`), and hides it when storage permission is missing. Debug whole-device protection is unchanged.
- **Home polish:** videos show duration badges; radius and row spacing become consistent; narrow-window card width is clamped to fit; new sections reveal briefly when motion is enabled, using the existing M6 `RdMotionPolicy`.
- **Mini-player:** collapsed header announces its expansion action; slimmed progress line without changing playback or MediaSession control flow.
- **Discoverability:** localized search guidance explains global search and per-tab sorting/filtering; help hides when a query is entered.
- **Playback overlay:** seekbar target is at least 48dp high; information overlay text wraps on smaller screens and has more readable secondary text.
- **Testing:** source-level unit/negative contracts in `ci/tests/test_m8_ui_refinement.py`; existing screenshot instrumentation gains Home + collapsed mini-player captures. `ci/m8_visual_compare.py` compares actual screenshots to separately approved references. `ci/m8_device_acceptance.sh` captures the physical screen and gfxinfo, without asserting device acceptance.

## Upstream merge policy

Preserve full Git ancestry. Do not touch LibVLC, MediaLibrary, player backend or database schema. New resources are additive; integration edits stay localized to the existing screen classes/layouts. Continue simulated upstream merges from KuchiSofts main using the existing integration workflow before acceptance. A clean text merge alone is not functional proof.

## Acceptance matrix (must be separately evidenced)

1. **Native Devtool:** exact preimages, full validator and clean named branch; successful source-bound native atomic transaction. Never reapply after a committed session.
2. **Hosted CI:** source tests, source policy, workflow-policy checks, hosted four-ABI Android APK/JVM checks on exact PR HEAD. No Gradle in Termux.
3. **Automated screenshot capture:** Android instrumentation on a supported hosted emulator; collect `m8_home` and `m8_mini_player` and existing Video/Player screenshots. A captured image is not a visual PASS by itself.
4. **Screenshot baselines:** approve separate references for light/dark/AMOLED, compact portrait/landscape, font scaling and API 35/36; compare with `python3 ci/m8_visual_compare.py --baseline ... --actual ...`. No baseline auto-approval or invented pass.
5. **Physical-device UX:** select `Movies/Films` via checkbox, ensure discovery; permission-denied screen, folder CTA, return/resume, switch views, playback, PiP, pause/resume, TalkBack, RTL, tablet/TV and reduced-motion setting. Capture real evidence.
6. **Performance:** compare `adb shell dumpsys gfxinfo <package>` before/after on the same device and workloads, plus startup, memory, jank and media-list scrolling. No invented target numbers.
7. **Upstream sync simulation:** run `bash ci/m8_upstream_simulation.sh` on a clean named M8 worktree; candidate merge from latest `KuchiSofts/main` into a disposable worktree; verify conflicts, rebuild, test and discard candidate; never auto-merge upstream or force-update user branches.
8. **Release:** M7 signing/identity remains independent; no production signing, published release or merge is implied by passing M8 validation.

## Limitations

No Android device/emulator or UI pixel-reference baselines were available during package authoring. Screenshots, performance, hosted builds and physical acceptance remain **unverified** until executed. This is an actual source-edit payload prepared for canonical Devtool delivery, not a claim that the changes have already been committed to GitHub.
