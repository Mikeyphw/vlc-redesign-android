"""Current, negative and regression CI contracts; no obsolete milestone gates."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ci"))
from workflow_policy import (  # noqa: E402
    ContractFailure, REPOSITORY, WORKFLOW_ID, WORKFLOW_NAME,
    check_repository, require_policy, require_workflow_contract,
    require_workflow_safe,
)


def source_files() -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8")
            for p in (ROOT / ".github/workflows").glob("*.yml")}


def valid_policy() -> dict:
    return json.loads((ROOT / "config/delivery-required-ci.json").read_text(encoding="utf-8"))


class CIContracts(unittest.TestCase):
    def test_real_workflow_and_policy(self):
        require_workflow_contract(source_files())
        require_policy(valid_policy())
        check_repository(ROOT)

    def test_guard_does_not_self_match(self):
        # The enforcement token occurs only in source code, not in a YAML command.
        source = source_files()["vlc-pr.yml"]
        require_workflow_safe(source, filename="vlc-pr.yml")
        self.assertIn("python3 -B ci/workflow_policy.py", source)

    def test_privileged_event_blocked_in_block_and_flow_forms(self):
        for snippet in ("on:\n  pull_request_target:\n", "on: [pull_request_target]",
                        "on: {'pull_request_target': {}}", "# pull_request_target:"):
            with self.subTest(snippet=snippet), self.assertRaises(ContractFailure):
                require_workflow_safe(snippet, filename="hostile.yml")

    def test_privileged_permissions_blocked(self):
        for snippet in ("permissions: write-all\n", "permissions:\n  contents: write\n",
                        "permissions: {contents: write}\n", "permissions:\n  id-token: write\n"):
            with self.subTest(snippet=snippet), self.assertRaises(ContractFailure):
                require_workflow_safe(snippet, filename="hostile.yml")

    def test_false_success_of_required_policy_blocked(self):
        for changes in ({"workflow_id": 12345}, {"name": "Wrong workflow"}):
            bad = copy.deepcopy(valid_policy())
            bad["required_workflows"][0].update(changes)
            with self.assertRaises(ContractFailure):
                require_policy(bad)

    def test_policy_must_match_repository_and_event(self):
        for field, wrong in (("repository", "KuchiSofts/vlc-redesign-android"),
                             ("base_branch", "other"), ("event", "push"),
                             ("release_qualification", "passed")):
            bad = copy.deepcopy(valid_policy())
            bad[field] = wrong
            with self.subTest(field=field), self.assertRaises(ContractFailure):
                require_policy(bad)

    def test_policy_exact_fields_and_types(self):
        bad = valid_policy();bad["undocumented"] = True
        with self.assertRaises(ContractFailure): require_policy(bad)
        bad = valid_policy();bad["schema_version"] = True
        with self.assertRaises(ContractFailure): require_policy(bad)
        bad = valid_policy();bad["required_workflows"][0]["workflow_id"] = "422964106"
        with self.assertRaises(ContractFailure): require_policy(bad)

    def test_required_identity_is_observed(self):
        self.assertEqual(REPOSITORY, "Mikeyphw/vlc-redesign-android")
        self.assertEqual(WORKFLOW_ID, 422964106)
        self.assertEqual(WORKFLOW_NAME, "VLC Android PR qualification")

    def test_wrong_gradle_version_is_refused(self):
        files = source_files()
        self.assertIn("gradle-version: '9.6.0'", files["vlc-pr.yml"])
        files["vlc-pr.yml"] = files["vlc-pr.yml"].replace("gradle-version: '9.6.0'", "gradle-version: '9.4.0'")
        with self.assertRaises(ContractFailure):
            require_workflow_contract(files)

    def test_missing_android_or_source_job_dependency_is_refused(self):
        files = source_files()
        files["vlc-pr.yml"] = files["vlc-pr.yml"].replace("needs: source-contracts", "needs: unknown", 1)
        with self.assertRaises(ContractFailure):
            require_workflow_contract(files)

    def test_maven_gate_runs_before_heavy_hosted_setup(self):
        files = source_files()
        workflow = files["vlc-pr.yml"]
        self.assertLess(workflow.index("- name: Enforce patched MediaLibrary dependency"),
                        workflow.index("- uses: actions/setup-java@v4"))
        # Negative: a check run *after* SDK setup wastes resources and hides dependency failures.
        segment_start = workflow.index("      - name: Enforce patched MediaLibrary dependency")
        segment_end = workflow.index("      - uses: actions/setup-java@v4", segment_start)
        gate = workflow[segment_start:segment_end]
        after_setup = workflow[:segment_start] + workflow[segment_end:]
        insert = after_setup.index("      - name: Compile Android debug app")
        files["vlc-pr.yml"] = after_setup[:insert] + gate + after_setup[insert:]
        with self.assertRaises(ContractFailure):
            require_workflow_contract(files)

    def test_no_silent_unpatched_media_library_fallback(self):
        files = source_files()
        files["vlc-pr.yml"] = files["vlc-pr.yml"].replace("VLC_RD_MAVEN_BASE_URL", "MISSING_MAVEN_SOURCE")
        with self.assertRaises(ContractFailure):
            require_workflow_contract(files)


if __name__ == "__main__":
    unittest.main()
