
import subprocess
import unittest

class CompilerFileModeTest(unittest.TestCase):
    def test_compile_sh_is_executable_in_git(self):
        result = subprocess.check_output(
            ["git", "ls-files", "--stage", "--", "buildsystem/compile.sh"],
            text=True
        )
        self.assertTrue(result.startswith("100755 "), result)
