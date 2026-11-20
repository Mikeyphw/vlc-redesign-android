# M4 — Official Maven Central HTTP 429 recovery

## Observed hosted failure

At PR #4 HEAD `3785aba19d3b6a5d8aea8aa341296ac5b60e086e`, run
`44676000555` attempt 1, all four source-bound native ABI jobs passed.
The mandatory Maven packaging job independently verified all four native
receipts, then failed because the official Maven Central AAR request returned
`HTTP 429 Too Many Requests`. JVM unit tests and APK assembly were skipped,
not passed.

## Corrective scope

Only the official `ci/medialibrary.py` fetch path gets five total attempts and
four bounded waits. `Retry-After` is honored only as numeric delta-seconds,
clamped to 90 seconds per attempt. There is no alternative Maven origin,
non-official mirror, skipped download, unvalidated cache, or unchecked binary.
Non-429 HTTP errors are never retried. After the maximum, 429 remains fatal.

The existing AAR and POM structural validation, optional strong checksum
sidecar semantics (404 only for sidecars), content digest receipts, four
ABI ELF/source/OCI gates, downstream JVM unit tests, debug APK build and CI
policy all remain mandatory and unchanged. Source/CI regression tests include
negative cases for status 403/404/500/503, malicious URLs, redirects, oversized
or empty payloads, and perpetual 429.

## Acceptance

Local source-oriented unit tests and native Devtool preflight are different
from hosted Android/Gradle and physical-device evidence. Do not mark M4
complete until the exact updated PR HEAD has successful required workflow
results, native Devtool session/CI receipts, and separately recorded device
TalkBack, PiP, orientation and Android TV smoke checks.
