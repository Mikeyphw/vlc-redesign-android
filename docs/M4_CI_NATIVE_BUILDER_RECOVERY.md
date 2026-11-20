# M4 hosted native CI — Gradle classpath isolation

## Observed CI failure

PR #4 at `1b6133b2aa1ee628c448f33a3cc525a8d8e9c0d2`, hosted run
`44620240512` attempt 1, failed on `arm64-v8a` and `armeabi-v7a`.
Both builds had already produced `libvlcjni.so`, then the inherited
`buildsystem/compile.sh -l` tail invoked `./gradlew` on LibVLC's Android
project. This separate Gradle task tried to resolve published
`org.jetbrains.kotlin:kotlin-stdlib:2.2.10` for
`com.android.settings.gradle.plugin:9.1.1` and returned unavailable.
The two x86-family ABI jobs passed. Maven-AAR and Android APK/JVM jobs
were skipped, **not passed**. Earlier VLC contrib download 404s were
nonterminal because native source compilation continued.

## Scope of correction

CI's selected `-t -l --release` LibVLC compiler now sets
`VLC_NATIVE_CI_ONLY=1`, a new guarded mode in upstream-derived
`buildsystem/compile.sh`. The flag is accepted only after real native
LibVLC C/C++ compilation, output copy and nonempty `libvlcjni.so`
verification. Invalid invocation fails. The mode stops **before**
unrelated Gradle Android library assembly, but the separate *real*
KuchiSofts `compile-medialibrary.sh` remains mandatory.

This is not a workaround that disables a failed required test. The
mandated four-ABI ELF/source/OCI attestations, patched Maven AAR,
JVM tests and Android debug APK remain in the existing DAG unchanged.
Gradle dependency retry retains its own bounded, fail-closed policy
in the downstream Android job. No added Maven mirrors, unpinned binary
caches, privileged actions, source repinning or suppressed diagnostics.

## Verification and acceptance

Run the current `ci/tests/test_*.py` suite, `ci/workflow_policy.py`,
`ci/medialibrary.py source`, and shell syntax checks in native Devtool
validation. Test the compiler gate's invalid-argument/absent-ELF
refusal behavior in current source.

**Only hosted PR-HEAD CI** proves all four MediaLibrary native builds,
patched AAR, actual JVM tests and debug APK. Physical device
PiP/TV/TalkBack and release identity/signature remain separate.
Existing PR #4 must be updated, not replaced by a new PR.
