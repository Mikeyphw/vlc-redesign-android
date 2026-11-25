# M11 — Playback startup and subtitle font-cache reliability

## Scope and behavior

This overlay leaves the signing/identity pipeline and libvlc/medialibrary pins unchanged. It hardens the application-side warmup and playback lifecycle; it does not impose a deadline on native decoder initialization or cancel a running JNI scan.

- One app-owned IO warmup per process. VLC4 bypasses it, audio-only and benchmark starts do not wait. A video/stream can wait up to 2 seconds, with the existing throttled toast only after a 250 ms grace. After the first timeout the process bypasses further pending waits; a later completed native result remains usable. Caller cancellation propagates; it cannot cancel the shared scan.
- An atomic, persisted attempt is recorded before JNI. A native success clears the count; three failed/interrupted attempts suppress further warmups for the same fingerprint. OS/build, ABI, app update, font directory metadata and policy version invalidate the budget. A previous success is revalidated once per process rather than assuming a cache survived storage eviction. Failed preference commits or unavailable JNI fall back without blocking playback indefinitely. The native LibVLC reference is retained through warmup, including if effects restart occurs.
- Playback starts bind the requested queue item and generation before waiting. A new request, load, stop, effects restart or service destruction invalidates stale starts. Async URI/subtitle work is checked before opening native playback. PlayerController serializes starts, binds a retained native player, checks source validity after IO, and releases caller-owned media on abandoned starts. TV preview tunes cancel superseded waits, wait for an active surface before creating media, and stop/retune after surface loss and restoration. No stale preview should start after release.

## Acceptance matrix

| ID | Required behavior | Evidence gate |
|---|---|---|
| M11-P01 | Single-flight IO cache, bounded application wait, no repeated waiting, cancellation isolation | Kotlin/JVM regression and Android cold-start test |
| M11-P02 | Persistent attempt and success, invalidation, native cache eviction revalidation, safe native reference and failure fallback | Kotlin policy test, source wiring, hosted compile and device fault/upgrade tests |
| M11-P03 | Audio-only/benchmark bypass; preserve video, subtitles, resume, casting, queue and effects settings | Hosted build and physical playback tests |
| M11-P04 | No stale native startup after replacement, stop, cancel, or service destruction; media references cleaned | JVM generation test, source guard, rapid-switch device test |
| M11-P05 | TV tune/release/surface recreation and repeat previews | Source guard, hosted build, Android TV device test |

## Physical-device qualification (separate, not inferred from tests)

On both package identities, record source-bound APK hash and package/version, device model/API, warmup log outcomes and elapsed monotonic time. Test clean install with text subtitles, cold relaunch with a valid cache, deleted cache through normal app storage controls, a failing cache and three interrupted starts, app update, video then rapid next/previous/stop, audio-only, resume confirmation, external subtitles and casting, PiP, effects restart, service destruction. On TV test tune before surface, rapid retune, surface loss/recreation, end-of-preview and release while waiting. Confirm no stale playback, no repeated toast or app-side warmup wait after timeout, normal playback fallback, and no native crash or ANR. Do not claim that a bounded coroutine wait guarantees a bound on native fontconfig/decoder startup. Rollback is a normal source revert of this overlay; no app data deletion or signing changes are required by the implementation.
