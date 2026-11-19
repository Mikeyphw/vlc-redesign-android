# M2 — Theme and design-system foundation

Baseline: `Mikeyphw/vlc-redesign-android` `main` merge `95d055013de9434f04a75948b6dceb95a220f822`, tree `a3cc6681bd43dbf32e72ed1b1449eee16ba420c1`.

## What already exists upstream

KuchiSofts supplies nine named accents, API-31+ system accents, Inter text appearance, light/dark/system preferences and an established `rd_*` palette. This milestone keeps those source-owned definitions and all `app_theme` values intact. Generated `application/resources/src/main/res/*/redesign_colors.xml` must never be edited directly.

## Additive design roles

`rd_ds_tokens.xml` establishes distinct `rd_ds_*` resources for spacing (4/8/12/16/24/32 dp), corners (6/10/12/14 dp), elevations (0/4/8 dp), a 48 dp primary touch target, and semantic text/surface/panel roles with `values-night` overrides. Existing Material shape appearance styles and the primary/outlined button touch target use those tokens; cramped player controls intentionally keep their old specialized dimensions pending device/landscape QA. No second UI framework or global style rewrite is introduced.

## AMOLED

`rd_amoled` is an independent, opt-in `SharedPreferences` Boolean defaulting to false. `app_theme` remains `-1` system / `1` light / `2` dark. The setting is exposed on the redesigned General page for non-TV devices and triggers existing settings recreation. During `BaseActivity.applyTheme`, the opt-in overlay is applied only for effective dark mode, before the existing accent overlay, so the user's orange/named/system accent remains authoritative. Forced player/onboarding and TV themes are not altered. `ThemeOverlay.Redesign.Amoled` sets black app-window and theme-aware base surfaces while retaining subtly separated dark panels.

**Coverage limitation:** layout references that directly hard-code a generated `@color/rd_dark_*` resource are not dynamically repainted by Android theme overlays. Full-screen AMOLED parity and screenshots on real devices are still required; do not claim every pixel is black. The preference and overlay are deliberately additive and can be disabled without migrating prior settings.

## Acceptance matrix

- CI: all existing source safety tests, M2 resource/theme regression tests, hosted Kotlin/JVM tests and debug APK at the exact PR HEAD; native ABI and AAR cache receipts remain checked, not skipped validation.
- Visual/device: light/dark/system/AMOLED (off/on), API 21 vs API 31+, system and each named accent, restore/migration, TV forced mode, player controls, 200% font scale, RTL, high contrast, rotating to landscape, screen-reader labels, touch-target reachability and screenshot/golden comparison.
- Upstream: no changes to generated colors, MediaLibrary, native toolchain, player controls or data schemas; review KuchiSofts merge simulation before merging.
- Release: no signing or production acceptance is implied by hosted debug CI.
