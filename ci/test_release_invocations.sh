#!/usr/bin/env bash
# Hosted qualification only. Never use production signing credentials or publish APKs.
set -euo pipefail
[[ "${GITHUB_ACTIONS:-}" == true && "${RUNNER_OS:-}" == Linux ]] || { echo 'Hosted runner required' >&2; exit 1; }
: "${RUNNER_TEMP:?}"
umask 077
fixture="$(mktemp -d "$RUNNER_TEMP/vlc-gradle-policy.XXXXXXXX")"
trap 'rm -rf -- "$fixture"' EXIT
unset RD_RELEASE_KEYSTORE_B64 RD_RELEASE_CERT_SHA256
export RD_KEYSTORE_FILE="$fixture/fixture.jks"
export RD_KEYSTORE_PASSWORD=fixture-only-store RD_KEY_ALIAS=fixture-only RD_KEY_PASSWORD=fixture-only-key
keytool -genkeypair -storetype JKS -keystore "$RD_KEYSTORE_FILE" -storepass "$RD_KEYSTORE_PASSWORD"   -alias "$RD_KEY_ALIAS" -keypass "$RD_KEY_PASSWORD" -keyalg RSA -keysize 2048   -validity 1 -dname 'CN=Disposable CI Fixture' > "$fixture/keytool.log" 2>&1
# Run real Gradle on the configured Android project, using precisely the release CLI.
for identity in standalone original; do
  export RD_RELEASE_IDENTITY="$identity"
  gradle --no-daemon :application:app:dependencies --configuration signedReleaseRuntimeClasspath > "$fixture/$identity.dependencies" 2>&1 || { cat "$fixture/$identity.dependencies"; exit 1; }
  python3 -B -c 'import sys; from pathlib import Path; from ci.release_qualify import parse_dependencies; print("RESOLVED_DEPENDENCIES=" + str(len(parse_dependencies(Path(sys.argv[1]).read_text()))))' "$fixture/$identity.dependencies"
  grep -F 'BUILD SUCCESSFUL' "$fixture/$identity.dependencies"
  gradle --no-daemon :application:app:assembleSignedRelease --dry-run > "$fixture/$identity.assembly" 2>&1 || { cat "$fixture/$identity.assembly"; exit 1; }
  grep -F ':application:app:assembleSignedRelease SKIPPED' "$fixture/$identity.assembly"
  echo "RELEASE_GRADLE_INVOCATION_PASS identity=$identity"
done
reject() {
  local expected="$1" label="$2"; shift 2
  if gradle --no-daemon "$@" > "$fixture/$label.log" 2>&1; then
    echo "Forbidden invocation succeeded: $label" >&2; exit 1
  fi
  grep -F "$expected" "$fixture/$label.log" || { cat "$fixture/$label.log"; exit 1; }
  echo "RELEASE_GRADLE_NEGATIVE_PASS case=$label"
}
export RD_RELEASE_IDENTITY=original
reason='Original VideoLAN package ID permitted only for signedRelease assembly or dependency inspection'
reject "$reason" debug :application:app:assembleDebug --dry-run
reject "$reason" wrong_configuration :application:app:dependencies --configuration debugRuntimeClasspath
reject "$reason" missing_configuration :application:app:dependencies
reject "$reason" extra_task :application:app:dependencies --configuration signedReleaseRuntimeClasspath :application:app:assembleDebug --dry-run
unset RD_KEYSTORE_FILE RD_KEYSTORE_PASSWORD RD_KEY_ALIAS RD_KEY_PASSWORD
for identity in standalone original; do
  export RD_RELEASE_IDENTITY="$identity"
  reject 'signedRelease requires explicit RD_KEYSTORE_FILE' "$identity-no-key" :application:app:dependencies --configuration signedReleaseRuntimeClasspath
  reject 'signedRelease requires explicit RD_KEYSTORE_FILE' "$identity-no-key-assembly" :application:app:assembleSignedRelease --dry-run
done
echo RELEASE_GRADLE_POLICY_PASS
