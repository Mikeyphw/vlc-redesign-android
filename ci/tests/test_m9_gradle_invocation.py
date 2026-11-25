"""Source-level checks for the hosted real Gradle invocation gate (no local Gradle)."""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]

class GradleInvocationContractTests(unittest.TestCase):
    def test_exact_original_id_vectors_match_workflow(self):
        root = (ROOT / 'build.gradle').read_text()
        release = (ROOT / '.github/workflows/vlc-release.yml').read_text()
        guard = root.split("def rdRequestedTasks = gradle.startParameter.taskNames", 1)[1].split("appId =", 1)[0]
        self.assertIn("rdRequestedTasks != [':application:app:assembleSignedRelease']", guard)
        self.assertIn("rdRequestedTasks != [':application:app:dependencies', '--configuration', 'signedReleaseRuntimeClasspath']", guard)
        self.assertNotIn('.every', guard)
        self.assertIn('gradle --no-daemon :application:app:assembleSignedRelease', release)
        self.assertRegex(release, r':application:app:dependencies\s+\\\s+--configuration signedReleaseRuntimeClasspath')

    def test_hosted_gate_is_required_and_real(self):
        workflow = (ROOT / '.github/workflows/vlc-pr.yml').read_text()
        hosted = workflow.split('  android-debug:', 1)[1]
        self.assertEqual(hosted.count('run: bash ci/test_release_invocations.sh'), 1)
        step = hosted.split('Exercise real Gradle release invocation policy with disposable test key', 1)[1].split('      - name:', 1)[0]
        self.assertNotIn('if:', step)
        self.assertNotIn('continue-on-error', step)
        self.assertNotIn('secrets.', step)
        script = (ROOT / 'ci/test_release_invocations.sh').read_text()
        self.assertIn('keytool -genkeypair', script)
        self.assertIn('for identity in standalone original', script)
        self.assertIn('gradle --no-daemon :application:app:dependencies --configuration signedReleaseRuntimeClasspath', script)
        for case in ('wrong_configuration', 'missing_configuration', 'extra_task', 'no-key-assembly'):
            self.assertIn(case, script)
        self.assertIn("trap 'rm -rf -- \"$fixture\"' EXIT", script)
        self.assertEqual(subprocess.run(['bash', '-n', str(ROOT / 'ci/test_release_invocations.sh')]).returncode, 0)

if __name__ == '__main__':
    unittest.main()
