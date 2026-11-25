package org.videolan.vlc


import android.annotation.TargetApi
import android.content.Context
import android.media.tv.TvInputManager
import android.media.tv.TvInputManager.VIDEO_UNAVAILABLE_REASON_TUNING
import android.media.tv.TvInputService
import android.net.Uri
import android.os.Build
import android.util.Log
import android.view.Surface
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.MainScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import org.videolan.libvlc.FactoryManager
import org.videolan.libvlc.MediaPlayer
import org.videolan.libvlc.interfaces.IMediaFactory
import org.videolan.resources.AppContextProvider
import org.videolan.resources.VLCInstance
import org.videolan.resources.util.getFromMl
import org.videolan.tools.getContextWithLocale
import org.videolan.vlc.media.MediaPlayerEventListener
import org.videolan.vlc.media.PlayerController
import org.videolan.vlc.util.FontCache
import org.videolan.vlc.util.PlaybackStartFence
import org.videolan.vlc.util.random
import java.io.IOException

private const val TAG = "PreviewInputService"

@TargetApi(Build.VERSION_CODES.LOLLIPOP)
class PreviewVideoInputService : TvInputService(), CoroutineScope by MainScope() {

    internal val factory = FactoryManager.getFactory(IMediaFactory.factoryId) as IMediaFactory

    override fun onCreateSession(inputId: String): Session? {
        return PreviewSession(this)
    }

    override fun attachBaseContext(newBase: Context?) {
        super.attachBaseContext(newBase?.getContextWithLocale(AppContextProvider.locale))
    }

    override fun getApplicationContext(): Context {
        return super.getApplicationContext().getContextWithLocale(AppContextProvider.locale)
    }

    private inner class PreviewSession(context: Context
    ) : Session(context), MediaPlayerEventListener {

        private val playerDelegate = lazy(LazyThreadSafetyMode.NONE) { PlayerController(applicationContext) }
        val player by playerDelegate
        private val tuneFence = PlaybackStartFence()
        private var tuneJob: Job? = null
        @Volatile private var released = false
        private var tunedUri: Uri? = null
        private var needsRetune = false

        override fun onRelease() {
            released = true
            tunedUri = null
            tuneFence.invalidate()
            tuneJob?.cancel()
            surfaceReady?.cancel()
            if (playerDelegate.isInitialized()) player.release()
        }

        override fun onTune(uri: Uri): Boolean {
            if (released) return false
            val id = uri.lastPathSegment?.toLongOrNull() ?: return false
            tunedUri = uri
            needsRetune = false
            val request = tuneFence.begin()
            tuneJob?.cancel()
            notifyVideoUnavailable(VIDEO_UNAVAILABLE_REASON_TUNING)
            tuneJob = launch {
                fun current() = !released && tuneFence.isCurrent(request)
                val mw = getFromMl { getMedia(id) }
                if (!current()) return@launch
                if (mw == null) {
                    Log.w(TAG, "Could not find video $id")
                    notifyVideoUnavailable(TvInputManager.VIDEO_UNAVAILABLE_REASON_UNKNOWN)
                    return@launch
                }
                try {
                    // Bounded shared warmup; canceled previews cannot open a native player later.
                    FontCache.await(this@PreviewVideoInputService)
                    awaitSurface()
                    currentCoroutineContext().ensureActive()
                    if (!current()) return@launch
                    val targetSurface = surface ?: return@launch
                    if (!targetSurface.isValid) return@launch
                    val media = factory.getFromUri(VLCInstance.getInstance(this@PreviewVideoInputService), mw.uri)
                    try {
                        val start = if (mw.length <= 0L) 0L else mw.length.random()
                        media.addOption(":start-time=${start/1000L}")
                        player.getVout()?.apply {
                            setVideoSurface(targetSurface, null)
                            attachViews(null)
                            setWindowSize(width, height)
                        }
                        player.setVideoAspectRatio(null)
                        player.setVideoScale(0f)
                        val started = player.startPlayback(media, this@PreviewSession, start) { current() && surface === targetSurface }
                        if (started && current()) notifyVideoAvailable()
                    } finally { media.release() }
                } catch (e: IOException) {
                    Log.e(TAG, "Could not prepare media player", e)
                    if (current()) notifyVideoUnavailable(TvInputManager.VIDEO_UNAVAILABLE_REASON_UNKNOWN)
                } catch (e: IllegalStateException) {
                    Log.e(TAG, "Could not prepare media player", e)
                    if (current()) notifyVideoUnavailable(TvInputManager.VIDEO_UNAVAILABLE_REASON_UNKNOWN)
                }
            }
            return true
        }

        private var width = 0
        private var height = 0
        @Volatile private var surface: Surface? = null
        private var surfaceReady : CompletableDeferred<Unit>? = null
        override fun onSetSurface(surface: Surface?): Boolean {
            if (released) return false
            val previousSurface = this.surface
            this.surface = surface
            if (surface == null) {
                if (previousSurface != null) {
                    tuneFence.invalidate()
                    tuneJob?.cancel()
                    needsRetune = tunedUri != null
                    if (playerDelegate.isInitialized()) player.stop()
                }
                return true
            }
            if (needsRetune || (previousSurface != null && previousSurface !== surface)) {
                if (playerDelegate.isInitialized()) player.stop()
                tunedUri?.let { onTune(it) }
            } else surfaceReady?.complete(Unit)
            return true
        }

        override fun onSurfaceChanged(format: Int, width: Int, height: Int) {
            this.width = width
            this.height = height
        }

        override fun onSetStreamVolume(volume: Float) {}

        override fun onSetCaptionEnabled(enabled: Boolean) {}

        override suspend fun onEvent(event: MediaPlayer.Event) {
            when(event.type) {
                MediaPlayer.Event.EndReached -> if (!released) player.stop()
            }
        }

        private suspend fun awaitSurface() {
            if (surface == null) {
                val ready = CompletableDeferred<Unit>()
                surfaceReady = ready
                try { ready.await() } finally {
                    if (surfaceReady === ready) surfaceReady = null
                }
            }
        }
    }

    override fun onDestroy() {
        cancel()
        super.onDestroy()
    }
}