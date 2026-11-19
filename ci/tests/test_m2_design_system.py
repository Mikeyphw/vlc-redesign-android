"""M2 theme-token regression checks: no generated file rewrites, opt-in dark-only AMOLED."""
import re
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / 'application/vlc-android/res'
CODE = ROOT / 'application/vlc-android/src/org/videolan/vlc'


def xml(path):
    tree = ET.parse(path)
    root = tree.getroot()
    if root.tag not in ('resources', 'PreferenceScreen', 'androidx.preference.PreferenceScreen'):
        raise AssertionError(f'Unexpected Android XML document: {path}')
    return root


def named(root, kind):
    return {e.attrib.get('name'): e for e in root.findall(kind)}


class DesignSystemM2(unittest.TestCase):
    def test_token_set(self):
        root=xml(RES/'values/rd_ds_tokens.xml')
        vals={n: (e.text or '').strip() for n,e in named(root,'dimen').items()}
        self.assertEqual({n:vals[n] for n in ['rd_ds_radius_small','rd_ds_radius_medium','rd_ds_radius_card','rd_ds_radius_large']},
                         dict(rd_ds_radius_small='6dp',rd_ds_radius_medium='10dp',rd_ds_radius_card='12dp',rd_ds_radius_large='14dp'))
        self.assertEqual(vals['rd_ds_touch_target'],'48dp')
        for key in ('xs','sm','md','lg','xl','2xl'):
            self.assertIn('rd_ds_space_'+key,vals)
        self.assertEqual(len(vals),len(named(root,'dimen')))

    def test_light_night_semantic_roles(self):
        light=named(xml(RES/'values/rd_ds_tokens.xml'),'color')
        night=named(xml(RES/'values-night/rd_ds_tokens.xml'),'color')
        self.assertEqual(set(light),set(night))
        self.assertEqual(set(light),{'rd_ds_surface','rd_ds_panel','rd_ds_text','rd_ds_text_muted'})
        for item in [*light.values(),*night.values()]:
            self.assertTrue((item.text or '').startswith('@color/rd_'))

    def test_overlay_true_black_and_no_accent_override(self):
        root=xml(RES/'values/rd_amoled_theme.xml')
        colors={k: (v.text or '').strip() for k,v in named(root,'color').items()}
        self.assertEqual(colors['rd_amoled_black'],'#FF000000')
        style=named(root,'style')['ThemeOverlay.Redesign.Amoled']
        items={e.attrib.get('name'):e.text for e in style.findall('item')}
        for key in ('android:windowBackground','background_default','header_background','rd_well','card_background'):
            self.assertEqual(items[key],'@color/rd_amoled_black')
        self.assertTrue({'colorSurface','rd_panel','bottom_sheet_background'} <= set(items))
        self.assertFalse(any(key.startswith('colorAccent') or key in {'colorPrimary','colorSecondary','rd_accent_dim','rd_accent_bright'} for key in items))

    def test_preference_key_default_and_localization(self):
        root=xml(RES/'xml/rd_settings_general.xml')
        matches=[e for e in root.iter() if e.attrib.get('{http://schemas.android.com/apk/res/android}key') == 'rd_amoled']
        self.assertEqual(len(matches),1)
        self.assertEqual(matches[0].tag,'CheckBoxPreference')
        self.assertEqual(matches[0].attrib['{http://schemas.android.com/apk/res/android}defaultValue'],'false')
        for directory in ('values','values-pt-rBR'):
            strings=named(xml(RES/directory/'rd_amoled_strings.xml'),'string')
            self.assertEqual(set(strings),{'rd_amoled_title','rd_amoled_summary'})
            self.assertTrue(all((e.text or '').strip() for e in strings.values()))

    def test_dark_only_and_user_choice_preserved(self):
        helper=(CODE/'gui/helpers/RdAmoledTheme.kt').read_text()
        tools=(CODE/'gui/helpers/UiTools.kt').read_text()
        prefs=(CODE/'gui/preferences/rd/RdSettingsPage.kt').read_text()
        self.assertIn('const val KEY_RD_AMOLED = "rd_amoled"',helper)
        self.assertIn('if (Settings.showTvUi) return',helper)
        self.assertIn('if (!Settings.getInstance(activity).getBoolean(KEY_RD_AMOLED, false)) return',helper)
        self.assertRegex(helper,r'"1"\s*->\s*false')
        self.assertRegex(helper,r'"2"\s*->\s*true')
        self.assertIn('Configuration.UI_MODE_NIGHT_MASK',helper)
        self.assertIn('if (!dark) return',helper)
        self.assertIn('ThemeOverlay_Redesign_Amoled',helper)
        self.assertIn('AppCompatDelegate.setDefaultNightMode(Integer.valueOf(string!!))\n    applyRdAmoledTheme(this, string)\n    applyAccent()',tools)
        self.assertIn('org.videolan.vlc.gui.helpers.KEY_RD_AMOLED',prefs)
        self.assertIn('KEY_APP_THEME -> {',prefs)
        self.assertIn('Settings.showTvUi) pref<Preference>(org.videolan.vlc.gui.helpers.KEY_RD_AMOLED)?.isVisible = false',prefs)
        self.assertNotIn('applyRdAmoledTheme(this, string)',tools.split('forcedTheme()?.let {',1)[1].split('return',1)[0])

    def test_primary_buttons_and_shapes_use_existing_styles(self):
        root=xml(RES/'values/redesign_styles.xml')
        styles=named(root,'style')
        for name in ('Widget.Redesign.Button','Widget.Redesign.Button.Outlined'):
            items={e.attrib.get('name'): (e.text or '').strip() for e in styles[name].findall('item')}
            self.assertEqual(items['android:minHeight'],'@dimen/rd_ds_touch_target')
        for name,token in [('Small','small'),('Medium','medium'),('Large','large'),('Card','card')]:
            items={e.attrib.get('name'): (e.text or '').strip() for e in styles['ShapeAppearance.Redesign.'+name].findall('item')}
            self.assertEqual(items['cornerSize'],'@dimen/rd_ds_radius_'+token)
        player={e.attrib.get('name'):(e.text or '').strip() for e in styles['Widget.Redesign.Button.Outlined.Player'].findall('item')}
        self.assertEqual(player.get('android:minHeight'),'36dp')

    def test_preserve_generated_resources(self):
        for path in (ROOT/'application/resources/src/main/res/values/redesign_colors.xml',
                     ROOT/'application/resources/src/main/res/values-night/redesign_colors.xml'):
            self.assertIn('Generated by buildsystem/redesign/import_design.py',path.read_text())
        self.assertTrue((RES/'values/redesign_accents.xml').exists())
        self.assertTrue((RES/'values-night/redesign_accents.xml').exists())
        self.assertTrue((RES/'values-v31/redesign_accent_system.xml').exists())
        self.assertTrue((RES/'values-night-v31/redesign_accent_system.xml').exists())


if __name__=='__main__':
    unittest.main()
