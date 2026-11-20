/*
 * M6: optional reduced motion, respecting the system animator scale.
 * GPL-2.0-or-later; preserves VideoLAN and KuchiSofts preference contracts.
 */
package org.videolan.vlc.gui.preferences.rd

import android.animation.ValueAnimator
import android.content.Context
import android.os.Build
import android.widget.ScrollView
import org.videolan.tools.Settings

/** A user override and Android's own reduced-animation preference are independent. */
object RdMotionPolicy {
    const val KEY = "rd_reduce_motion"

    fun shouldAnimate(context: Context): Boolean {
        if (Settings.getInstance(context).getBoolean(KEY, false)) return false
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) return ValueAnimator.areAnimatorsEnabled()
        return runCatching {
            android.provider.Settings.Global.getFloat(
                context.contentResolver,
                android.provider.Settings.Global.ANIMATOR_DURATION_SCALE, 1f) > 0f
        }.getOrDefault(true)
    }

    fun scrollTo(scroll: ScrollView, x: Int, y: Int) {
        if (shouldAnimate(scroll.context)) scroll.smoothScrollTo(x, y)
        else scroll.scrollTo(x, y)
    }
}
