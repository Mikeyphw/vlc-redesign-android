"""Current M3 library/navigation behavioral contracts, including negative mutation checks.

These fast static contracts complement (do not replace) hosted Android JVM, resource,
layout, device and keyboard tests. They protect active code rather than historical handoffs.
"""
import re, unittest
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]
APP=ROOT/'application/vlc-android'
JAVA=APP/'src/org/videolan/vlc/gui'


def read(name): return (JAVA/name).read_text(encoding='utf-8')


def nav_valid(source):
    return ("state?.getInt(EXTRA_TARGET, 0)" in source and
            'putString(savedPageKey, pageNames.getValue(id))' in source and
            'putInt(KEY_FRAGMENT_ID, id)' in source and
            'pageNames.entries.firstOrNull' in source and
            'R.id.nav_tv && !org.videolan.vlc.livetv.LiveTv.enabled' in source and
            'if (currentFragment != null && currentFragmentId in pages)' in source)


def search_valid(source):
    return ("searchJob?.cancel()" in source and
            "val generation = ++searchGeneration" in source and
            'generation != searchGeneration' in source and
            'clearResults()' in source and
            'STATE_SEARCH_QUERY' in source and
            'binding.searchEditText.addTextChangedListener(this)' in source and
            'EmptyLoadingState.LOADING' in source and
            'if (normalized.isEmpty())' in source and
            'if (!query.isNullOrBlank())' in source and
            'private fun performSearh' not in source)


class M3NavigationAndLibrary(unittest.TestCase):
    def test_navigation_restoration_is_stable_and_validated(self):
        source=read('helpers/Navigator.kt')
        self.assertTrue(nav_valid(source))
        self.assertIn('R.id.nav_home -> "rd/home"',source)
        self.assertIn('R.id.nav_playlists -> "rd/playlists"',source)
        self.assertIn('R.id.nav_more -> "rd/more"',source)
        self.assertLess(source.index('val stable = settings.getString(savedPageKey'),source.index('settings.getInt(KEY_FRAGMENT_ID, defaultFragmentId)'))

    def test_restoration_negatives(self):
        source=read('helpers/Navigator.kt')
        self.assertFalse(nav_valid(source.replace('putString(savedPageKey, pageNames.getValue(id))','// intentionally removed')))
        self.assertFalse(nav_valid(source.replace('state?.getInt(EXTRA_TARGET, 0)','0')))
        self.assertFalse(nav_valid(source.replace('R.id.nav_tv && !org.videolan.vlc.livetv.LiveTv.enabled','false')))

    def test_activity_restoration_without_force_unwrap(self):
        source=read('MainActivity.kt')
        self.assertIn('current?.let { supportFragmentManager.putFragment(outState, "current_fragment", it) }',source)
        self.assertNotIn('putFragment(outState, "current_fragment", current!!)',source)
        self.assertIn('outState.putInt(EXTRA_TARGET, currentFragmentId)',source)

    def test_video_subtab_persisted_in_existing_preferences(self):
        source=read('video/VideoBrowserFragment.kt')
        self.assertIn('private const val RD_VIDEO_CURRENT_TAB = "rd_video_current_tab"',source)
        self.assertIn('if (savedInstanceState == null)',source)
        self.assertIn('setCurrentItem(selected, false)',source)
        self.assertIn('tab.position.coerceIn(0, 1)',source)
        self.assertIn('fun filter(query: String)',source)
        self.assertIn('fun restoreList()',source)

    def test_search_cancellation_generation_and_state(self):
        source=read('SearchActivity.kt')
        self.assertTrue(search_valid(source))
        self.assertIn('binding.audioEmptyLoading.state = if (result.isEmpty)',source)
        self.assertIn('outState.putString(STATE_SEARCH_QUERY',source)
        self.assertIn('private fun clearResults()',source)
        self.assertIn('as? SearchResultAdapter)?.add(emptyArray())',source)
        self.assertLess(source.index('initializeLists()'),source.index('binding.searchEditText.addTextChangedListener(this)'))

    def test_search_negative_regressions(self):
        source=read('SearchActivity.kt')
        self.assertFalse(search_valid(source.replace('searchJob?.cancel()','// removed')))
        self.assertFalse(search_valid(source.replace('generation != searchGeneration','false')))
        self.assertFalse(search_valid(source.replace('clearResults()','// removed')))
        self.assertFalse(search_valid(source.replace('STATE_SEARCH_QUERY','STATE_REMOVED')))

    def test_result_artwork_cleared_when_row_recycled(self):
        source=read('SearchResultAdapter.kt')
        self.assertIn('UiTools.getDefaultCover(holder.itemView.context, item) else null',source)
        self.assertIn('fun add(newList: Array<MediaLibraryItem>)',source)

    def test_playlist_empty_not_conflated_with_empty_search(self):
        source=read('PlaylistFragment.kt')
        self.assertIn('empty && viewModel.filterQuery != null -> EmptyLoadingState.EMPTY_SEARCH',source)
        self.assertIn('empty -> EmptyLoadingState.EMPTY',source)
        self.assertIn('viewModel.provider.onlyFavorites -> EmptyLoadingState.EMPTY_FAVORITES',source)
        self.assertIn('viewModel.provider.loading.value == true && empty -> EmptyLoadingState.LOADING',source)

    def test_home_card_accessibility_and_large_text(self):
        source=read('HomeFragment.kt')
        self.assertIn('b.root.contentDescription = listOfNotNull(',source)
        self.assertIn('b.subtitle?.takeIf { it.isNotBlank() }',source)
        root=ET.parse(APP/'res/layout/rd_home_card.xml').getroot()
        ns='{http://schemas.android.com/apk/res/android}'
        views={v.attrib.get(ns+'id'):v for v in root.iter() if v.attrib.get(ns+'id')}
        for field in ('rd_title','rd_subtitle'):
            self.assertEqual(views['@+id/'+field].attrib.get(ns+'maxLines'),'2')
        self.assertEqual(views['@+id/rd_cover'].attrib.get(ns+'importantForAccessibility'),'no')

    def test_existing_provider_and_theme_boundaries(self):
        navigator=read('helpers/Navigator.kt')
        for name in ('HomeFragment()','VideoBrowserFragment()','AudioBrowserFragment()','PlaylistFragment()'):
            self.assertIn(name,navigator)
        for file in ('res/values/rd_amoled_theme.xml','res/values/rd_ds_tokens.xml'):
            self.assertTrue((APP/file).exists())
        self.assertTrue((ROOT/'ci/workflow_policy.py').exists())
        self.assertTrue((ROOT/'config/delivery-required-ci.json').exists())


if __name__=='__main__': unittest.main()
