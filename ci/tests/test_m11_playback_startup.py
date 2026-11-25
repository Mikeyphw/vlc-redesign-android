"""M11 production wiring guards; actual coroutine tests execute in the app JVM suite."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
VLC = ROOT / 'application/vlc-android/src/org/videolan/vlc'

class M11Wiring(unittest.TestCase):
    def text(self, p):
        return (VLC/p).read_text(encoding='utf-8')

    def test_scan_runs_in_app_io_and_journals_before_jni(self):
        s=self.text('util/FontCache.kt')
        self.assertIn('FontCacheGate(AppScope, Dispatchers.IO)',s)
        self.assertIn('context.applicationContext',s)
        self.assertLess(s.index('.putInt(KEY_FONT_CACHE_FAILURES, attempt).commit()'),s.index('lib.buildFontCacheIfSupported()'))
        self.assertIn('if (!lib.retain())',s)
        self.assertIn('finally { lib.release() }',s)
        self.assertIn('catch (e: CancellationException) {\n            throw e',s)
        self.assertIn('BuildConfig.VLC_MAJOR_VERSION != 3',s)
        self.assertIn('lastUpdateTime',s)

    def test_wait_is_bounded_and_not_repeated(self):
        s=self.text('util/FontCacheGate.kt')
        self.assertIn('withTimeoutOrNull(waitMillis)',s)
        self.assertIn('waitBudgetExhausted.compareAndSet(false, true)',s)
        self.assertIn('if (waitBudgetExhausted.get()) return FontCacheResult.SKIPPED',s)
        self.assertNotIn('pending.cancel(',s)

    def test_playlist_guards_real_start_and_invalidation(self):
        s=self.text('media/PlaylistManager.kt')
        play=s.split('suspend fun playIndex(',1)[1].split('private suspend fun applySubtitleCharset',1)[0]
        self.assertLess(play.index('val mw = mediaList.getMedia(targetIndex)'),play.index('FontCache.await'))
        self.assertIn('mw.type != MediaWrapper.TYPE_AUDIO',play)
        self.assertIn('mediaList.getMedia(targetIndex) === mw',play)
        self.assertIn('if (!player.startPlayback(media, mediaplayerEventListener, start, ::stillCurrent)) return',play)
        self.assertIn('if (!handedOff) media.release()',play)
        for marker in ('suspend fun load(list:', 'fun stop(systemExit:', 'fun onServiceDestroyed()', 'suspend fun restartForEffects('):
            self.assertIn('playbackStart.invalidate()',s.split(marker,1)[1][:260])

    def test_player_and_preview_bind_native_media_and_surface(self):
        s=self.text('media/PlayerController.kt')
        self.assertIn('startMutex.withLock',s)
        self.assertIn('mediaplayer === target',s)
        self.assertIn('if (!current()) return@withLock false',s)
        self.assertIn('target.play()',s)
        p=self.text('PreviewVideoInputService.kt')
        self.assertIn('tuneJob?.cancel()',p)
        self.assertIn('tuneFence.invalidate()',p)
        self.assertLess(p.index('awaitSurface()'),p.index('factory.getFromUri'))
        self.assertIn('finally { media.release() }',p)
        self.assertIn('surface === targetSurface',p)
        self.assertIn('tunedUri?.let { onTune(it) }',p)

    def test_tests_are_in_actual_app_jvm_path(self):
        p=ROOT/'application/app/src/test/java/org/videolan/mobile/app/M11PlaybackRegressionTest.kt'
        self.assertEqual(p.read_text().count('@Test'),5)
        self.assertIn(':application:app:testDebugUnitTest',(ROOT/'ci/gradle_dependency_retry.sh').read_text())

if __name__ == '__main__': unittest.main()
