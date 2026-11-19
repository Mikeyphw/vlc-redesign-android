"""M4 active playback view contracts, including fail-closed negative mutations.

Complements, never substitutes for, hosted Kotlin/build and device PiP/TV/TalkBack tests.
This suite runs from current source through the existing ci/tests discovery.
"""
import re
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / 'application' / 'vlc-android'
SRC = APP / 'src' / 'org' / 'videolan' / 'vlc' / 'gui'
NS = '{http://schemas.android.com/apk/res/android}'


def read(path):
    return (SRC / path).read_text(encoding='utf-8')


def labels_present(s):
    return all(x in s for x in (
        'hudRightBinding.spuDelayQuickAction.contentDescription =',
        'hudRightBinding.audioDelayQuickAction.contentDescription =',
        'player.getString(R.string.spu_delay)',
        'player.getString(R.string.audio_delay)',
        'val subtitleDelayMs =',
        'val audioDelayMs =',
        'R.string.talkback_action_rewind, Settings.videoJumpDelay.toString()',
        'R.string.talkback_action_forward, Settings.videoJumpDelay.toString()',
    ))


def audio_semantics(s):
    return all(x in s for x in (
        'binding.playbackSpeedQuickAction.contentDescription =',
        'getString(R.string.playback_speed)',
        'binding.sleepQuickAction.contentDescription =',
        'getString(R.string.sleep_title)',
        'binding.timeline.contentDescription =',
        'getString(R.string.talkback_out_of,',
        'TalkbackUtil.millisToString(requireActivity(), progress.time)',
        'TalkbackUtil.millisToString(requireActivity(), progress.length)',
    ))


def res_id(path, view_id):
    root = ET.parse(APP / 'res' / 'layout' / path).getroot()
    views = [x for x in root.iter() if x.get(NS+'id') == '@+id/'+view_id]
    if len(views) != 1:
        raise AssertionError('Expected one element: '+view_id)
    return views[0]


class M4PlaybackAccessibilityContracts(unittest.TestCase):
    def test_video_status_chips_announce_kind_and_value(self):
        s = read('video/VideoPlayerOverlayDelegate.kt')
        self.assertTrue(labels_present(s))
        self.assertIn('hudRightBinding.spuDelayQuickAction.text = "$subtitleDelayMs ms"', s)
        self.assertIn('hudRightBinding.audioDelayQuickAction.text = "$audioDelayMs ms"', s)

    def test_video_labels_missing_mutations_are_rejected(self):
        s = read('video/VideoPlayerOverlayDelegate.kt')
        for phrase in ('hudRightBinding.spuDelayQuickAction.contentDescription =',
                       'hudRightBinding.audioDelayQuickAction.contentDescription =',
                       'R.string.talkback_action_rewind, Settings.videoJumpDelay.toString()',
                       'R.string.talkback_action_forward, Settings.videoJumpDelay.toString()'):
            self.assertFalse(labels_present(s.replace(phrase, 'REMOVED')))

    def test_video_controls_retain_seek_and_track_contracts(self):
        s = read('video/VideoPlayerOverlayDelegate.kt')
        for phrase in ('fun updateSeekable(seekable: Boolean)',
                       'hudBinding.playerOverlaySeekbar.isEnabled = seekable',
                       'hudBinding.playerOverlayTracks', 'hudRightBinding.videoRenderer'):
            self.assertIn(phrase, s)

    def test_audio_speed_sleep_seek_labels(self):
        s = read('audio/AudioPlayer.kt')
        self.assertTrue(audio_semantics(s))
        self.assertIn('if (progress.length > 0L)', s)
        self.assertIn('else getString(R.string.seek)', s)

    def test_audio_accessibility_negative_mutations(self):
        s = read('audio/AudioPlayer.kt')
        for phrase in ('binding.timeline.contentDescription =',
                       'getString(R.string.talkback_out_of,',
                       'binding.sleepQuickAction.contentDescription =',
                       'binding.playbackSpeedQuickAction.contentDescription ='):
            self.assertFalse(audio_semantics(s.replace(phrase, 'REMOVED')))

    def test_decorative_video_seek_digits_are_not_focus_targets(self):
        for view_id in ('player_overlay_rewind_text', 'player_overlay_forward_text'):
            v = res_id('player_hud.xml', view_id)
            self.assertEqual(v.get(NS+'importantForAccessibility'), 'no')
        # The actual buttons, unlike their decorative labels, stay actionable.
        for view_id in ('player_overlay_rewind','player_overlay_forward'):
            v = res_id('player_hud.xml', view_id)
            self.assertNotEqual(v.get(NS+'importantForAccessibility'), 'no')

    def test_decorative_audio_seek_digits_are_not_focus_targets(self):
        for view_id in ('audio_rewind_text', 'audio_forward_text'):
            v = res_id('audio_player.xml', view_id)
            self.assertEqual(v.get(NS+'importantForAccessibility'), 'no')
        for view_id in ('audio_rewind_10', 'audio_forward_10'):
            v = res_id('audio_player.xml', view_id)
            self.assertEqual(v.get(NS+'clickable'), 'true')

    def test_no_playback_engine_or_medialibrary_change(self):
        self.assertTrue((ROOT/'ci/medialibrary.py').is_file())
        self.assertTrue((ROOT/'config/delivery-required-ci.json').is_file())
        self.assertTrue((APP/'src/org/videolan/vlc/gui/video/VideoPlayerActivity.kt').is_file())
        self.assertTrue((APP/'src/org/videolan/vlc/gui/video/VideoTouchDelegate.kt').is_file())
        self.assertTrue((APP/'src/org/videolan/vlc/gui/video/RdOsd.kt').is_file())


if __name__ == '__main__':
    unittest.main()
