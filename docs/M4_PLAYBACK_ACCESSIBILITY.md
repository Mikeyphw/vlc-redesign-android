# M4: Playback UI semantics and accessibility (first consolidated M4 delivery)

This changes only existing presentation delegates/layouts. VideoLAN LibVLC playback,
MediaSession, casting services, PiP policy, media library, the four native ABIs and
media selection handlers are intentionally unchanged.

## Current behavior

- Video HUD quick chips announce whether they adjust subtitle or audio delay plus
  their current signed duration in milliseconds, rather than a bare number.
- Rewind and forward controls announce the configured jump duration whenever the
  selected player-bar profile is materialized. Existing play/pause, seekable and
  casting-state transitions remain in their original delegates.
- Audio playback chips speak the playback speed/sleep timer type and value, not
  only the numeric chip text; audio seek progress has an elapsed/total spoken value.
- Decorative video/audio numeric jump overlays no longer become separate TalkBack
  focus stops. The actual transport controls remain accessible and clickable.
- Existing strings (`spu_delay`, `audio_delay`, `playback_speed`, `sleep_title`,
  `talkback_out_of`, `talkback_action_rewind`, `talkback_action_forward`) are reused.
  No untranslated hardcoded **labels**, obsolete gates or duplicate player logic.

## Review / acceptance matrix

1. Phone, dark/light/AMOLED, large fonts, screen reader on: video HUD seek/jump
   controls; audio and subtitle delay chips; playback speed, sleep countdown.
2. Audio player expanded/mini: speed chip, sleep timer, seek progress; verify
   TalkBack does not read each visual jump counter twice.
3. Landscape and portrait, tablet, Android TV D-pad focus and custom HUD bar;
   verify seek/track selection and return focus.
4. Seekable video/stream not seekable; 10s and custom jump delays; changing
   playback speed on a remote stream; lock/unlock player.
5. Subtitle track changes, dual subtitles, audio track selectors, PiP
   enter/exit, cast connect/disconnect, notification media controls and
   background playback: all behavior must remain stable.
6. Hosted CI must compile Android/Kotlin/XML, run JVM tests, assemble debug APK,
   verify the four native ABI artifacts and Maven AAR at **actual M4 PR HEAD**.
   Static Python source tests are complementary, not proof of device behavior.

## Stacked branch and integration

M4 is built on the exact unmerged M3 PR head (12c424d2fa4aa004ec7a4fb6df7c524115220a56)
and should target M3 feature branch as PR base; it is **not safe to merge** until
M3 has been merged and M4's PR is retargeted/qualified against latest main.
The immutable bootstrap must refuse if either parent branch or main has drifted.
No rebase, force-push, reset or automatic merge is performed by the delivery.
