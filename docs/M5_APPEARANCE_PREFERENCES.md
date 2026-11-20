# M5 — settings and personalization

Starting point: `Mikeyphw/vlc-redesign-android` main @ `53048751d151b70b67a4fa45ceb755d538e093f3`, tree `f864016b3b20c2304c2570a21aafcd8281a252ac` (M4 merged).

## Behavior

- Keeps the existing General settings page and VideoLAN/KuchiSofts `app_theme`, `rd_accent`, `rd_accent_system`, and `rd_amoled` keys. No new theme engine and no MediaLibrary schema change.
- Adds an appearance/player **read-only live preview** rendered from the active Android theme/accent attributes. Existing theme and accent controls already recreate the screen; it therefore shows the updated applied palette. The sample player is illustrative, not an interactive player or proof of fullscreen pixel parity.
- Adds an explicit confirmation and scoped reset to XML defaults. Reset removes only the four appearance overrides; it does not clear history, subtitle, TV, player engine, network or media preferences. Re-selecting any appearance setting after reset is supported.
- Invalid appearance value **types** and unrecognized accent IDs are removed when General settings initializes; valid AppCompat legacy auto-night mode values are preserved. The Android theme preference keeps its pre-existing migration from `KEY_DAYNIGHT` and `KEY_BLACK_THEME`.
- Preview and reset are hidden on TV where the forced TV palette overrides the phone appearance; no experimental player layout is activated.

## Assurance and limitations

- Source-owned positive/negative tests cover migration/reset scope, resource structure, page wiring and TV visibility guards. Current `ci/tests` discovery remains authoritative, and the existing four ABI, AAR, JVM and APK jobs remain required.
- The preview uses theme attrs and not direct generated `rd_dark_*` color resources, so direct hardcoded colors elsewhere are unaffected. Physical screenshot/color checks are separate.
- Device acceptance still requires light/dark/system/AMOLED, system accent on API 31+, 200% font/RTL, phone/tablet settings rotation and screen reader, fresh/upgrade/process restart, and TV mode suppression. Rollback behavior is limited to removing the opt-in overrides and is not a guaranteed downgrade of external settings storage.
- Existing safety, CI and security checks are retained. No obsolete version-specific gates were found in the touched scope; no checks were deleted merely to make CI pass.

## Subsequent roadmap

M6: Android TV focus/D-pad, tablet/foldable, screen-reader, reduced motion, localization and performance. M7: distinct app ID, managed signing, SBOM/license notices, verified release APKs and upstream maintenance.
