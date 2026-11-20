"""M6 TV accessibility/motion integration source contracts; hosted Android compile is separate."""
from pathlib import Path
import re
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "application/vlc-android/res"
SRC = ROOT / "application/vlc-android/src/org/videolan/vlc/gui"


def read(path):
    return path.read_text(encoding="utf-8")


class M6TvAccessibility(unittest.TestCase):
    def test_opt_in_and_existing_interface_screen(self):
        root = ET.parse(RES / "xml/rd_settings_interface.xml").getroot()
        nodes = [n for n in root.iter() if n.attrib.get("{http://schemas.android.com/apk/res/android}key") == "rd_reduce_motion"]
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0].tag, "CheckBoxPreference")
        self.assertEqual(nodes[0].attrib["{http://schemas.android.com/apk/res/android}defaultValue"], "false")
        self.assertEqual(nodes[0].attrib["{http://schemas.android.com/apk/res/android}title"], "@string/rd_m6_reduce_motion")

    def test_reduced_motion_and_system_animation_are_both_respected(self):
        src = read(SRC / "preferences/rd/RdMotionPolicy.kt")
        self.assertIn('const val KEY = "rd_reduce_motion"', src)
        self.assertIn("getBoolean(KEY, false)", src)
        self.assertIn("ValueAnimator.areAnimatorsEnabled()", src)
        self.assertIn("ANIMATOR_DURATION_SCALE", src)
        self.assertIn("scroll.smoothScrollTo(x, y)", src)
        self.assertIn("scroll.scrollTo(x, y)", src)

    def test_settings_change_refreshes_effect(self):
        src = read(SRC / "preferences/rd/RdSettingsPage.kt")
        self.assertRegex(src, r"RdMotionPolicy\.KEY\s*->\s*\{\s*activity\.setRestart\(\)\s*activity\.recreate\(\)")

    def test_sidebar_restores_focus_and_removes_posted_callbacks(self):
        src = read(SRC / "preferences/rd/RdSettingsSidebar.kt")
        self.assertIn("RdMotionPolicy.scrollTo(scroll, 0, 0)", src)
        self.assertIn("RdMotionPolicy.scrollTo(scroll, 0, list.height)", src)
        self.assertIn("override fun onDestroyView()", src)
        self.assertIn("row.removeCallbacks(pending)", src)
        self.assertIn("ViewCompat.setStateDescription(row,", src)
        self.assertIn("fun focusCurrent(): Boolean", src)

    def test_player_bar_focus_and_hidden_phone_hud(self):
        src = read(SRC / "video/RdTvPlayerTopBar.kt")
        self.assertIn("IMPORTANT_FOR_ACCESSIBILITY_NO_HIDE_DESCENDANTS", src)
        self.assertIn("setOnFocusChangeListener", src)
        self.assertIn("setStroke(if (has) 2.dp else 0", src)
        self.assertIn("FrameLayout.LayoutParams(36.dp, 36.dp)", src)

    def test_mini_queue_target_and_now_playing_label(self):
        src = read(SRC / "tablet/RdTvMiniPlayer.kt")
        self.assertIn("LinearLayout.LayoutParams(48.dp, 48.dp)", src)
        self.assertIn("LinearLayout.LayoutParams(359.dp, 48.dp)", src)
        self.assertIn("R.string.rd_m6_mini_now_playing", src)
        self.assertIn("setOnFocusChangeListener", src) if "setOnFocusChangeListener" in src else self.assertIn("onFocusChangeListener", src)
        self.assertIn("marginEnd = 6.dp", src)

    def test_localization_keys_and_format_arguments(self):
        english = ET.parse(RES / "values/rd_m6_strings.xml").getroot()
        brazilian = ET.parse(RES / "values-pt-rBR/rd_m6_strings.xml").getroot()
        a = {n.attrib["name"]: n.text for n in english}
        b = {n.attrib["name"]: n.text for n in brazilian}
        self.assertEqual(set(a), set(b))
        self.assertEqual(set(a), {"rd_m6_reduce_motion", "rd_m6_reduce_motion_summary", "rd_m6_current_page", "rd_m6_mini_now_playing"})
        self.assertEqual(a["rd_m6_mini_now_playing"].count("%1$s"), 1)
        self.assertEqual(b["rd_m6_mini_now_playing"].count("%1$s"), 1)

    def test_negative_contract_for_deleted_motion_guard(self):
        src = read(SRC / "preferences/rd/RdMotionPolicy.kt")
        def compliant(text):
            return all(token in text for token in (
                "getBoolean(KEY, false)",
                "ValueAnimator.areAnimatorsEnabled()",
                "ANIMATOR_DURATION_SCALE",
            ))
        self.assertTrue(compliant(src))
        self.assertFalse(compliant(src.replace("ValueAnimator.areAnimatorsEnabled()", "true")))
        self.assertFalse(compliant(src.replace("ANIMATOR_DURATION_SCALE", "UNSAFE_SCALE")))
        self.assertNotIn("setDurationScale(0", src)


if __name__ == "__main__":
    unittest.main()
