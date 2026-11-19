"""Bounded Gradle Maven classpath retry; refuse test bypass and unrelated errors."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT/'ci/gradle_dependency_retry.sh'

FAKE_GRADLE = '''#!/usr/bin/env python3
import os,sys
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
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        p=self.root/'bin'
        p.mkdir()
        gradle=p/'gradle'
        gradle.write_text(FAKE_GRADLE)
        gradle.chmod(0o755)
        sleep=p/'sleep'
        sleep.write_text('#!/bin/sh\nexit 0\n')
        sleep.chmod(0o755)
        self.env=dict(os.environ, PATH=str(p)+os.pathsep+os.environ.get('PATH',''),
                      VLC_FAKE_CALLS=str(self.root/'calls'), TMPDIR=str(self.root), VLC_FAKE_MODE='success')

    def invoke(self,mode='success',task='test'):
        env=dict(self.env,VLC_FAKE_MODE=mode)
        r=subprocess.run(['bash',str(RUNNER),task],env=env,capture_output=True,text=True,timeout=20)
        calls=(self.root/'calls').read_text().splitlines() if (self.root/'calls').exists() else []
        return r,calls

    def test_first_pass_runs_real_gradle_once(self):
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
