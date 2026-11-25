package org.videolan.mobile.app

import org.junit.Test

class M11PlaybackRegressionTest {
    @Test fun boundedSharedWarmup() = M11PlaybackRegression.singleFlightAndBudget()
    @Test fun cancellationIsolation() = M11PlaybackRegression.cancelCallerNotSharedScan()
    @Test fun completedFailure() = M11PlaybackRegression.failureAndReadyAreNotTimeouts()
    @Test fun persistentRetryPolicy() = M11PlaybackRegression.retryAccounting()
    @Test fun staleRequests() = M11PlaybackRegression.staleRequestsCannotResume()
}
