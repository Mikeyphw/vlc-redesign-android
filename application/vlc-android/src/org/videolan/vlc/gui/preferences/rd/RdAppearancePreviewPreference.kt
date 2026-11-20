/* VLC Redesign M5: read-only live theme/accent/player preview. GPL-2.0-or-later. */
package org.videolan.vlc.gui.preferences.rd

import android.content.Context
import android.content.res.Configuration
import android.graphics.drawable.GradientDrawable
import android.util.AttributeSet
import android.view.View
import android.widget.TextView
import androidx.preference.Preference
import androidx.preference.PreferenceViewHolder
import org.videolan.tools.KEY_APP_THEME
import org.videolan.tools.Settings
import org.videolan.vlc.R
import org.videolan.vlc.gui.helpers.KEY_RD_AMOLED

/** Uses the *applied* Android theme; appearance changes already recreate this settings page. */
class RdAppearancePreviewPreference @JvmOverloads constructor(
    context: Context, attrs: AttributeSet? = null
) : Preference(context, attrs) {
    init {
        layoutResource = R.layout.rd_m5_appearance_preview
        isSelectable = false
    }

    override fun onBindViewHolder(holder: PreferenceViewHolder) {
        super.onBindViewHolder(holder)
        val accent = context.rdAttr(R.attr.colorPrimary)
        val panel = context.rdAttr(R.attr.rd_panel)
        val well = context.rdAttr(R.attr.rd_well)
        val corner = context.rdDp(12f)
        fun shade(id: Int, value: Int, radius: Float) {
            (holder.findViewById(id) as? View)?.background = GradientDrawable().apply {
                setColor(value)
                cornerRadius = radius
            }
        }
        shade(R.id.rd_m5_preview_surface, panel, corner)
        shade(R.id.rd_m5_preview_player, well, context.rdDp(8f))
        shade(R.id.rd_m5_preview_accent, accent, context.rdDp(6f))
        shade(R.id.rd_m5_preview_play, accent, context.rdDp(8f))
        val dark = (context.resources.configuration.uiMode and Configuration.UI_MODE_NIGHT_MASK) == Configuration.UI_MODE_NIGHT_YES
        val preferences = Settings.getInstance(context).all
        val amoled = dark && preferences[KEY_RD_AMOLED] == true
        val label = context.getString(if (dark) R.string.rd_m5_dark else R.string.rd_m5_light)
        val status = context.getString(R.string.rd_m5_live_state, label,
            context.getString(if (amoled) R.string.rd_m5_amoled_on else R.string.rd_m5_amoled_off))
        (holder.findViewById(R.id.rd_m5_preview_status) as? TextView)?.text = status
        holder.itemView.contentDescription = context.getString(R.string.rd_m5_preview_accessibility, status)
        holder.itemView.isClickable = false
    }
}
