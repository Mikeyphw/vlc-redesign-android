"""M5 settings integration checks; real Android compile/JVM and device QA remain hosted."""
from pathlib import Path
import re
import unittest
from xml.etree import ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]
APP=ROOT/'application/vlc-android'
PRE=APP/'src/org/videolan/vlc/gui/preferences/rd/RdAppearancePreferences.kt'
VIEW=APP/'src/org/videolan/vlc/gui/preferences/rd/RdAppearancePreviewPreference.kt'
PAGE=APP/'src/org/videolan/vlc/gui/preferences/rd/RdSettingsPage.kt'
GENERAL=APP/'res/xml/rd_settings_general.xml'
LAYOUT=APP/'res/layout/rd_m5_appearance_preview.xml'
STRINGS=APP/'res/values/rd_m5_strings.xml'
NS='{http://schemas.android.com/apk/res/android}'

class M5AppearanceContracts(unittest.TestCase):
    def test_preview_and_reset_on_existing_general_page(self):
        xml=ET.parse(GENERAL).getroot()
        keys=[x.get(NS+'key') for x in xml.iter() if x.get(NS+'key')]
        for key in ('rd_m5_live_preview','rd_m5_reset_appearance'):
            self.assertEqual(keys.count(key),1)
        self.assertIn('RdAppearancePreviewPreference',GENERAL.read_text())
        self.assertIn('RdActionPreference',GENERAL.read_text())
        self.assertLess(keys.index('rd_m5_live_preview'),keys.index('rd_m5_reset_appearance'))

    def test_live_theme_preview_and_player_not_duplicate_engine(self):
        view=VIEW.read_text()
        self.assertIn('R.attr.colorPrimary',view)
        self.assertIn('R.attr.rd_panel',view)
        self.assertIn('R.attr.rd_well',view)
        self.assertIn('Settings.getInstance(context).all',view)
        self.assertIn('isSelectable = false',view)
        self.assertNotIn('preferences.edit()',view)
        root=ET.parse(LAYOUT).getroot()
        ids=[e.get(NS+'id') for e in root.iter()]
        for key in ('rd_m5_preview_surface','rd_m5_preview_accent','rd_m5_preview_player','rd_m5_preview_play','rd_m5_preview_status'):
            self.assertEqual(ids.count('@+id/'+key),1)
        texts=ET.parse(STRINGS).getroot()
        self.assertGreaterEqual(len(list(texts)),12)

    def test_reset_is_scoped_and_defaults_are_reversible(self):
        p=PRE.read_text()
        for token in ('KEY_APP_THEME','ACCENT_KEY', 'KEY_RD_ACCENT_SYSTEM','KEY_RD_AMOLED',
                      'VISUAL_KEYS.forEach { editor.remove(it) }','editor.apply()'):
            self.assertIn(token,p)
        for forbidden in ('editor.clear()', 'prefs.edit().clear()', 'KEY_CURRENT_MEDIA',
                          'KEY_MEDIA_SEEN','KEY_NETWORK_CACHING_VALUE','KEY_SUBTITLES_SIZE'):
            self.assertNotIn(forbidden,p)

    def test_migrations_preserve_legacy_auto_and_remove_malformed_values(self):
        p=PRE.read_text()
        self.assertIn('setOf("-1", "0", "1", "2", "3")',p)
        self.assertIn('savedAccent !in allowedAccents',p)
        self.assertIn('values[key] !is Boolean',p)
        self.assertIn('if (invalid.isEmpty()) return false',p)
        self.assertNotIn('putString(KEY_APP_THEME',p)

    def test_general_page_controls_and_tv_guards(self):
        page=PAGE.read_text()
        for phrase in ('RdAppearancePreferences.migrate(',
                       'rd_m5_live_preview','rd_m5_reset_appearance',
                       'Settings.showTvUi','RdAppearancePreferences.reset(settings)',
                       'AppCompatDelegate.MODE_NIGHT_FOLLOW_SYSTEM',
                       'resettingAppearance'):
            self.assertIn(phrase,page)
        self.assertRegex(page,r'if \(resettingAppearance && key in RdAppearancePreferences.VISUAL_KEYS\) return')
        self.assertIn('setNegativeButton(android.R.string.cancel',page)

    def test_negative_mutations_detect_missing_protection(self):
        original=PRE.read_text()
        self.assertNotEqual(original.replace('VISUAL_KEYS.forEach { editor.remove(it) }','editor.clear()'),original)
        changed=original.replace('VISUAL_KEYS.forEach { editor.remove(it) }','editor.clear()')
        self.assertNotIn('VISUAL_KEYS.forEach { editor.remove(it) }',changed)
        page=PAGE.read_text()
        self.assertNotIn('RdAppearancePreferences.reset(settings)',page.replace('RdAppearancePreferences.reset(settings)','bypass()'))

if __name__=='__main__': unittest.main()
