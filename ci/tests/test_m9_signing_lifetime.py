"""M9-F02: execute the real release step with synthetic signing and Gradle doubles."""
from __future__ import annotations

import base64
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'ci'))
import release_qualify as q

SIGNING = '      - name: Build four independently signed APK splits for selected package identity'
PUBLIC = '      - name: Check signed APKs'
INVENTORY = '          gradle --no-daemon :application:app:dependencies'

# Shell functions shadow the executables: no Gradle, APK assembly, production
# key, external service, or network is used in these source regression tests.
DOUBLES = r'''
record() { printf '%s\n' "$1" >> "$RUNNER_TEMP/events"; }
credentials_live() {
    test -n "$RD_KEYSTORE_PASSWORD" && test -n "$RD_KEY_ALIAS" &&
    test -n "$RD_KEY_PASSWORD" && test -n "$RD_MAVEN" &&
    test -s "$RD_KEYSTORE_FILE" && test "$(stat -c %a "$RD_KEYSTORE_FILE")" = 600
}
python3() {
    case "$2:$3" in
        ci/release_qualify.py:signing-env)
            record signing-env
            test "$FAIL_AT" != signing-env ;;
        ci/update_manifest.py:sign)
            credentials_live || return 91
            record sign
            test "$FAIL_AT" != sign ;;
        *) return 92 ;;
    esac
}
gradle() {
    credentials_live || return 93
    test "$1" = --no-daemon || return 94
    case "$2" in
        :application:app:assembleSignedRelease)
            record assemble
            test "$FAIL_AT" != assemble ;;
        :application:app:dependencies)
            test "$3:$4" = --configuration:signedReleaseRuntimeClasspath || return 95
            record inventory
            test "$FAIL_AT" != inventory || return 96
            if test "$FAIL_AT" != empty; then printf 'signedReleaseRuntimeClasspath\nfixture:dependency:1.0\n'; fi ;;
        *) return 97 ;;
    esac
}
'''


class SigningLifetimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = (ROOT / '.github/workflows/vlc-release.yml').read_text('utf-8')
        step = cls.workflow.split(SIGNING, 1)[1].split(PUBLIC, 1)[0]
        cls.body = textwrap.dedent(step.split('        run: |\n', 1)[1])

    def test_guard_rejects_original_failure_and_boundary_mutations(self):
        q.require_release_workflow_contract(self.workflow)
        inventory_step = ('      - name: Generate resolved runtime dependency inventory\n'
                          '        shell: bash\n        env:\n'
                          '          RD_MAVEN: ${{ github.workspace }}/ci/_maven/repository\n'
                          '        run: |\n')
        mutations = (
            self.workflow.replace(INVENTORY, inventory_step + INVENTORY, 1),
            self.workflow.replace('--notes docs/RELEASE_NOTES.md || exit 1', '--notes docs/RELEASE_NOTES.md', 1),
            self.workflow.replace('trap \'rm -f -- "$RD_KEYSTORE_FILE"\' EXIT', 'trap \'true\' EXIT', 1),
            self.workflow.replace('          RD_KEY_PASSWORD: ${{ secrets.RD_KEY_PASSWORD }}\n', '', 1),
            self.workflow.replace(INVENTORY, '          printf "secret" >> "$GITHUB_ENV"\n' + INVENTORY, 1),
            self.workflow.replace('--dependencies "$RUNNER_TEMP/vlc-m7-dependencies.txt"', '--dependencies /tmp/other.txt', 1),
        )
        for i, mutated in enumerate(mutations):
            with self.subTest(mutation=i), self.assertRaises(q.ReleaseRefused):
                q.require_release_workflow_contract(mutated)

    def exercise(self, identity, failure, expected):
        with TemporaryDirectory(prefix='vlc-signing-fixture-') as tmp:
            root = Path(tmp)
            env = dict(os.environ, RUNNER_TEMP=str(root), RD_RELEASE_IDENTITY=identity,
                       RD_RELEASE_KEYSTORE_B64=base64.b64encode(b'synthetic-fixture-only' * 100).decode(),
                       RD_KEYSTORE_PASSWORD='fixture-store', RD_KEY_ALIAS='fixture',
                       RD_KEY_PASSWORD='fixture-key', RD_RELEASE_CERT_SHA256='a' * 64,
                       RD_MAVEN=str(root / 'maven'), RD_UPDATE_CHANNEL='stable',
                       GITHUB_SHA='b' * 40, FAIL_AT=failure)
            result = subprocess.run(['bash', '--noprofile', '--norc', '-eo', 'pipefail', '-c', DOUBLES + '\n' + self.body],
                                    env=env, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode == 0, not failure, result.stderr)
            self.assertEqual((root / 'events').read_text().splitlines(), expected)
            self.assertFalse((root / 'vlc-m7-keystore/release.jks').exists(), 'temporary private key was retained')
            inventory = root / 'vlc-m7-dependencies.txt'
            if not failure:
                self.assertIn('signedReleaseRuntimeClasspath', inventory.read_text())
                self.assertGreater(inventory.stat().st_size, 0)
            self.assertNotIn('fixture-store', result.stdout + result.stderr)
            self.assertNotIn('fixture-key', result.stdout + result.stderr)

    def test_both_editions_inventory_and_cleanup_on_success(self):
        for identity in q.RELEASE_IDENTITIES:
            with self.subTest(identity=identity):
                self.exercise(identity, '', ['signing-env', 'assemble', 'sign', 'inventory'])

    def test_both_editions_stop_and_cleanup_on_failure(self):
        cases = {'signing-env': ['signing-env'], 'assemble': ['signing-env', 'assemble'],
                 'sign': ['signing-env', 'assemble', 'sign'],
                 'inventory': ['signing-env', 'assemble', 'sign', 'inventory'],
                 'empty': ['signing-env', 'assemble', 'sign', 'inventory']}
        for identity in q.RELEASE_IDENTITIES:
            for failure, expected in cases.items():
                with self.subTest(identity=identity, failure=failure):
                    self.exercise(identity, failure, expected)
