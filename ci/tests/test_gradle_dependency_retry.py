"""Bounded Gradle Maven classpath retry; refuse test bypass and unrelated errors."""
from pathlib import Path
import os
import subprocess
import sys
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT/'ci/gradle_dependency_retry.sh'

FAKE_GRADLE = '''import os,sys
from pathlib import Path
p=Path(os.environ['VLC_FAKE_CALLS'])
items=p.read_text().splitlines() if p.is_file() else []
items.append(' '.join(sys.argv[1:]))
p.write_text('\\n'.join(items)+'\\n')
mode=os.environ.get('VLC_FAKE_MODE')
if mode=='success' or (mode=='transient' and len(items)>1):
 print('FAKE_GRADLE_REAL_STDOUT visible')
 print('FAKE_GRADLE_REAL_STDERR visible',file=sys.stderr)
 sys.exit(0)
if mode=='jvm-failure':
 print('> Task :application:app:testDebugUnitTest FAILED')
 print("Could not resolve all artifacts for configuration 'classpath'.")
 print('Could not find library.jar')
 print('Searched in the following locations:')
 print('https://repo.maven.apache.org/maven2/example')
 sys.exit(4)
if mode=='compile-failure':
 print('> Task :application:app:compileDebugKotlin FAILED')
 print('Compilation error in app')
 sys.exit(5)
if mode=='no-maven':
 print("Could not resolve all artifacts for configuration 'classpath'.")
 print('Could not find library.jar')
 print('Searched in the following locations:')
 print('https://evil.example.invalid/artifacts/library.jar')
 sys.exit(7)
print("Could not resolve all artifacts for configuration 'classpath'.")
print('Could not find org.jetbrains.kotlin:kotlin-stdlib:2.2.10.')
print('Searched in the following locations:')
print('https://repo.maven.apache.org/maven2/org/jetbrains/kotlin/kotlin-stdlib/2.2.10/kotlin-stdlib-2.2.10.pom')
sys.exit(1)
'''

class GradleRetryTests(unittest.TestCase):
    def setUp(self):
        # Android does not provide Linux's /usr/bin/env or /bin/sh. Keep
        # executable fixtures on internal storage and use the actual running
        # Python, not a system shebang or a fallback to a real Gradle.
        self.python = os.path.abspath(sys.executable)
        prefix = os.environ.get('PREFIX', '')
        internal_tmp = None
        if sys.platform == 'android' or self.python.startswith('/data/') or prefix.startswith('/data/'):
            # Derive the prefix when a launcher has stripped the PREFIX variable.
            runtime_prefix = Path(prefix) if prefix.startswith('/data/') else Path(self.python).resolve().parent.parent
            internal_tmp = runtime_prefix / 'tmp'
            if not internal_tmp.is_dir() or not os.access(internal_tmp, os.W_OK | os.X_OK):
                internal_tmp = Path.home()
        self.tmp=tempfile.TemporaryDirectory(dir=internal_tmp)
        self.addCleanup(self.tmp.cleanup)
        if not os.path.isfile(self.python) or not os.access(self.python, os.X_OK) or any(c.isspace() for c in self.python):
            self.fail('Fixture requires a directly executable Python interpreter path')
        self.root=Path(self.tmp.name)
        p=self.root/'bin'
        p.mkdir()
        gradle=p/'gradle'
        gradle.write_text('#!'+self.python+'\n'+FAKE_GRADLE)
        gradle.chmod(0o755)
        sleep=p/'sleep'
        sleep.write_text('#!'+self.python+'\nraise SystemExit(0)\n')
        sleep.chmod(0o755)
        self.env=dict(os.environ, PATH=str(p)+os.pathsep+os.environ.get('PATH',''),
                      VLC_FAKE_CALLS=str(self.root/'calls'), TMPDIR=str(self.root), VLC_FAKE_MODE='success')

    def invoke(self,mode='success',task='test'):
        env=dict(self.env,VLC_FAKE_MODE=mode)
        self.assertEqual(shutil.which('gradle', path=env['PATH']), str(self.root/'bin/gradle'))
        self.assertEqual(shutil.which('sleep', path=env['PATH']), str(self.root/'bin/sleep'))
        r=subprocess.run(['bash',str(RUNNER),task],env=env,capture_output=True,text=True,timeout=20)
        calls=(self.root/'calls').read_text().splitlines() if (self.root/'calls').exists() else []
        return r,calls

    def test_fixture_executables_use_current_python_without_env_or_shell(self):
        for name in ('gradle', 'sleep'):
            path = self.root/'bin'/name
            self.assertEqual(path.read_text().splitlines()[0], '#!'+self.python)
            result = subprocess.run([str(path)], env=dict(self.env, PATH=str(self.root/'bin')),
                                    capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root/'calls').read_text().splitlines(), [''])

    def test_first_pass_runs_mock_gradle_once(self):
        r,calls=self.invoke()
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(len(calls),1)
        self.assertIn('testDebugUnitTest',calls[0])
        self.assertNotIn('--refresh-dependencies',calls[0])
        self.assertIn('FAKE_GRADLE_REAL_STDOUT visible',r.stdout)
        self.assertIn('FAKE_GRADLE_REAL_STDERR visible',r.stdout)

    def test_network_classpath_failure_retried_fresh_then_passes(self):
        r,calls=self.invoke('transient')
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(len(calls),2)
        self.assertNotIn('--refresh-dependencies',calls[0])
        self.assertIn('--refresh-dependencies',calls[1])
        self.assertIn('VLC_GRADLE_REMOTE_CLASSPATH_RETRY',r.stderr)

    def test_still_missing_after_three_attempts_fails_closed(self):
        r,calls=self.invoke('always-missing')
        self.assertEqual(r.returncode,1)
        self.assertEqual(len(calls),3)
        self.assertTrue(all('--refresh-dependencies' in arg for arg in calls[1:]))
        self.assertIn('VLC_GRADLE_REMOTE_CLASSPATH_UNAVAILABLE',r.stderr)
        self.assertNotIn('VLC_GRADLE_NATIVE_PASS',r.stderr)

    def test_reuses_only_approved_assemble_task(self):
        r,calls=self.invoke('transient','assemble')
        self.assertEqual(r.returncode,0)
        self.assertEqual(len(calls),2)
        self.assertTrue(all(':application:app:assembleDebug' in c for c in calls))
        self.assertTrue(all(':application:app:testDebugUnitTest' not in c for c in calls))

    def test_no_retry_on_jvm_failure_even_with_dependency_text(self):
        r,calls=self.invoke('jvm-failure')
        self.assertEqual(r.returncode,4)
        self.assertEqual(len(calls),1)
        self.assertIn('VLC_GRADLE_NON_CLASSPATH_FAILURE',r.stderr)

    def test_no_retry_on_compiler_failure(self):
        r,calls=self.invoke('compile-failure')
        self.assertEqual(r.returncode,5)
        self.assertEqual(len(calls),1)
        self.assertIn('VLC_GRADLE_NON_CLASSPATH_FAILURE',r.stderr)

    def test_no_retry_for_untrusted_maven_host(self):
        r,calls=self.invoke('no-maven')
        self.assertEqual(r.returncode,7)
        self.assertEqual(len(calls),1)
        self.assertIn('VLC_GRADLE_NON_CLASSPATH_FAILURE',r.stderr)

    def test_invalid_command_refused_before_gradle(self):
        for mode in ('release','publish','testDebugUnitTest',''):
            r,calls=self.invoke('success',mode)
            self.assertEqual(r.returncode,2)
            self.assertEqual(calls,[])

if __name__=='__main__':
    unittest.main()
