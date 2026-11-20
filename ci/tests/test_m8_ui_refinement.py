"""M8 source contracts: run via existing unittest discovery, no Android SDK required."""
from pathlib import Path
import re
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / 'application/vlc-android'
NS = {'android': 'http://schemas.android.com/apk/res/android'}
ID = '{http://schemas.android.com/apk/res/android}id'


def xml(name):
    return ET.parse(APP / name).getroot()


def has_id(root, value):
    return any(el.attrib.get(ID) == '@+id/' + value for el in root.iter())


class M8UXContracts(unittest.TestCase):
    def test_xml_parses(self):
        paths = [
            'res/layout/rd_home_fragment.xml', 'res/layout/rd_home_card.xml',
            'res/layout/rd_home_section.xml', 'res/layout/onboarding_scanning.xml',
            'res/layout/audio_player.xml', 'res/layout/search_activity.xml',
            'res/layout/player_overlay_info.xml', 'res/layout/player_hud.xml',
            'res/values/rd_m8_strings.xml', 'res/values-pt-rBR/rd_m8_strings.xml',
            'res/drawable/rd_m8_duration_badge.xml',
        ]
        for path in paths:
            with self.subTest(path=path):
                self.assertIsNotNone(xml(path))

    def test_empty_library_action(self):
        self.assertTrue(has_id(xml('res/layout/rd_home_fragment.xml'), 'rd_m8_pick_folders'))
        src = (APP/'src/org/videolan/vlc/gui/HomeFragment.kt').read_text()
        self.assertIn('SecondaryActivity.STORAGE_BROWSER',src)
        self.assertIn('emptyAction.visibility = View.VISIBLE',src)
        self.assertIn('emptyAction.visibility = View.GONE',src)
        self.assertIn('R.string.rd_m8_empty_library_help',src)

    def test_onboarding_requires_explicit_checkbox(self):
        r=xml('res/layout/onboarding_scanning.xml')
        self.assertTrue(any(e.attrib.get('{http://schemas.android.com/apk/res/android}text') == '@string/rd_m8_folder_checkbox_hint' for e in r.iter()))
        # Preserve the existing explicit folder selection flow; never auto-index device root.
        svc=(APP/'src/org/videolan/vlc/MediaParsingService.kt').read_text()
        self.assertIn('LibraryScopeGuard.allowed',svc)

    def test_card_duration_and_responsive_layout(self):
        card=xml('res/layout/rd_home_card.xml')
        self.assertTrue(has_id(card,'rd_m8_duration_badge'))
        src=(APP/'src/org/videolan/vlc/gui/HomeFragment.kt').read_text()
        self.assertIn('b.duration = if (video && media.length > 0L)',src)
        self.assertIn('availablePhoneWidth',src)
        self.assertIn('RdMotionPolicy.shouldAnimate',src)

    def test_audio_and_search_accessibility(self):
        a=(APP/'src/org/videolan/vlc/gui/audio/AudioPlayer.kt').read_text()
        s=(APP/'src/org/videolan/vlc/gui/SearchActivity.kt').read_text()
        self.assertIn('binding.header.contentDescription = getString(R.string.rd_m8_expand_player)',a)
        self.assertTrue(has_id(xml('res/layout/search_activity.xml'),'rd_m8_search_help'))
        self.assertIn('binding.rdM8SearchHelp.visibility',s)

    def test_string_keys_are_parallel(self):
        en=xml('res/values/rd_m8_strings.xml')
        pt=xml('res/values-pt-rBR/rd_m8_strings.xml')
        self.assertEqual({el.attrib['name'] for el in en}, {el.attrib['name'] for el in pt})
        self.assertEqual(len(en),len({el.attrib['name'] for el in en}))

    def test_playback_ovl_and_screenshot_capture(self):
        seek=xml('res/layout/player_hud.xml')
        controls=[e for e in seek.iter() if e.attrib.get(ID)=='@+id/player_overlay_seekbar']
        self.assertEqual(len(controls),1)
        self.assertEqual(controls[0].attrib.get('{http://schemas.android.com/apk/res/android}layout_height'),'48dp')
        screenshot=(ROOT/'application/app/src/androidTest/java/org/videolan/vlc/PhoneScreenhotsInstrumentedTest.kt').read_text()
        self.assertIn('ScreenshotUtil.takeScreenshot(10, "m8_home")',screenshot)
        self.assertIn('ScreenshotUtil.takeScreenshot(11, "m8_mini_player")',screenshot)


if __name__=='__main__':
    unittest.main()
