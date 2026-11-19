#!/usr/bin/env python3
"""Read-only worktree upstream-merge qualification for VLC Android.

This performs no checkout, branch movement, upstream merge or remote mutation.
Git's merge-tree writes *only disposable Git tree objects* in the CI checkout.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

UPSTREAM_REPO = "KuchiSofts/vlc-redesign-android"
_SHA = re.compile(r"[0-9a-f]{40}\Z")


class QualificationError(Exception):
    pass


def run_git(*args: str, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", check=False)
    if check and proc.returncode != 0:
        raise QualificationError(f"git {' '.join(args[:2])}: {proc.stderr.strip() or proc.stdout.strip()}")
    return proc


def canonical_repo(url: str) -> str | None:
    """Return owner/repository for a literal GitHub URL (not any arbitrary host)."""
    s = url.strip()
    m = re.fullmatch(r"(?:https://github\.com/|ssh://git@github\.com/|git@github\.com:)([\w.-]+/[\w.-]+?)(?:\.git)?/?", s, flags=re.I)
    return m.group(1).lower() if m else None


def resolve_commit(ref: str, *, cwd: Path | None = None) -> str:
    if not ref or ref.startswith("-"):
        raise QualificationError("Unsafe/empty revision")
    sha = run_git("rev-parse", "--verify", "--end-of-options", ref + "^{commit}", cwd=cwd).stdout.strip()
    if not _SHA.fullmatch(sha):
        raise QualificationError("Git did not resolve a full commit SHA")
    return sha


def qualify(*, cwd: Path | None = None, fork_ref: str = "HEAD",
            upstream_ref: str = "refs/remotes/upstream/main",
            expected_fork: str | None = None, expected_upstream: str | None = None,
            verify_upstream_url: bool = True) -> dict[str, str]:
    if verify_upstream_url:
        url = run_git("remote", "get-url", "upstream", cwd=cwd).stdout.strip()
        if canonical_repo(url) != UPSTREAM_REPO.lower():
            raise QualificationError("upstream remote must be the official KuchiSofts source")
    ours = resolve_commit(fork_ref, cwd=cwd)
    theirs = resolve_commit(upstream_ref, cwd=cwd)
    for label, expected, observed in (("fork", expected_fork, ours), ("upstream", expected_upstream, theirs)):
        if expected is not None and (not _SHA.fullmatch(expected) or expected != observed):
            raise QualificationError(f"{label} SHA drift: expected {expected}, observed {observed}")
    shared = run_git("merge-base", ours, theirs, cwd=cwd, check=False)
    if shared.returncode != 0 or not _SHA.fullmatch(shared.stdout.strip()):
        raise QualificationError("No shared Git ancestry; this is not a mergeable upstream fork")
    attempt = run_git("merge-tree", "--write-tree", "--messages", ours, theirs, cwd=cwd, check=False)
    outcome = "mergeable" if attempt.returncode == 0 else "conflicted" if attempt.returncode == 1 else "error"
    if outcome == "error":
        raise QualificationError("merge-tree failed: " + (attempt.stderr or attempt.stdout).strip()[:1000])
    first_line = attempt.stdout.splitlines()[0].strip() if attempt.stdout else ""
    result = {
        "schema_version": 1,
        "source": UPSTREAM_REPO,
        "fork_sha": ours,
        "upstream_sha": theirs,
        "merge_base_sha": shared.stdout.strip(),
        "result": outcome,
        "candidate_tree": first_line if outcome == "mergeable" and _SHA.fullmatch(first_line) else "",
        "diagnostic": (attempt.stdout + "\n" + attempt.stderr).strip()[:8192] if outcome != "mergeable" else "",
    }
    return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--fork-ref", default="HEAD")
    p.add_argument("--upstream-ref", default="refs/remotes/upstream/main")
    p.add_argument("--expected-fork-sha")
    p.add_argument("--expected-upstream-sha")
    p.add_argument("--output", help="Write JSON report below CI workspace")
    p.add_argument("--skip-remote-check", action="store_true", help="Only for local fixture tests")
    args = p.parse_args(argv)
    try:
        r = qualify(fork_ref=args.fork_ref, upstream_ref=args.upstream_ref,
                    expected_fork=args.expected_fork_sha, expected_upstream=args.expected_upstream_sha,
                    verify_upstream_url=not args.skip_remote_check)
    except QualificationError as ex:
        r = {"schema_version": 1, "result": "error", "diagnostic": str(ex)}
    body = json.dumps(r, sort_keys=True, indent=2) + "\n"
    if args.output:
        path = Path(args.output)
        if path.is_absolute() or ".." in path.parts or path.is_symlink():
            print("Unsafe report path; requires workspace-relative regular file", file=sys.stderr)
            return 2
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    print(body, end="")
    return 0 if r["result"] == "mergeable" else 1


if __name__ == "__main__":
    raise SystemExit(main())
