package org.videolan.vlc.util

import java.util.concurrent.atomic.AtomicLong

/** Invalidate only suspended starts; no cancellation of the shared application font scan. */
class PlaybackStartFence {
    private val generation = AtomicLong()
    fun begin(): Long = generation.incrementAndGet()
    fun invalidate() { generation.incrementAndGet() }
    fun isCurrent(request: Long): Boolean = generation.get() == request
}
