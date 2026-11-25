/*
 * *************************************************************************
 *  FontCache.kt
 * **************************************************************************
 *  Copyright © 2026 VLC authors and VideoLAN
 *
 *  This program is free software; you can redistribute it and/or modify
 *  it under the terms of the GNU General Public License as published by
 *  the Free Software Foundation; either version 2 of the License, or
 *  (at your option) any later version.
 *
 *  This program is distributed in the hope that it will be useful,
 *  but WITHOUT ANY WARRANTY; without even the implied warranty of
 *  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 *  GNU General Public License for more details.
 *
 *  You should have received a copy of the GNU General Public License
 *  along with this program; if not, write to the Free Software
 *  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston MA 02110-1301, USA.
 *  ***************************************************************************
 */

package org.videolan.vlc.util

import android.content.Context
import android.os.Build
import android.os.SystemClock
import android.util.Log
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import org.videolan.vlc.BuildConfig
import org.videolan.libvlc.LibVLC
import org.videolan.resources.VLCInstance
import org.videolan.tools.AppScope
import org.videolan.tools.KEY_FONT_CACHE_FAILURES
import org.videolan.tools.KEY_FONT_CACHE_FINGERPRINT
import org.videolan.tools.Settings
import org.videolan.vlc.buildFontCacheIfSupported
import java.io.File
import java.util.concurrent.atomic.AtomicLong

private const val TAG = "VLC/FontCache"
private const val WAIT_NOTIFICATION_INTERVAL = 3500L

/** Best-effort fontconfig warmup; native playback remains the fallback. */
object FontCache {
    private val gate = FontCacheGate(AppScope, Dispatchers.IO)
    private val lastWaitNotification = AtomicLong(-WAIT_NOTIFICATION_INTERVAL)

    private fun start(context: Context) = context.applicationContext.let { appContext ->
        gate.prepare { build(appContext) }
    }

    fun prepare(context: Context) { start(context) }

    /** The application-side wait is bounded. Never swallow the requesting coroutine's cancellation. */
    suspend fun await(context: Context, onWait: (() -> Unit)? = null) {
        if (BuildConfig.VLC_MAJOR_VERSION != 3) return
        val result = gate.await(start(context)) {
            if (onWait != null && shouldNotifyWait()) onWait()
        }
        if (result == FontCacheResult.TIMED_OUT)
            Log.w(TAG, "Font cache warmup still running; continuing playback startup")
    }

    private fun shouldNotifyWait(): Boolean {
        val now = SystemClock.elapsedRealtime()
        val last = lastWaitNotification.get()
        return now - last >= WAIT_NOTIFICATION_INTERVAL && lastWaitNotification.compareAndSet(last, now)
    }

    private fun build(context: Context): FontCacheResult {
        if (BuildConfig.VLC_MAJOR_VERSION != 3) return FontCacheResult.SKIPPED
        try {
            // All settings, package and font-directory reads occur on the IO dispatcher.
            val settings = Settings.getInstance(context)
            val fingerprint = fingerprint(context)
            val attempt = FontCacheAttempts.next(settings.getString(KEY_FONT_CACHE_FINGERPRINT, null),
                fingerprint, settings.getInt(KEY_FONT_CACHE_FAILURES, 0)) ?: return FontCacheResult.SKIPPED
            // Journal the attempt atomically before entering JNI: process death or a hung scan counts.
            if (!settings.edit().putString(KEY_FONT_CACHE_FINGERPRINT, fingerprint)
                    .putInt(KEY_FONT_CACHE_FAILURES, attempt).commit()) {
                Log.w(TAG, "Font cache attempt could not be persisted; skipping warmup")
                return FontCacheResult.FAILED
            }
            val start = SystemClock.elapsedRealtime()
            val lib = VLCInstance.getInstance(context) as LibVLC
            // A simultaneous effects restart may release the singleton's owner reference.
            // Retain this native object for the complete background scan, including after wait timeout.
            if (!lib.retain()) return FontCacheResult.FAILED
            val cached = try { lib.buildFontCacheIfSupported() } finally { lib.release() }
            if (cached && !settings.edit().putString(KEY_FONT_CACHE_FINGERPRINT, fingerprint)
                    .putInt(KEY_FONT_CACHE_FAILURES, 0).commit()) {
                Log.w(TAG, "Font cache success could not be persisted")
                return FontCacheResult.FAILED
            }
            Log.i(TAG, "Font cache scan took ${SystemClock.elapsedRealtime() - start}ms; valid on disk: $cached")
            if (!cached && attempt >= FontCacheAttempts.MAX_FAILURES)
                Log.w(TAG, "Font cache retry budget exhausted for current fingerprint")
            return if (cached) FontCacheResult.READY else FontCacheResult.FAILED
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            Log.w(TAG, "Font cache warmup failed; playback fallback remains available", e)
        } catch (e: LinkageError) {
            Log.w(TAG, "Font cache warmup not available in native library", e)
        }
        return FontCacheResult.FAILED
    }

    @Suppress("DEPRECATION")
    private fun fingerprint(context: Context): String {
        val update = context.packageManager.getPackageInfo(context.packageName, 0).lastUpdateTime
        val fonts = listOf("/system/fonts", "/product/fonts", "/system_ext/fonts", "/vendor/fonts", "/data/fonts")
            .joinToString("|") { "$it:${File(it).lastModified()}" }
        // Version this policy independently of the APK version. Changes reset a legacy exhausted budget.
        return "m11-v1|${Build.FINGERPRINT}|${Build.SUPPORTED_ABIS.joinToString(",")}|$update|$fonts"
    }
}
