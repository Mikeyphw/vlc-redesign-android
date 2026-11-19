/*
 * Opt-in AMOLED treatment for the main phone/tablet theme. It does not change the
 * persisted VLC app_theme values or the player's forced dark / TV themes.
 * GPL-2.0-or-later. VideoLAN and KuchiSofts attribution retained in upstream sources.
 */
package org.videolan.vlc.gui.helpers

import android.app.Activity
import android.content.res.Configuration
import android.graphics.Color
import android.graphics.drawable.ColorDrawable
import androidx.core.view.WindowCompat
import org.videolan.tools.Settings
import org.videolan.vlc.R

const val KEY_RD_AMOLED = "rd_amoled"

/**
 * Applied before accent overlays, so existing user/system accent preferences win.
 * "1" is forced light, "2" forced dark, other legacy modes follow active configuration.
 * This affects theme-aware panels and the window, not raw @color references in layouts.
 */
fun applyRdAmoledTheme(activity: Activity, chosenMode: String?) {
    if (Settings.showTvUi) return
    if (!Settings.getInstance(activity).getBoolean(KEY_RD_AMOLED, false)) return
    val dark = when (chosenMode) {
        "1" -> false
        "2" -> true
        else -> (activity.resources.configuration.uiMode and Configuration.UI_MODE_NIGHT_MASK) == Configuration.UI_MODE_NIGHT_YES
    }
    if (!dark) return
    activity.theme.applyStyle(R.style.ThemeOverlay_Redesign_Amoled, true)
    activity.window.setBackgroundDrawable(ColorDrawable(Color.BLACK))
    val insets = WindowCompat.getInsetsController(activity.window, activity.window.decorView)
    insets.isAppearanceLightStatusBars = false
    insets.isAppearanceLightNavigationBars = false
}
