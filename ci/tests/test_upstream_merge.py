"""Positive and adversarial cases for the actual upstream merge simulation."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from upstream_merge import QualificationError, canonical_repo, qualify, resolve_commit


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="vlc-upstream-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Upstream Test")
        self.git("config", "user.email", "test@example.invalid")
        self.git("remote", "add", "upstream", "https://github.com/KuchiSofts/vlc-redesign-android.git")
        self.edit("shared.txt", "original\n")
        self.git("add", ".")
        self.git("commit", "-m", "initial")
        self.base = self.sha()

    def git(self, *args):
        p = subprocess.run(["git", *args], cwd=self.root, capture_output=True, text=True)
        if p.returncode:
            raise AssertionError(f"git {args}: {p.stderr}")
        return p.stdout.strip()

    def sha(self):
        return self.git("rev-parse", "HEAD")

    def edit(self, file, content):
        (self.root / file).write_text(content, encoding="utf-8")

    def upstream_commit(self, filename, value):
        self.git("switch", "-c", "upstream", self.base)
        self.edit(filename, value)
        self.git("add", ".")
        self.git("commit", "-m", "upstream change")
        upstream_sha = self.sha()
        self.git("switch", "main")
        return upstream_sha

    def test_clean_divergence_merges_without_checkout(self):
        up = self.upstream_commit("remote.txt", "upstream\n")
        self.edit("local.txt", "local\n")
        self.git("add", ".")
        self.git("commit", "-m", "local")
        before = self.sha()
        report = qualify(cwd=self.root, fork_ref="HEAD", upstream_ref=up,
                         expected_fork=before, expected_upstream=up)
        self.assertEqual(report["result"], "mergeable")
        self.assertEqual(report["fork_sha"], before)
        self.assertEqual(self.sha(), before, "must not change checkout HEAD")
        self.assertFalse((self.root / "remote.txt").exists(), "must not merge files into checkout")

    def test_conflict_is_hard_failure(self):
        up = self.upstream_commit("shared.txt", "UPSTREAM\n")
        self.edit("shared.txt", "FORK\n")
        self.git("add", ".")
        self.git("commit", "-m", "fork conflicting change")
        report = qualify(cwd=self.root, upstream_ref=up)
        self.assertEqual(report["result"], "conflicted")
        self.assertEqual((self.root / "shared.txt").read_text(), "FORK\n")

    def test_stale_fork_preimage_refused(self):
        up = self.upstream_commit("remote.txt", "upstream\n")
        with self.assertRaisesRegex(QualificationError, "fork SHA drift"):
            qualify(cwd=self.root, upstream_ref=up, expected_fork="f" * 40)

    def test_stale_upstream_refused(self):
        up = self.upstream_commit("remote.txt", "upstream\n")
        with self.assertRaisesRegex(QualificationError, "upstream SHA drift"):
            qualify(cwd=self.root, upstream_ref=up, expected_upstream="e" * 40)

    def test_wrong_upstream_remote_refused(self):
        up = self.upstream_commit("remote.txt", "upstream\n")
        self.git("remote", "set-url", "upstream", "https://github.com/attacker/vlc-redesign-android")
        with self.assertRaisesRegex(QualificationError, "official KuchiSofts"):
            qualify(cwd=self.root, upstream_ref=up)

    def test_unsafe_revision_refused(self):
        with self.assertRaisesRegex(QualificationError, "Unsafe"):
            resolve_commit("--upload-pack=anything", cwd=self.root)

    def test_unrelated_history_is_refused(self):
        self.git("switch", "--orphan", "unrelated")
        for entry in self.root.iterdir():
            if entry.name != ".git" and entry.is_file():
                entry.unlink()
        self.edit("other.txt", "foreign\n")
        self.git("add", ".")
        self.git("commit", "-m", "unrelated root")
        foreign = self.sha()
        self.git("switch", "main")
        with self.assertRaisesRegex(QualificationError, "No shared Git ancestry"):
            qualify(cwd=self.root, upstream_ref=foreign)

    def test_allowed_upstream_urls_only(self):
        for url in ("https://github.com/KuchiSofts/vlc-redesign-android.git",
                    "git@github.com:KuchiSofts/vlc-redesign-android.git",
                    "ssh://git@github.com/KuchiSofts/vlc-redesign-android"):
            self.assertEqual(canonical_repo(url), "kuchisofts/vlc-redesign-android")
        for url in ("https://evil.example/KuchiSofts/vlc-redesign-android",
                    "https://github.com/attacker/vlc-redesign-android",
                    "git@github.com:KuchiSofts/vlc-redesign-android.evil.git"):
            self.assertNotEqual(canonical_repo(url), "kuchisofts/vlc-redesign-android")


if __name__ == "__main__":
    unittest.main()
