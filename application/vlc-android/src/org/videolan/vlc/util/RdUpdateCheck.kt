/* SPDX-License-Identifier: GPL-2.0-or-later */
package org.videolan.vlc.util

import org.videolan.vlc.rd.updater.*

import android.content.Context
import org.json.JSONArray
import org.videolan.tools.Settings
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.util.concurrent.TimeUnit

object RdUpdateCheck {
    const val KEY_CHECK = "rd_check_updates" // retain the user's existing privacy setting
    const val KEY_CHANNEL = "rd_fork_update_channel_v1"
    const val KEY_WIFI = "rd_fork_update_wifi_v1"
    private const val LAST = "rd_fork_update_last_v1"
    private const val NOTIFIED = "rd_fork_update_notified_v1"
    private val mutex = Mutex()
    private const val FEED = "https://api.github.com/repos/${UpdateTrust.REPOSITORY}/releases?per_page=20"
    fun channel(c: Context): String = Settings.getInstance(c).getString(KEY_CHANNEL,"stable")?.takeIf { it == "beta" } ?: "stable"
    fun wifiOnly(c: Context) = Settings.getInstance(c).getBoolean(KEY_WIFI,true)
    fun enabled(c: Context) = UpdateTrust.edition(c.packageName) != null && Settings.getInstance(c).getBoolean(KEY_CHECK,true)
    internal fun setNotified(c: Context, m: UpdateManifest) = Settings.getInstance(c).edit().putString(NOTIFIED,"${m.channel}:${m.asset.code}").apply()
    internal fun alreadyNotified(c: Context, m: UpdateManifest) = Settings.getInstance(c).getString(NOTIFIED,"") == "${m.channel}:${m.asset.code}"
    internal suspend fun check(c: Context, automatic: Boolean): UpdateManifest? = mutex.withLock {
        withContext(Dispatchers.IO) {
            val prefs=Settings.getInstance(c); val now=System.currentTimeMillis(); val selectedChannel=channel(c)
            if(automatic && (!enabled(c) || now-prefs.getLong("$LAST:$selectedChannel",0L) in 0 until TimeUnit.DAYS.toMillis(1))) return@withContext null
            val installed=InstalledIdentity.current(c)
            val json=JSONArray(UpdateHttp.read(FEED, 8*1024*1024).toString(Charsets.UTF_8))
            val candidates=mutableListOf<Pair<Long,String>>()
            for(i in 0 until json.length()) {
                val r=json.optJSONObject(i)?:continue
                if(r.optBoolean("draft",true)||r.isNull("published_at")||r.optString("published_at").isBlank()) continue
                val beta=r.optBoolean("prerelease",false)
                if(beta && selectedChannel!="beta") continue
                val ch=if(beta) "beta" else "stable"
                val tag=r.optString("tag_name");val version=tag.removePrefix("v").removeSuffix("-beta")
                val code=try{if(UpdateTrust.tag(version,ch)!=tag) continue;UpdateTrust.expectedCode(version,installed.abi)}catch(e:IllegalArgumentException){continue}
                if(code<=installed.code)continue
                val assets=r.optJSONArray("assets")?:continue
                val counts=mutableMapOf<String,Int>()
                for(j in 0 until assets.length()){val name=assets.optJSONObject(j)?.optString("name")?:continue;counts[name]=(counts[name]?:0)+1}
                val prefix="update-${installed.edition}"
                val needed=listOf("$prefix.json","$prefix.sig",UpdateTrust.assetName(installed.edition,version,installed.abi))
                // A release without an update manifest is not an eligible in-app release.
                if(needed.all{counts[it]==1}) candidates.add(code to tag)
            }
            val top=candidates.maxWithOrNull(compareBy<Pair<Long,String>> { it.first }.thenBy { if(it.second.endsWith("-beta")) 0 else 1 })
            if(top==null){prefs.edit().putLong("$LAST:$selectedChannel",now).apply();return@withContext null}
            // Refuse ambiguous versions and any invalid newest eligible manifest. Never silently downgrade.
            require(candidates.count{it.first==top.first && it.second==top.second}==1){"Ambiguous release version"}
            val prefix="update-${installed.edition}"
            val payload=UpdateHttp.read(UpdateTrust.assetUrl(top.second,"$prefix.json"),UpdateTrust.MAX_MANIFEST)
            val signature=UpdateHttp.read(UpdateTrust.assetUrl(top.second,"$prefix.sig"),16384)
            val m=UpdateManifest.parse(payload,signature,installed)
            require(m.tag==top.second && m.asset.code==top.first && m.asset.code>installed.code)
            require(m.channel=="stable" || selectedChannel=="beta")
            prefs.edit().putLong("$LAST:$selectedChannel",now).apply()
            m
        }
    }
}
