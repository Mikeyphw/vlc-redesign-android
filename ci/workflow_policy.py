#!/usr/bin/env python3
"""Source-owned, fail-closed checks for VLC Android workflows and CI identity.

No GitHub token, Gradle, network access or third-party Python dependencies.
This verifier runs locally, in Devtool's native validation hook and in hosted CI.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys

REPOSITORY = "Mikeyphw/vlc-redesign-android"
WORKFLOW_FILE = "vlc-pr.yml"
WORKFLOW_NAME = "VLC Android PR qualification"
WORKFLOW_ID = 422964106  # observed from GitHub Actions run 44371205406
GRADLE_MINIMUM = "9.6.0"  # required by upstream AGP 9.4.x
POLICY_PATH = Path("config/delivery-required-ci.json")
WORKFLOW_DIRECTORY = Path(".github/workflows")


class ContractFailure(ValueError):
    pass


def require_workflow_safe(text: str, *, filename: str) -> None:
    """Conservatively forbid privileged PR events/permissions in any workflow.

    Searching the YAML document for the sensitive token also catches aliases,
    flow-style event lists and quoted keys. The implementation lives outside
    the YAML files, eliminating self-matching command strings. Comments that
    contain the forbidden token are deliberately rejected (fail closed).
    """
    if re.search(r"(?<![A-Za-z0-9_])pull_request_target(?![A-Za-z0-9_])", text):
        raise ContractFailure(f"{filename}: privileged pull request event is prohibited")
    if re.search(r"(?m)^\s*permissions\s*:\s*(?:write-all|\{[^}]*\bwrite\b[^}]*\})", text):
        raise ContractFailure(f"{filename}: over-broad workflow permissions are prohibited")
    if re.search(r"(?m)^\s*(?:contents|actions|id-token|pull-requests|issues|packages|workflows|checks|statuses|deployments)\s*:\s*write\s*(?:#.*)?$", text):
        raise ContractFailure(f"{filename}: write-permission escalation is prohibited")


def require_policy(policy: dict) -> None:
    required = {"schema_version", "repository", "base_branch", "event", "release_qualification", "required_workflows"}
    if type(policy) is not dict or set(policy) != required:
        raise ContractFailure("required CI policy has missing or unsupported keys")
    if (type(policy["schema_version"]) is not int or policy["schema_version"] != 1
            or policy["repository"] != REPOSITORY
            or policy["base_branch"] != "main"
            or policy["event"] != "pull_request"
            or policy["release_qualification"] != "separate"):
        raise ContractFailure("required CI policy repository/base/event/release identity mismatch")
    expected = [{"name": WORKFLOW_NAME, "workflow_id": WORKFLOW_ID}]
    if policy["required_workflows"] != expected:
        raise ContractFailure("required CI workflow name or numeric GitHub ID mismatch")


def require_workflow_contract(contents: dict[str, str]) -> None:
    if WORKFLOW_FILE not in contents or "vlc-upstream.yml" not in contents:
        raise ContractFailure("source or read-only upstream workflow missing")
    for filename, source in sorted(contents.items()):
        require_workflow_safe(source, filename=filename)
    source = contents[WORKFLOW_FILE]
    if not re.search(r"(?m)^name:\s*VLC Android PR qualification\s*$", source):
        raise ContractFailure("PR workflow name drifted from required CI policy")
    if not re.search(r"(?m)^on:\s*\n\s+pull_request:\s*\n\s+branches:\s*\[main\]", source):
        raise ContractFailure("PR event or main-branch target is missing")
    if not re.search(r"(?m)^\s+permissions:\s*\n\s+contents:\s*read\s*$", source):
        # Also accept a workflow-global 'permissions: contents: read' block.
        if not re.search(r"(?m)^permissions:\s*\n\s+contents:\s*read\s*$", source):
            raise ContractFailure("PR workflow must have explicit read-only permissions")
    if "python3 -B ci/workflow_policy.py" not in source:
        raise ContractFailure("PR workflow does not execute source-owned policy gate")
    if not re.search(r"(?m)^\s+gradle-version:\s*['\"]?9\.6\.0['\"]?\s*$", source):
        raise ContractFailure("hosted Gradle version violates AGP 9.4 compatibility minimum")
    if not re.search(r"(?m)^\s+needs:\s*source-contracts\s*$", source):
        raise ContractFailure("Android build must depend on source-contract qualification")
    if "VLC_RD_MAVEN_BASE_URL" not in source or "assembleDebug" not in source:
        raise ContractFailure("patched Maven dependency or real Android compilation gate missing")
    dependency_check = source.find("- name: Enforce patched MediaLibrary dependency")
    toolchain_setup = source.find("- uses: actions/setup-java@v4", source.find("  android-debug:"))
    if dependency_check < 0 or toolchain_setup < 0 or dependency_check >= toolchain_setup:
        raise ContractFailure("patched Maven source must fail before expensive hosted setup")


def check_repository(root: Path) -> None:
    workflow_root = root / WORKFLOW_DIRECTORY
    if not workflow_root.is_dir() or workflow_root.is_symlink():
        raise ContractFailure("workflow directory unavailable or untrusted")
    paths = sorted((*workflow_root.glob("*.yml"), *workflow_root.glob("*.yaml")))
    if not paths:
        raise ContractFailure("no GitHub Actions workflows available")
    if any(not path.is_file() or path.is_symlink() for path in paths):
        raise ContractFailure("unsafe workflow file type")
    contents = {path.name: path.read_text(encoding="utf-8") for path in paths}
    require_workflow_contract(contents)
    policy_path = root / POLICY_PATH
    if not policy_path.is_file() or policy_path.is_symlink():
        raise ContractFailure("committed-policy candidate is missing or symlinked")
    require_policy(json.loads(policy_path.read_text(encoding="utf-8")))
    upstream_build = root / "build.gradle"
    if upstream_build.is_file():
        source = upstream_build.read_text(encoding="utf-8")
        if not re.search(r"(?m)^\s*ext\.android_plugin_version\s*=\s*['\"]9\.4\.1['\"]", source):
            raise ContractFailure("AGP version changed; requalify hosted Gradle pairing")


def main() -> int:
    try:
        check_repository(Path.cwd())
    except (ContractFailure, OSError, UnicodeError, ValueError) as exc:
        print(f"VLC_CI_CONTRACT_FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"VLC_CI_CONTRACT_PASS workflow_id={WORKFLOW_ID} hosted_gradle={GRADLE_MINIMUM}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
