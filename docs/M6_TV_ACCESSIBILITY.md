# M6 — TV, accessibility, localization and reduced-motion polish

Pinned baseline: `Mikeyphw/vlc-redesign-android/main` @ `1a75e68638b0045ceca10a725bb6dee3ba44aad6`, tree `0df9e8c9811ee3f953159325f10fc71fcae9f2f1`; Devtool `main` @ `6a670f9695a4461c2e75ac5df17bde25fc469077` (launcher 3.2.1).

## Scope

- Retain the existing VLC/KuchiSofts TV implementation and focus navigation. In the TV player title bar, hide zero-alpha legacy phone controls from accessibility traversal, give each TV button a visible focus ring and increase focus targets from 28 dp to 36 dp without changing the bar geometry or playback actions.
- Improve the TV mini-player: focused-card stroke, queue affordance increased to 48 × 48 dp within a 48 dp row, its decorative icons excluded from reading order, and media-specific translated TalkBack label. Retain all service/media/queue behavior.
- TV Settings sidebar: expose selected page in accessibility state, remove deferred callbacks when its view is destroyed, and apply reduced-motion-aware scroll behavior. Keep D-pad focus restoration and 2-pane layout behavior.
- Interface → Accessibility: add opt-in `rd_reduce_motion` (`false`), respecting system animator settings (`ValueAnimator.areAnimatorsEnabled` API 26+; lower-API global scale). No global animation setting is written. Choice is reversible with existing preferences and app lifecycle. English and Brazilian Portuguese strings share exact format arguments.

## Assurance

- No playback engine, media-library schema, network/cast/DRM, video rendering, upstream merge or release signing changes.
- Current `ci/tests` discovery is retained. Native validation runs structural/negative checks, existing workflow policy, and MediaLibrary source-lock checks. GitHub-hosted four-ABI native, verified Maven AAR, Kotlin/JVM and debug APK remain required.
- No obsolete or duplicate gates were found in the changed scope; none were removed. Existing coverage must not be skipped to pass this milestone.

## Remaining acceptance

- Manual TV/phone/foldable matrix (D-pad loops, OK/Back, TalkBack, keyboard, landscape, resize/recreation, large fonts, RTL, contrast, English and pt-BR, system animations off/on, reduced motion on/off) is **not claimed passed** by source tests.
- Performance and startup/scroll measurement require hosted/device baselines with comparable KuchiSofts build; no device or microbenchmark claim is made here. The implementation intentionally avoids new polling and retains current media update cadence.
- Release/signing checks belong to M7; require distinct application ID and signed-install acceptance.

## Next roadmap

**M7 — Release & Maintenance:** signed release, distinct identity, SBOM/licenses, provenance, staged install/upgrade, and continuing upstream integration.
