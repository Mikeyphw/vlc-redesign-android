package org.videolan.vlc.util

import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.Deferred
import kotlinx.coroutines.async
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withTimeoutOrNull
import java.util.concurrent.atomic.AtomicBoolean

enum class FontCacheResult { READY, FAILED, SKIPPED, TIMED_OUT }

/** One application-owned job per process. A caller timing out or being canceled never cancels it. */
class FontCacheGate(
    private val scope: CoroutineScope,
    private val dispatcher: CoroutineDispatcher,
    private val waitMillis: Long = 2000L,
    private val notificationDelayMillis: Long = 250L
) {
    init { require(waitMillis > 0 && notificationDelayMillis in 1..waitMillis) }
    private var job: Deferred<FontCacheResult>? = null
    private val waitBudgetExhausted = AtomicBoolean()

    @Synchronized
    fun prepare(build: suspend () -> FontCacheResult): Deferred<FontCacheResult> {
        job?.let { return it }
        return scope.async(dispatcher, CoroutineStart.LAZY) { build() }
            .also { job = it; it.start() }
    }

    suspend fun await(pending: Deferred<FontCacheResult>, onWait: (() -> Unit)?): FontCacheResult {
        // The outer deadline includes the notification grace period. Do not catch caller cancellation.
        currentCoroutineContext().ensureActive()
        if (pending.isCompleted) return pending.await()
        if (waitBudgetExhausted.get()) return FontCacheResult.SKIPPED
        val result = withTimeoutOrNull(waitMillis) {
            val quick = withTimeoutOrNull(notificationDelayMillis) { pending.await() }
            if (quick != null) quick else {
                if (!pending.isCompleted) onWait?.invoke()
                pending.await()
            }
        }
        if (result != null) return result
        return if (waitBudgetExhausted.compareAndSet(false, true)) FontCacheResult.TIMED_OUT
        else FontCacheResult.SKIPPED
    }
}

/** A failed/interrupted scan consumes one attempt; only an affirmative native result clears it. */
object FontCacheAttempts {
    const val MAX_FAILURES = 3
    fun next(previousFingerprint: String?, fingerprint: String, previousFailures: Int): Int? {
        if (previousFingerprint != fingerprint) return 1
        // A prior successful scan is not proof the OS still has the disk cache.
        // Revalidate once per process, but do not retry a repeatedly failing fingerprint.
        if (previousFailures >= MAX_FAILURES) return null
        return previousFailures.coerceAtLeast(0) + 1
    }
}
