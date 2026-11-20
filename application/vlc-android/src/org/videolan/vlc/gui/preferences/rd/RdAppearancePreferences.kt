/*
 * VLC Redesign M5: scoped, migration-safe visual preference defaults.
 * GPL-2.0-or-later. Original VideoLAN/KuchiSofts source attribution retained.
 */
package org.videolan.vlc.gui.preferences.rd

import android.content.SharedPreferences
import org.videolan.tools.KEY_APP_THEME
import org.videolan.vlc.gui.helpers.KEY_RD_AMOLED
import org.videolan.vlc.gui.helpers.KEY_RD_ACCENT_SYSTEM

/** No new theme engine or duplicate preference keys: reuse the existing contracts. */
internal object RdAppearancePreferences {
    const val ACCENT_KEY = "rd_accent"
    val VISUAL_KEYS: Set<String> = setOf(KEY_APP_THEME, ACCENT_KEY, KEY_RD_ACCENT_SYSTEM, KEY_RD_AMOLED)
    private val booleanKeys = setOf(KEY_RD_ACCENT_SYSTEM, KEY_RD_AMOLED)
    // Retain older AppCompat auto-night values for backwards-compatible upgrades.
    private val acceptedThemeModes = setOf("-1", "0", "1", "2", "3")

    /** Repair only malformed visual entries. Missing keys keep upstream XML defaults. */
    fun migrate(prefs: SharedPreferences, allowedAccents: Set<String>): Boolean {
        val values = prefs.all
        val invalid = mutableSetOf<String>()
        val savedTheme = values[KEY_APP_THEME] as? String
        val savedAccent = values[ACCENT_KEY] as? String
        if (values.containsKey(KEY_APP_THEME) && (savedTheme == null || savedTheme !in acceptedThemeModes)) {
            invalid.add(KEY_APP_THEME)
        }
        if (values.containsKey(ACCENT_KEY) && (savedAccent == null || savedAccent !in allowedAccents)) {
            invalid.add(ACCENT_KEY)
        }
        for (key in booleanKeys) {
            if (values.containsKey(key) && values[key] !is Boolean) invalid.add(key)
        }
        if (invalid.isEmpty()) return false
        val editor = prefs.edit()
        invalid.forEach { editor.remove(it) }
        editor.apply()
        return true
    }

    /** Scoped reset: removes only appearance overrides; never clears media/app settings. */
    fun reset(prefs: SharedPreferences) {
        val editor = prefs.edit()
        VISUAL_KEYS.forEach { editor.remove(it) }
        editor.apply()
    }
}
