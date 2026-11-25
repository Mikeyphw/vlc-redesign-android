package org.videolan.mobile.app

import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.async
import kotlinx.coroutines.cancel
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.videolan.vlc.util.FontCacheAttempts
import org.videolan.vlc.util.FontCacheGate
import org.videolan.vlc.util.FontCacheResult
import org.videolan.vlc.util.PlaybackStartFence
import java.util.concurrent.atomic.AtomicInteger

/** Runs unchanged in the app JVM suite and in a standalone Kotlin/JVM fixture. */
object M11PlaybackRegression {
    fun singleFlightAndBudget() = runBlocking {
        val app = CoroutineScope(SupervisorJob() + Dispatchers.Default)
        try {
            val gate = FontCacheGate(app, Dispatchers.Default, 300, 20)
            val release = CompletableDeferred<Unit>()
            val entered = CompletableDeferred<Unit>()
            val scans = AtomicInteger()
            val pending = gate.prepare {
                scans.incrementAndGet()
                entered.complete(Unit)
                release.await()
                FontCacheResult.READY
            }
            withTimeout(5000) { entered.await() }
            check(gate.prepare { error("duplicate scan") } === pending)
            var notices = 0
            check(withTimeout(5000) { gate.await(pending) { notices++ } } == FontCacheResult.TIMED_OUT)
            check(notices == 1 && scans.get() == 1 && !pending.isCancelled && !pending.isCompleted)
            check(gate.await(pending) { error("repeated wait notice") } == FontCacheResult.SKIPPED)
            release.complete(Unit)
            check(withTimeout(5000) { pending.await() } == FontCacheResult.READY)
            check(gate.await(pending) { error("ready cache notified") } == FontCacheResult.READY)
        } finally { app.cancel() }
    }

    fun cancelCallerNotSharedScan() = runBlocking {
        val app = CoroutineScope(SupervisorJob() + Dispatchers.Default)
        try {
            val gate = FontCacheGate(app, Dispatchers.Default, 5000, 10)
            val release = CompletableDeferred<Unit>()
            val pending = gate.prepare { release.await(); FontCacheResult.READY }
            val waiting = CompletableDeferred<Unit>()
            val caller = async { gate.await(pending) { waiting.complete(Unit) } }
            withTimeout(2000) { waiting.await() }
            caller.cancelAndJoin()
            check(caller.isCancelled && !pending.isCancelled && !pending.isCompleted)
            release.complete(Unit)
            check(withTimeout(2000) { pending.await() } == FontCacheResult.READY)
        } finally { app.cancel() }
    }

    fun failureAndReadyAreNotTimeouts() = runBlocking {
        val app = CoroutineScope(SupervisorJob() + Dispatchers.Default)
        try {
            val gate = FontCacheGate(app, Dispatchers.Default, 300, 20)
            val pending = gate.prepare { FontCacheResult.FAILED }
            withTimeout(2000) { pending.await() }
            check(gate.await(pending) { error("failed job notified") } == FontCacheResult.FAILED)
            check(gate.prepare { error("same-process retry") } === pending)
        } finally { app.cancel() }
    }

    fun retryAccounting() {
        check(FontCacheAttempts.next(null, "new", 0) == 1)
        check(FontCacheAttempts.next("old", "new", 3) == 1)
        check(FontCacheAttempts.next("new", "new", 0) == 1) // revalidate evicted cache
        check(FontCacheAttempts.next("new", "new", 1) == 2)
        check(FontCacheAttempts.next("new", "new", 2) == 3)
        check(FontCacheAttempts.next("new", "new", 3) == null)
        check(FontCacheAttempts.next("new", "new", Int.MAX_VALUE) == null)
    }

    fun staleRequestsCannotResume() = runBlocking {
        val fence = PlaybackStartFence()
        val first = fence.begin()
        val resume = CompletableDeferred<Unit>()
        val old = async { resume.await(); fence.isCurrent(first) }
        val second = fence.begin()
        resume.complete(Unit)
        check(!old.await() && fence.isCurrent(second))
        fence.invalidate() // stop/release/replacement
        check(!fence.isCurrent(second))
        val third = fence.begin()
        check(fence.isCurrent(third) && !fence.isCurrent(first))
    }

    @JvmStatic fun main(args: Array<String>) {
        singleFlightAndBudget(); println("M11_SINGLE_FLIGHT_BUDGET_PASS")
        cancelCallerNotSharedScan(); println("M11_CANCELLATION_PASS")
        failureAndReadyAreNotTimeouts(); println("M11_FAILED_SCAN_PASS")
        retryAccounting(); println("M11_RETRY_POLICY_PASS")
        staleRequestsCannotResume(); println("M11_STALE_START_PASS")
    }
}
