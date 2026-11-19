#!/usr/bin/env bash
# Bounded retry ONLY for remote Maven classpath artifacts that Gradle reported
# missing in its plugin/settings resolution stage. Never retries JVM tests,
# compilation, signing, other build failures, or a damaged local artifact.
set -euo pipefail
umask 077
if [[ $# -ne 1 ]]; then
    echo 'VLC_GRADLE_RETRY_USAGE: expected test or assemble' >&2
    exit 2
fi
case "$1" in
    test) task=':application:app:testDebugUnitTest' ;;
    assemble) task=':application:app:assembleDebug' ;;
    *) echo 'VLC_GRADLE_RETRY_INVALID_TASK' >&2; exit 2 ;;
esac
command -v gradle >/dev/null || { echo 'VLC_GRADLE_REQUIRED_BINARY_MISSING' >&2; exit 3; }
log="$(mktemp "${TMPDIR:-/tmp}/vlc-gradle-classpath.XXXXXXXX")"
trap 'rm -f -- "$log"' EXIT
for attempt in 1 2 3; do
    echo "VLC_GRADLE_NATIVE_ATTEMPT ${attempt}/3 task=${task}" >&2
    flags=(--no-daemon --stacktrace)
    # The prior failure can be cached by Gradle. A retry must force a fresh
    # metadata and artifact lookup, not reuse cached remote-absence results.
    if (( attempt > 1 )); then flags+=(--refresh-dependencies); fi
    if gradle "${flags[@]}" "$task" 2>&1 | tee "$log"; then
        echo "VLC_GRADLE_NATIVE_PASS attempt=${attempt} task=${task}" >&2
        exit 0
    else
        status=$?
    fi
    # A retry is permitted only when configuration failed resolving a
    # specific published artifact from the official Maven Central endpoint.
    # Test/compile failures are final, even when their logs contain
    # incidental dependency diagnostics.
    if ! grep -Fq "Could not resolve all artifacts for configuration 'classpath'." "$log" \
       || ! grep -Fq 'Could not find ' "$log" \
       || ! grep -Fq 'Searched in the following locations:' "$log" \
       || ! grep -Fq 'https://repo.maven.apache.org/maven2/' "$log" \
       || grep -Eq '^> Task ' "$log"; then
        echo "VLC_GRADLE_NON_CLASSPATH_FAILURE rc=${status}; not retrying" >&2
        exit "$status"
    fi
    if [[ "$attempt" -ge 3 ]]; then
        echo 'VLC_GRADLE_REMOTE_CLASSPATH_UNAVAILABLE: 3 attempts; all required gates remain failed' >&2
        exit "$status"
    fi
    echo "VLC_GRADLE_REMOTE_CLASSPATH_RETRY next=$((attempt+1))/3; --refresh-dependencies" >&2
    sleep "$((attempt * 2))"
done
exit 1
