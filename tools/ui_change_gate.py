#!/usr/bin/env python3
"""Enforce design-first ordering and exact reference lineage for UI implementation changes."""

from __future__ import annotations

import argparse
import copy
import fnmatch
import hashlib
import json
import os
import re
import subprocess
from datetime import date, datetime
from functools import lru_cache
from itertools import pairwise
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker

TEXT_SUFFIXES = frozenset(
    {".css", ".html", ".js", ".json", ".md", ".mjs", ".py", ".scss", ".ts", ".tsx", ".yaml", ".yml"}
)
REFERENCE_EXCLUSIONS = frozenset(
    {"REFERENCE_MANIFEST.yaml", "SHA256SUMS.txt", "VALIDATION_REPORT.md", "ui-reference-validation.json"}
)
HUMAN_ID = re.compile(r"^human:[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$")
AGENT_ID = re.compile(r"agent:(?:/?[a-z0-9_-]+)(?:/[a-z0-9_-]+)*")
LINKED_CORRECTION_ID = re.compile(r"W(?:[0-9]|1[01])\.C[0-9]{2,}\.T01")
INTENTIONAL_AMENDMENT_ID = "W2.A01"
INTENTIONAL_AMENDMENT_TASK_ID = "W2.A01.T02"
INTENTIONAL_AMENDMENT_CONTROL_TASK_ID = "W2.A01.T01"
INTENTIONAL_AMENDMENT_CHANGE_REQUEST_ID = "ECR-0009"
INTENTIONAL_AMENDMENT_REFERENCE_ID = "RO-UI-ACADEMIC-MINIMAL-1.8"
INTENTIONAL_AMENDMENT_REFERENCE_APPROVAL_PATH = "planning/reference-approvals/RO-UI-ACADEMIC-MINIMAL-1.8.json"
ADOPTED_CONTINUATION_TASK_ID = "CAP-05.S01.T01"
ADOPTED_CONTINUATION_BASE = "6506c68461144747b0ee9be10853211717aa381d"
ADOPTED_CONTINUATION_CONTRACT_PATH = "artifacts/evidence/ui-change/CAP-05.S01.T01.json"
ADOPTED_CONTINUATION_INHERITED_CONTRACT_PATH = "artifacts/evidence/ui-change/W2.A01.T02.json"
ADOPTED_CONTINUATION_APPROVED_REFERENCE = "RO-UI-ACADEMIC-MINIMAL-1.8"
REFERENCE_ACTIVATION_AMENDMENT_ID = "W2.A03"
REFERENCE_ACTIVATION_PACKET_COMMIT = "746c05dcd7dbabaa7f5eebee8e3fa56b8ac6b9b5"
REFERENCE_ACTIVATION_CONTROL_TASK_ID = "W2.A03.T01"
REFERENCE_ACTIVATION_CONSUMER_TASK_ID = "W2.A03.T02"
REFERENCE_ACTIVATION_WITNESS_PATH = "packages/contracts/workflow-profile/presentation-compatibility-1.8.json"
REFERENCE_ACTIVATION_CONTROL_SOURCE = frozenset(
    {
        REFERENCE_ACTIVATION_WITNESS_PATH,
        "tools/ui_conformance.py",
        "tests/contracts/test_workflow_profile_contracts.py",
        "tests/desktop/test_ui_conformance.py",
        "tools/ui_change_gate.py",
        "tests/foundation/test_ui_change_gate.py",
        "design/ui-change.schema.json",
        "docs/automation/design-first-ui-changes.md",
        "docs/automation/ui-conformance-verification.md",
        "docs/adr/ADR-0039-bind-approved-desktop-reference-activation.md",
        "docs/adr/index.json",
    }
)
REFERENCE_ACTIVATION_CONSUMER_SOURCE = frozenset(
    {
        "verification/extensions/desktop-ui.json",
        "verification/baselines/desktop-ui.json",
        "apps/desktop/scripts/assemble-reference.mjs",
        "apps/desktop/scripts/assemble-application.mjs",
        "tests/desktop/test_desktop_app_check.py",
        "tests/desktop/test_ui_conformance.py",
        "tests/foundation/test_ui_reference_check.py",
    }
)
REFERENCE_ACTIVATION_CONSUMER_FILES = frozenset(
    {
        "verification/extensions/desktop-ui.json",
        "verification/baselines/desktop-ui.json",
        "apps/desktop/scripts/assemble-reference.mjs",
        "apps/desktop/scripts/assemble-application.mjs",
    }
)
REFERENCE_ACTIVATION_SHARED_ORIGINAL_TESTS = frozenset(
    {
        "tests/desktop/test_desktop_app_check.py",
        "tests/desktop/test_ui_conformance.py",
        "tests/foundation/test_ui_reference_check.py",
    }
)
REFERENCE_ACTIVATION_GOV26_BASE = "0847aea4cf93bfc444373045ade4e17891b4afe5"
REFERENCE_ACTIVATION_GOV26_CANDIDATE = "6e396c5e18fefb255334e1ddeeea02eb4b6bdb2c"
REFERENCE_ACTIVATION_GOV26_REVIEW = "b763fa8ccff87c2828e94459252f02e35e1f4ef1"
REFERENCE_ACTIVATION_C10_BASE = "eee6f5df4ba2b940e69fc8d7b49c033139e01856"
REFERENCE_ACTIVATION_C10_CANDIDATE = "3dde91238b0be11847f68845a52b9785048dc8cd"
REFERENCE_ACTIVATION_C10_DISPOSITION = "015f0272d4eae0e34d2758b519ef5bc9df99ac5f"
REFERENCE_ACTIVATION_T03_RANGES = (
    ("2283e37e43cb56f8330b060b4c7d4b4f0f19489b", "9a22c5fe122358b854ceae6c7cb47cdfd68c8f12"),
    ("9a22c5fe122358b854ceae6c7cb47cdfd68c8f12", "42379f73cf6853be3618a8bb554ffa50a3fdf5c0"),
    ("42379f73cf6853be3618a8bb554ffa50a3fdf5c0", "c879f5d68aea48622b719e105b7915821ddbb6a5"),
)
REFERENCE_ACTIVATION_T03_SOURCE_COMMITS = (
    "33333d0f990ba6a01b7cec2fab1e9af7b2f7aee9",
    "63cd40222c110fbe748137190df15cf14f958b94",
    "9176dce55dcec315dad28c6e314bc7bfdad8652a",
)
REFERENCE_ACTIVATION_T03_MOVED_PATHS = frozenset(
    {
        "plugins/connectors/sample_repository/fixtures/repository-metadata.case.json",
        "plugins/connectors/sample_repository/fixtures/search-page-1.case.json",
        "plugins/connectors/sample_repository/fixtures/search-page-2.case.json",
        "plugins/connectors/sample_repository/manifest.json",
        "plugins/connectors/sample_repository/plugin/__init__.py",
        "plugins/connectors/sample_repository/plugin/connector.py",
    }
)
REFERENCE_ACTIVATION_BOOTSTRAP_APPROVAL = "f45d6de7af4bbd04f228483e78ea3e5b3c80de56"
REFERENCE_ACTIVATION_MATERIALIZATION = "b3120e32f521b60bbd03ddca8f755ba9871947cc"
REFERENCE_ACTIVATION_CAMPAIGN_START = "cd61bae9681690f92b754e443cd61f2c62026288"
REFERENCE_ACTIVATION_CONTROL_CLAIM = "1c71895f572b668a7dd5132a0a735a5d215f5406"
REFERENCE_ACTIVATION_CORRECTION_ID = "W2.A04"
REFERENCE_ACTIVATION_CORRECTION_TASK = "W2.A04.T01"
REFERENCE_ACTIVATION_CORRECTION_PACKET = "7f35c7a8e49eb8415ffdffa5a2e04374161f0eae"
REFERENCE_ACTIVATION_CORRECTION_PACKET_SHA = "eb1cbf1b827bffdd5914f9255c6f0bba374621f916711b3e05815202d0312b8c"
REFERENCE_ACTIVATION_COMBINED_PAUSE = "a211f24107f21f6b87221fd8b60c04b95a97fc8b"
REFERENCE_ACTIVATION_RETAINED_BASE = "ca8b1448e094b637bbd06c3129b69a78df792619"
REFERENCE_ACTIVATION_CORRECTION_BOOTSTRAP = "2c73da0c8af96e3436191f2339b827c4ddf8cf36"
REFERENCE_ACTIVATION_CORRECTION_MATERIALIZATION = "850cf16281779c09691e566ac453547338eb16a3"
REFERENCE_ACTIVATION_CORRECTION_ACTIVATION = "223f48a0cfac0612049fc6bf0537dac79f90be36"
REFERENCE_ACTIVATION_CORRECTION_CLAIM = "53d510464e2f9a2ab64bc9e78d09ae7b3996bba7"
REFERENCE_ACTIVATION_CORRECTION_ADR = "docs/adr/ADR-0040-document-protected-desktop-activation-correction.md"
REFERENCE_ACTIVATION_CORRECTION_SOURCE = frozenset(
    {
        "tools/ui_change_gate.py",
        "tests/foundation/test_ui_change_gate.py",
        "docs/automation/design-first-ui-changes.md",
        REFERENCE_ACTIVATION_CORRECTION_ADR,
        "docs/adr/index.json",
    }
)
REFERENCE_ACTIVATION_CORRECTION_WORKFLOW = frozenset(
    {
        "planning/backlog.yaml",
        "docs/planning-implementation-plan.md",
        "planning/status-summary.md",
        "planning/review-site/README.md",
        "planning/review-site/index.html",
        "planning/review-site/enablers/ECR-0011.html",
        "planning/review-site/enablers/ECR-0012.html",
        "planning/review-site/enablers/index.html",
        "planning/review-site/manifest.json",
        "planning/review-site/waves/W2.html",
    }
)
ADOPTED_CONTINUATION_MIXED_COMMIT = "9727f1b195e7dee300e7f3df3c289e7739fb0fdc"
ADOPTED_CONTINUATION_MIXED_TREE = "86070473647696598c9af57c5fc088eadaea667d"
ADOPTED_CONTINUATION_MIXED_UI_PATHS = frozenset(
    {
        "apps/desktop/src/app/DocumentAttachmentPane.tsx",
        "apps/desktop/src/app/documentAttachment.ts",
    }
)
ADOPTED_CONTINUATION_MIXED_PYTHON = (
    "services/core-api/src/research_observatory_core/migrations/versions/v0023_attachment_operations.py",
    "tests/desktop/tools/run_windows_document_drop_probe.py",
    "tests/desktop/tools/seed_document_drop_fixture.py",
    "tests/documents/test_attachment_lifecycle_regressions.py",
    "tests/desktop/tools/verify_document_attachment_fixture.py",
    "tests/desktop/tools/run_windows_document_picker_probe.py",
    "tests/desktop/test_document_stage_fixture_probe.py",
    "tests/desktop/test_document_attachment_fixture_verifier.py",
    "tests/desktop/test_windows_document_picker_probe.py",
)
ADOPTED_CONTINUATION_VERIFIER_CANDIDATE = "f54da79f9313bda175676f36d1ea0a29e8f57378"
ADOPTED_CONTINUATION_VERIFIER_REVIEW = "1f628843e415b6affbd811eb37d9fff437fac51f"
ADOPTED_CONTINUATION_VERIFIER_REVIEW_SHA256 = "cd0cfcb7f733fa45f739cfb282f3ef50bed935792daaeaa1aefd402b9c199dc7"
ADOPTED_CONTINUATION_GATE_CHAIN = (
    "0d9ab50b25e980c454c14ba597e06333b21d6d93",
    "089c00c62a3e1301b76bc6f0fd7052c63605eb05",
    "fff7a04b20ad571c40c81a524b1eec447d206e9f",
)
ADOPTED_CONTINUATION_GATE_REVIEW = "ab2c868eea54b00dc1e9e71c6cd2f2d9a0e5b9c1"
ADOPTED_CONTINUATION_GATE_REVIEW_SHA256 = "7b56f3896962b53d14f9e28b32ec0bc483c55ff6b09e2de655f784396af20398"
ADOPTED_CONTINUATION_QUALITY_CANDIDATE = "52ff3d04a4a6dd61b8f49c7de620ea4cbc9cfb0e"
ADOPTED_CONTINUATION_TASKCTL_PREDECESSOR = "9b72d0213d6210f7457654ebaccd26779bee2431"
ADOPTED_CONTINUATION_TASKCTL_TREE = "7fd55261c16d85d0f4beede92880c3358e136f3b"
ADOPTED_CONTINUATION_SITE_REPAIR_SOURCE = (
    "b07472407749386cfbd76d5d5649fb120a880cc8",
    "63eb761d82b98bbce5ae81d2dcaecb987ecc10b7",
)
ADOPTED_CONTINUATION_SITE_REPAIR_CANDIDATE = "c7489ac184ad1b2422f049c4bd1a28887c5a7aae"
ADOPTED_CONTINUATION_SITE_REPAIR_REVIEW = "3fb76d6cb6bce6eaf16774931704de68c6168500"
ADOPTED_CONTINUATION_SITE_REPAIR_REVIEW_SHA256 = "f24f9645a9a24d4023e84909e28660e57e39252fa6312bf59d22daf73fad721a"
ADOPTED_CONTINUATION_BOOTSTRAP_FOLLOWUP = "907ed1adefa1607aa372873eb804c8a1375b9ba0"
ADOPTED_CONTINUATION_BOOTSTRAP_FOLLOWUP_TREE = "233e7ffde2781a424c699783a2573d22227544b6"
ADOPTED_CONTINUATION_PLANNING_TOOLS = frozenset({"tools/plan_review_site.py", "tools/plan_review_check.py"})
ADOPTED_CONTINUATION_A01_CONTROL_CANDIDATE = "a2e16012cfa9eb9a0f3413438fa0a88583d0be50"
ADOPTED_CONTINUATION_A02_CONTROL_SOURCE = frozenset(
    {
        "design/ui-change.schema.json",
        "tools/ui_change_gate.py",
        "tests/foundation/test_ui_change_gate.py",
        "docs/automation/design-first-ui-changes.md",
        "docs/adr/ADR-0037-authenticate-adopted-attachment-ui-continuation.md",
        "docs/adr/index.json",
    }
)
ADOPTED_CONTINUATION_A02_TRACKING_OUTPUTS = frozenset(
    {
        "docs/planning-implementation-plan.md",
        "planning/backlog.yaml",
        "planning/review-site/enablers/ECR-0010.html",
        "planning/review-site/enablers/index.html",
        "planning/review-site/manifest.json",
        "planning/review-site/waves/W2.html",
        "planning/status-summary.md",
    }
)
ADOPTED_CONTINUATION_AUTHORITY_INPUTS = frozenset(
    {
        "tools/taskctl.py",
        "tools/planctl.py",
        "tools/governance_kernel.py",
        "tools/desktop_app_check.py",
        "tools/product_style_check.py",
        "tools/build_manifest.py",
        "tools/product_layout_measurements.py",
        "tools/ui_reference_check.py",
        "tools/adr_check.py",
    }
)
ADOPTED_CONTINUATION_PRODUCT_ROOTS = (
    "apps/",
    "services/",
    "workers/",
    "tests/",
    "modules/",
    "packages/",
    "verification/",
)
ADOPTED_CONTINUATION_PRODUCT_TOOLS = frozenset({"tools/architecture_check.py", "tools/core_sidecar_build.py"})
INTENTIONAL_AMENDMENT_CONTROL_PATHS = frozenset(
    {
        "tools/ui_change_gate.py",
        "design/ui-change.schema.json",
        "tests/foundation/test_ui_change_gate.py",
        "docs/automation/design-first-ui-changes.md",
        "docs/adr/ADR-0035-admit-exact-intentional-amendment-ui-lineage.md",
        "docs/adr/index.json",
    }
)
EXPECTED_POLICY_SCALARS = {
    "schemaVersion": "1.0",
    "documentType": "ui-change-policy",
    "referenceRoot": "design/ui-reference",
    "approvalPath": "design/ui-reference/APPROVAL.yaml",
    "manifestPath": "design/ui-reference/REFERENCE_MANIFEST.yaml",
    "contractSchemaPath": "design/ui-change.schema.json",
    "contractRoot": "artifacts/evidence/ui-change",
}
EXPECTED_IMPLEMENTATION_ROOTS = {
    "apps/desktop/src",
    "modules/ui",
    "packages/ui-components",
    "packages/ui-tokens",
}
EXPECTED_IMPLEMENTATION_EXTENSIONS = {
    ".css",
    ".html",
    ".js",
    ".jpeg",
    ".jpg",
    ".json",
    ".jsx",
    ".mjs",
    ".png",
    ".scss",
    ".svg",
    ".ts",
    ".tsx",
    ".webp",
    ".woff",
    ".woff2",
}
EXPECTED_IGNORED_SUFFIXES = {
    ".d.ts",
    ".spec.js",
    ".spec.jsx",
    ".spec.ts",
    ".spec.tsx",
    ".test.js",
    ".test.jsx",
    ".test.ts",
    ".test.tsx",
}
GATE_CONTROL_PATHS = frozenset(
    {
        ".github/pull_request_template.md",
        ".github/workflows/ci.yml",
        "architecture-protected-paths.json",
        "ci-policy.json",
        "design/ui-change.schema.json",
        "planning/backlog.schema.json",
        "quality-scope.json",
        "tools/ci_check.py",
        "tools/ui_change_gate.py",
        "tools/ui_accessibility_check.py",
        "tools/ui_conformance.py",
        "tools/ui_route_check.py",
        "tools/ui_token_check.py",
        "tools/ui_visual_regression_check.py",
        "tools/ui_workflow_check.py",
        "ui-change-policy.json",
        "verification/baselines/desktop-ui.json",
        "verification/desktop-ui-baseline.schema.json",
        "verification/desktop-ui.schema.json",
        "verification/extensions/desktop-ui.json",
        "verification-profiles.json",
    }
)
MAINTENANCE_CONTROL_PATHS = GATE_CONTROL_PATHS | frozenset(
    {
        "docs/automation/design-first-ui-changes.md",
        "tests/desktop/test_ui_conformance.py",
        "tests/foundation/test_ui_change_gate.py",
    }
)
LEGACY_GOVERNANCE_CONTROL_PATHS = MAINTENANCE_CONTROL_PATHS | frozenset(
    {
        "docs/automation/governance-automation-simplification.md",
        "planning/enabler-change-requests/enabler-change-request.v4.1.schema.json",
        "tests/foundation/test_governance_kernel.py",
        "tests/foundation/test_planctl_amendments.py",
        "tests/foundation/test_taskctl_workflow.py",
        "tools/governance_kernel.py",
        "tools/plan_review_site.py",
        "tools/planctl.py",
        "tools/taskctl.py",
    }
)
MAINTENANCE_CONTROL_ENVELOPE_CUTOVER = "07cecd999e84e1e6096df5fbbefe044c4789893f"
PROVENANCE_REFERENCE_HANDOFF_PATHS = frozenset(
    {
        "design/ui-reference/APPROVAL.yaml",
        "design/ui-reference/REFERENCE_MANIFEST.yaml",
    }
)
APPLICATION_ACTIVATION_PATHS = frozenset(
    {
        "quality-scope.json",
        "tools/ui_change_gate.py",
        "tools/ui_conformance.py",
        "verification/desktop-ui.schema.json",
        "verification/extensions/desktop-ui.json",
        "verification-profiles.json",
    }
)
APPLICATION_INVENTORY_HARDENING_ENVELOPE = frozenset(
    {
        "tests/desktop/test_ui_conformance.py",
        "tests/foundation/test_ui_change_gate.py",
        "tools/ui_change_gate.py",
        "tools/ui_conformance.py",
    }
)
REVIEW_HARDENING_ENVELOPES = frozenset(
    {
        frozenset(
            {
                "tests/desktop/test_desktop_app_check.py",
                "tests/desktop/test_ui_conformance.py",
                "tests/foundation/test_ui_change_gate.py",
                "tools/desktop_app_check.py",
                "tools/ui_change_gate.py",
                "tools/ui_conformance.py",
            }
        ),
        APPLICATION_INVENTORY_HARDENING_ENVELOPE,
        frozenset({"tests/foundation/test_ui_change_gate.py", "tools/ui_change_gate.py"}),
    }
)
REVIEW_RECORD_ENVELOPE = frozenset(
    {"docs/planning-implementation-plan.md", "planning/backlog.yaml", "planning/status-summary.md"}
)
AGENT_REVIEWER = re.compile(r"^agent:[a-z0-9](?:[a-z0-9_-]*[a-z0-9])?$")
IMPLEMENTATION_AGENT = re.compile(r"^(?:agent:)?[a-z0-9](?:[a-z0-9_-]*[a-z0-9])?$")
REVIEWED_HISTORICAL_HARDENING = {
    "1cd9deebe94fa2b667ad6b0030bd07ec45d1c6bb": {
        "taskId": "CAP-01.S04.T03",
        "paths": frozenset({"quality-scope.json"}),
        "evidencePath": "artifacts/evidence/CAP-01.S04.T03.review-fix-3.json",
        "evidenceSha256": "b762711c1903cf556195118c8fc3b14a34258fdcaa77464d87a10a65b79b6ed2",
        "approvalCommit": "43bcdec4eba110f994a540f0a1e625a6d44aff4b",
        "reviewer": "agent:curie",
    }
}


def canonical_agent_identity(value: object, *, reviewer: bool = False) -> str | None:
    if not isinstance(value, str):
        return None
    pattern = AGENT_REVIEWER if reviewer else IMPLEMENTATION_AGENT
    if pattern.fullmatch(value) is None:
        return None
    local_name = value.removeprefix("agent:")
    canonical = re.sub(r"[^a-z0-9]", "", local_name)
    return canonical or None


def maintenance_path_semantics_changed(repo: Path, predecessor: str, candidate: str, path: str) -> bool:
    try:
        before = blob(repo, predecessor, path)
        after = blob(repo, candidate, path)
    except ValueError:
        return True
    if before == after:
        return False
    if PurePosixPath(path).suffix == ".json":
        try:
            return json.loads(before.decode("utf-8")) != json.loads(after.decode("utf-8"))
        except UnicodeDecodeError, json.JSONDecodeError:
            return True
    return True


def backlog_tasks(backlog: dict[str, Any]) -> list[dict[str, Any]]:
    tasks = [
        task
        for capability in backlog.get("capabilities", [])
        if isinstance(capability, dict)
        for slice_item in capability.get("slices", [])
        if isinstance(slice_item, dict)
        for task in slice_item.get("tasks", [])
        if isinstance(task, dict)
    ]
    tasks.extend(
        task
        for amendment in backlog.get("wave_amendments", [])
        if isinstance(amendment, dict)
        for task in amendment.get("tasks", [])
        if isinstance(task, dict)
    )
    tasks.extend(
        task
        for wave in backlog.get("waves", [])
        if isinstance(wave, dict)
        for task in (wave.get("campaign") or {}).get("corrective_tasks", [])
        if isinstance(task, dict)
    )
    return tasks


def backlog_task(backlog: dict[str, Any], task_id: str) -> dict[str, Any] | None:
    matches = [task for task in backlog_tasks(backlog) if task.get("id") == task_id]
    return matches[0] if len(matches) == 1 else None


def independent_review_hardening_errors(
    backlog: dict[str, Any], previous_backlog: dict[str, Any], task_id: str, paths: set[str]
) -> list[str]:
    if frozenset(paths) not in REVIEW_HARDENING_ENVELOPES:
        return [
            "post-implementation gate hardening must match one exact canonical implementation-and-regression envelope"
        ]
    task = backlog_task(backlog, task_id)
    previous_task = backlog_task(previous_backlog, task_id)
    if task is None or previous_task is None:
        return ["post-implementation gate hardening requires one exact task in both review-transition backlogs"]
    review = task.get("review")
    previous_review = previous_task.get("review")
    reviewer = review.get("reviewer") if isinstance(review, dict) else None
    owner = task.get("owner")
    if (
        task.get("status") != "IN_PROGRESS"
        or not isinstance(review, dict)
        or review.get("result") != "changes-requested"
        or not isinstance(reviewer, str)
        or AGENT_REVIEWER.fullmatch(reviewer) is None
        or re.sub(r"[^a-z0-9]", "", reviewer.removeprefix("agent:")) == re.sub(r"[^a-z0-9]", "", str(owner).lower())
    ):
        return [
            "post-implementation gate hardening requires a canonical independent agent CHANGES_REQUESTED "
            "record in the commit's parent backlog"
        ]
    if (
        previous_task.get("status") != "REVIEW"
        or not isinstance(previous_review, dict)
        or not review.get("reviewed_at")
        or review.get("reviewed_at") == previous_review.get("reviewed_at")
        or task.get("updated_at") != review.get("reviewed_at")
    ):
        return [
            "post-implementation gate hardening requires its immediate parent to introduce a distinct "
            "REVIEW-to-IN_PROGRESS independent review transition"
        ]
    return []


def additive_preimplementation_quality_scope_errors(repo: Path, commit: str, policy: dict[str, Any]) -> list[str]:
    """Allow only additive, non-UI Python inventory introduced with its source.

    Retain the historical helper name, but apply this semantic boundary at every
    commit position. Adding a new regular services/tests/tools Python file to
    the inventory does not change UI authority. All other control changes still
    require independently reviewed gate maintenance.
    """

    paths = commit_paths(repo, commit)
    if paths & GATE_CONTROL_PATHS != {"quality-scope.json"}:
        return ["additive quality inventory may change only quality-scope.json among UI gate controls"]
    if any(is_implementation_path(path, policy) for path in paths):
        return ["additive quality inventory cannot share a commit with UI implementation"]
    try:
        if len(git(repo, "rev-list", "--parents", "-n", "1", commit).split()) != 2:
            return ["additive quality inventory requires an unambiguous single-parent commit"]
        parent = resolve_commit(repo, f"{commit}^")
        if tree_entry(repo, parent, "quality-scope.json") != tree_entry(repo, commit, "quality-scope.json"):
            return ["additive quality inventory may not change the inventory file mode or type"]
        for revision in (parent, commit):
            if tree_entry(repo, revision, "quality-scope.json") not in {("100644", "blob"), ("100755", "blob")}:
                return ["additive quality inventory requires regular quality-scope blobs"]
        before = json_object(blob(repo, parent, "quality-scope.json"), "parent quality scope")
        after = json_object(blob(repo, commit, "quality-scope.json"), "quality scope")
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        return [f"invalid additive quality inventory: {exc}"]
    if {key: value for key, value in before.items() if key != "pythonFiles"} != {
        key: value for key, value in after.items() if key != "pythonFiles"
    }:
        return ["additive quality inventory may not change quality-scope metadata or governed roots"]
    before_files = before.get("pythonFiles")
    after_files = after.get("pythonFiles")
    if (
        not isinstance(before_files, list)
        or not isinstance(after_files, list)
        or not all(isinstance(path, str) and path for path in before_files + after_files)
        or len(before_files) != len(set(before_files))
        or len(after_files) != len(set(after_files))
    ):
        return ["additive quality inventory requires unique non-empty Python file paths"]
    cursor = 0
    for path in after_files:
        if cursor < len(before_files) and path == before_files[cursor]:
            cursor += 1
    additions = set(after_files) - set(before_files)
    if cursor != len(before_files) or not additions or set(before_files) - set(after_files):
        return ["additive quality inventory must be strictly additive without reordering existing entries"]
    invalid = sorted(
        path
        for path in additions
        if path not in paths
        or not path.endswith(".py")
        or not path.startswith(("services/", "tests/", "tools/"))
        or any(part in {"", ".", ".."} for part in path.split("/"))
        or "\\" in path
        or path in GATE_CONTROL_PATHS
        or is_implementation_path(path, policy)
    )
    if invalid:
        return [
            "additive quality inventory requires canonical same-commit non-UI services/tests/tools Python files: "
            + invalid[0]
        ]
    for path in sorted(additions):
        if tree_entry(repo, parent, path) is not None or tree_entry(repo, commit, path) not in {
            ("100644", "blob"),
            ("100755", "blob"),
        }:
            return ["additive quality inventory source must be a newly added regular Git blob: " + path]
    return []


def adopted_continuation_quality_scope_errors(repo: Path, commit: str, policy: dict[str, Any]) -> list[str]:
    """Authenticate the one frozen T01 mixed inventory/product commit.

    This is deliberately separate from the reusable additive-inventory rule:
    that rule must continue to reject a quality-scope edit mixed with UI work.
    """

    try:
        if (
            commit != ADOPTED_CONTINUATION_MIXED_COMMIT
            or git(repo, "rev-parse", f"{commit}^{{tree}}").decode().strip() != ADOPTED_CONTINUATION_MIXED_TREE
        ):
            return ["adopted continuation mixed inventory is not the exact frozen T01 commit/tree"]
        if len(git(repo, "rev-list", "--parents", "-n", "1", commit).split()) != 2:
            return ["adopted continuation mixed inventory requires one parent"]
        parent = resolve_commit(repo, f"{commit}^")
        paths = commit_paths(repo, commit)
        if paths & GATE_CONTROL_PATHS != {"quality-scope.json"}:
            return ["adopted continuation mixed commit changed another gate control"]
        if {path for path in paths if is_implementation_path(path, policy)} != ADOPTED_CONTINUATION_MIXED_UI_PATHS:
            return ["adopted continuation mixed commit changed an unexpected governed renderer path"]
        if tree_entry(repo, parent, "quality-scope.json") != ("100644", "blob") or tree_entry(
            repo, commit, "quality-scope.json"
        ) != ("100644", "blob"):
            return ["adopted continuation quality inventory must remain a regular non-executable blob"]
        before = json_object(blob(repo, parent, "quality-scope.json"), "parent quality inventory")
        after = json_object(blob(repo, commit, "quality-scope.json"), "adopted continuation quality inventory")
        if {key: value for key, value in before.items() if key != "pythonFiles"} != {
            key: value for key, value in after.items() if key != "pythonFiles"
        }:
            return ["adopted continuation quality inventory changed metadata or governed roots"]
        prior_files, current_files = before.get("pythonFiles"), after.get("pythonFiles")
        if (
            not isinstance(prior_files, list)
            or not all(isinstance(path, str) and path for path in prior_files)
            or not isinstance(current_files, list)
            or current_files != [*prior_files, *ADOPTED_CONTINUATION_MIXED_PYTHON]
            or len(current_files) != len(set(current_files))
        ):
            return ["adopted continuation quality inventory must append exactly the nine frozen Python paths"]
        for path in ADOPTED_CONTINUATION_MIXED_PYTHON:
            if (
                path not in paths
                or not path.endswith(".py")
                or not path.startswith(("services/", "tests/", "tools/"))
                or canonical_path(path) != path
                or tree_entry(repo, parent, path) is not None
                or tree_entry(repo, commit, path) != ("100644", "blob")
            ):
                return ["adopted continuation Python source is not a canonical newly introduced regular blob: " + path]
        return []
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        return [f"invalid adopted continuation mixed inventory: {exc}"]


def reviewed_historical_hardening_errors(
    repo: Path, commit: str, head: str, task_id: str, paths: set[str]
) -> list[str]:
    record = REVIEWED_HISTORICAL_HARDENING.get(commit)
    if record is None:
        return ["post-implementation gate hardening has no exact reviewed historical attestation"]
    if record["taskId"] != task_id or record["paths"] != frozenset(paths) or commit_paths(repo, commit) != paths:
        return ["reviewed historical gate hardening identity or path scope differs from its exact attestation"]
    approval_commit = str(record["approvalCommit"])
    if (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", commit, approval_commit],
            cwd=repo,
            capture_output=True,
            check=False,
            timeout=30,
        ).returncode
        != 0
    ):
        return ["reviewed historical gate hardening is not ancestral to its approval commit"]
    if (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", approval_commit, head],
            cwd=repo,
            capture_output=True,
            check=False,
            timeout=30,
        ).returncode
        != 0
    ):
        return ["reviewed historical gate-hardening approval is not ancestral to the validated head"]
    evidence_path = str(record["evidencePath"])
    evidence_payload = blob(repo, approval_commit, evidence_path)
    if hashlib.sha256(evidence_payload).hexdigest() != record["evidenceSha256"]:
        return ["reviewed historical gate-hardening evidence differs from its exact attested hash"]
    try:
        evidence = json_object(evidence_payload, "reviewed historical gate-hardening evidence")
        backlog = yaml_object(blob(repo, approval_commit, "planning/backlog.yaml"), "approval backlog")
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError, yaml.YAMLError) as exc:
        return [f"invalid reviewed historical gate-hardening approval: {exc}"]
    task = backlog_task(backlog, task_id)
    if task is None:
        return ["reviewed historical gate hardening approval lacks the exact task"]
    review = task.get("review")
    attached = task.get("evidence")
    expected_attachment = {
        "path": evidence_path,
        "sha256": record["evidenceSha256"],
        "commit": evidence.get("commit"),
    }
    attachment_matches = any(
        isinstance(item, dict) and all(item.get(field) == value for field, value in expected_attachment.items())
        for item in attached or []
    )
    if (
        evidence.get("taskId") != task_id
        or paths.isdisjoint(set(evidence.get("changedFiles", [])))
        or not isinstance(review, dict)
        or task.get("status") != "DONE"
        or review.get("result") != "approved"
        or review.get("reviewer") != record["reviewer"]
        or not review.get("reviewed_at")
        or not attachment_matches
    ):
        return ["reviewed historical gate hardening lacks its exact independent approval and evidence attachment"]
    return []


def provenance_reference_handoff_errors(
    repo: Path,
    prior_review_commit: str,
    remediation_commit: str,
) -> list[str]:
    sequence = (
        git(
            repo,
            "rev-list",
            "--reverse",
            "--ancestry-path",
            f"{prior_review_commit}..{remediation_commit}",
        )
        .decode("ascii")
        .splitlines()
    )
    if len(sequence) != 3 or sequence[-1] != remediation_commit:
        return ["pre-UI gate maintenance remediation has an unauthorized intervening commit"]
    proposal_commit, approval_commit, _ = sequence
    if (
        resolve_commit(repo, f"{proposal_commit}^") != prior_review_commit
        or resolve_commit(repo, f"{approval_commit}^") != proposal_commit
        or resolve_commit(repo, f"{remediation_commit}^") != approval_commit
        or commit_paths(repo, proposal_commit) != PROVENANCE_REFERENCE_HANDOFF_PATHS
        or commit_paths(repo, approval_commit) != PROVENANCE_REFERENCE_HANDOFF_PATHS
    ):
        return ["pre-UI gate maintenance remediation has an invalid provenance-only reference handoff"]
    approval_path = "design/ui-reference/APPROVAL.yaml"
    manifest_path = "design/ui-reference/REFERENCE_MANIFEST.yaml"
    try:
        proposal = yaml_object(blob(repo, proposal_commit, approval_path), approval_path)
        proposal_manifest = yaml_object(blob(repo, proposal_commit, manifest_path), manifest_path)
        policy = json_object(blob(repo, approval_commit, "ui-change-policy.json"), "ui-change-policy.json")
        require_canonical_policy(policy)
        approved_state, state_errors = reference_state(repo, approval_commit, policy)
    except (KeyError, UnicodeDecodeError, ValueError, json.JSONDecodeError, yaml.YAMLError) as exc:
        return [f"pre-UI gate maintenance reference handoff is unreadable: {exc}"]
    if state_errors:
        return [f"pre-UI gate maintenance reference handoff is invalid: {state_errors[0]}"]
    approved = approved_state.get("approval")
    approved_manifest = approved_state.get("manifest")
    if not isinstance(approved, dict) or not isinstance(approved_manifest, dict):
        return ["pre-UI gate maintenance reference handoff lacks exact approved governance records"]
    authority = approved.get("authority")
    proposal_authority = proposal.get("authority")
    mutable_approval_fields = {
        "status",
        "approval_kind",
        "approved_by",
        "approved_at",
        "approval_basis",
        "authority",
    }
    proposal_stable_approval = {key: value for key, value in proposal.items() if key not in mutable_approval_fields}
    approved_stable_approval = {key: value for key, value in approved.items() if key not in mutable_approval_fields}
    stable_manifest = {key: value for key, value in approved_manifest.items() if key not in {"status", "file_hashes"}}
    proposal_stable_manifest = {
        key: value for key, value in proposal_manifest.items() if key not in {"status", "file_hashes"}
    }
    approved_hashes = approved_manifest.get("file_hashes")
    proposal_hashes = proposal_manifest.get("file_hashes")
    if (
        proposal.get("status") != "proposed"
        or proposal.get("approval_kind") != "pending-human"
        or proposal.get("approved_by") is not None
        or proposal.get("approved_at") is not None
        or proposal_manifest.get("status") != "proposed"
        or approved.get("status") != "approved"
        or approved.get("approval_kind") != "human"
        or not isinstance(approved.get("approved_by"), str)
        or HUMAN_ID.fullmatch(str(approved["approved_by"])) is None
        or not isinstance(authority, dict)
        or authority.get("proposal_commit") != proposal_commit
        or not isinstance(proposal_authority, dict)
        or proposal_authority != {key: value for key, value in authority.items() if key != "proposal_commit"}
        or proposal_stable_approval != approved_stable_approval
        or stable_manifest != proposal_stable_manifest
        or not isinstance(approved_hashes, dict)
        or not isinstance(proposal_hashes, dict)
        or {key: value for key, value in approved_hashes.items() if key != "APPROVAL.yaml"}
        != {key: value for key, value in proposal_hashes.items() if key != "APPROVAL.yaml"}
        or proposal_hashes.get("APPROVAL.yaml")
        != hashlib.sha256(canonical_payload("APPROVAL.yaml", blob(repo, proposal_commit, approval_path))).hexdigest()
    ):
        return ["pre-UI gate maintenance reference handoff is not an exact human-approved provenance-only transition"]
    return []


def reviewed_preimplementation_maintenance_errors(
    repo: Path,
    commit: str,
    head: str,
    paths: set[str],
    implementation_commit_ids: list[str],
) -> list[str]:
    root = "planning/governance-migrations"
    inventory = git(repo, "ls-tree", "-r", "--name-only", "-z", head, "--", root)
    record_paths = sorted(
        item.decode("utf-8")
        for item in inventory.split(b"\0")
        if re.fullmatch(rb"planning/governance-migrations/GOV-MAINT-[0-9]{4}\.json", item)
    )
    matches: list[tuple[str, dict[str, Any]]] = []
    for record_path in record_paths:
        try:
            record = json_object(blob(repo, head, record_path), record_path)
        except UnicodeDecodeError, ValueError, json.JSONDecodeError:
            continue
        attempts = record.get("reviewAttempts")
        if isinstance(attempts, list) and any(
            isinstance(attempt, dict) and attempt.get("reviewedCommit") == commit for attempt in attempts
        ):
            matches.append((record_path, record))
    if len(matches) != 1:
        return ["pre-UI gate maintenance lacks one exact adopted independent-review attestation"]
    record_path, record = matches[0]
    maintenance_id = PurePosixPath(record_path).stem
    attempts = record.get("reviewAttempts")
    review = record.get("review")
    implementer = record.get("implementationAgent")
    errors: list[str] = []
    if (
        record.get("maintenanceId") != maintenance_id
        or record.get("status") != "adopted"
        or record.get("riskTier") != 2
        or record.get("humanApprovalRequired") is not False
        or canonical_agent_identity(implementer) is None
        or not isinstance(attempts, list)
        or not attempts
        or not isinstance(review, dict)
        or review != attempts[-1]
        or review.get("disposition") != "APPROVED"
        or review.get("findings") != []
    ):
        errors.append("pre-UI gate maintenance record is not an exact authority-preserving independent approval")
        return errors
    try:
        first_attempt = attempts[0]
        if not isinstance(first_attempt, dict):
            raise ValueError("first review attempt is not an object")
        first_candidate = resolve_commit(repo, str(first_attempt.get("reviewedCommit")))
        candidate_record = json_object(blob(repo, first_candidate, record_path), "candidate maintenance record")
        predecessor = resolve_commit(repo, str((record.get("predecessor") or {}).get("commit")))
        if resolve_commit(repo, f"{first_candidate}^") != predecessor:
            errors.append("pre-UI gate maintenance candidate is not the direct child of its frozen predecessor")
        immutable_fields = {
            "schemaVersion",
            "documentType",
            "maintenanceId",
            "title",
            "riskTier",
            "humanApprovalRequired",
            "implementationAgent",
            "predecessor",
            "trigger",
            "authority",
            "intendedDelta",
            "rollback",
        }
        initial_changed_paths = (candidate_record.get("intendedDelta") or {}).get("changedPaths")
        if (
            candidate_record.get("status") != "candidate"
            or candidate_record.get("reviewAttempts") != []
            or candidate_record.get("review") is not None
            or any(candidate_record.get(field) != record.get(field) for field in immutable_fields)
            or initial_changed_paths != sorted(commit_paths(repo, first_candidate))
        ):
            errors.append("pre-UI gate maintenance candidate bytes or changed-path envelope differ from review")
        implementer_identity = canonical_agent_identity(implementer)
        prior_review_commit: str | None = None
        final_review_introduction: str | None = None
        open_findings: set[str] = set()
        authorized_intermediate_paths: set[str] = set()
        for index, attempt in enumerate(attempts, start=1):
            if not isinstance(attempt, dict):
                errors.append("pre-UI gate maintenance review attempt is not an object")
                continue
            review_id = f"{maintenance_id}.R{index:02d}"
            reviewed_commit = resolve_commit(repo, str(attempt.get("reviewedCommit")))
            reviewer = attempt.get("reviewer")
            reviewer_identity = canonical_agent_identity(reviewer, reviewer=True)
            disposition = attempt.get("disposition")
            finding_ids = attempt.get("findings")
            review_path = f"{root}/{maintenance_id}.review-R{index:02d}.json"
            if (
                attempt.get("reviewId") != review_id
                or attempt.get("path") != review_path
                or not isinstance(attempt.get("reviewedAt"), str)
                or not attempt.get("reviewedAt")
                or not isinstance(attempt.get("sha256"), str)
                or reviewer_identity is None
                or reviewer_identity == implementer_identity
                or disposition not in {"APPROVED", "CHANGES_REQUESTED"}
                or not isinstance(finding_ids, list)
                or not all(isinstance(item, str) and item for item in finding_ids)
                or len(finding_ids) != len(set(finding_ids))
                or (disposition == "APPROVED" and finding_ids)
                or (disposition == "CHANGES_REQUESTED" and not finding_ids)
                or (index < len(attempts) and disposition != "CHANGES_REQUESTED")
                or (index == len(attempts) and disposition != "APPROVED")
            ):
                errors.append("pre-UI gate maintenance review sequence is not canonical and independent")
                continue
            if prior_review_commit is not None and resolve_commit(repo, f"{reviewed_commit}^") != prior_review_commit:
                handoff_errors = provenance_reference_handoff_errors(repo, prior_review_commit, reviewed_commit)
                errors.extend(handoff_errors)
                if not handoff_errors:
                    authorized_intermediate_paths.update(PROVENANCE_REFERENCE_HANDOFF_PATHS)
            review_payload = blob(repo, head, review_path)
            if hashlib.sha256(review_payload).hexdigest() != attempt["sha256"]:
                errors.append("pre-UI gate maintenance review hash differs from its adopted record")
            review_record = json_object(review_payload, "pre-UI gate maintenance review")
            review_findings = review_record.get("findings")
            observed_finding_ids = [finding.get("id") for finding in review_findings or [] if isinstance(finding, dict)]
            expected_review_record = {
                "schemaVersion": "1.0",
                "documentType": "governance-control-maintenance-review",
                "maintenanceId": maintenance_id,
                "reviewId": review_id,
                "reviewedCommit": reviewed_commit,
                "reviewer": reviewer,
                "reviewedAt": attempt.get("reviewedAt"),
                "disposition": disposition,
                "authorityPreserved": disposition == "APPROVED",
                "candidateChangedPaths": sorted(commit_paths(repo, reviewed_commit)),
                "findings": review_findings,
            }
            if (
                review_record != expected_review_record
                or observed_finding_ids != finding_ids
                or len(observed_finding_ids) != len(set(observed_finding_ids))
            ):
                errors.append("pre-UI gate maintenance review is not the exact commit-bound disposition")
            introductions = (
                git(repo, "log", "--format=%H", "--diff-filter=A", head, "--", review_path).decode("ascii").splitlines()
            )
            if len(introductions) != 1:
                errors.append("pre-UI gate maintenance review lacks one immutable introduction commit")
                continue
            introduction = introductions[0]
            projection = json_object(blob(repo, introduction, record_path), "maintenance review projection")
            reviewed_record = json_object(blob(repo, reviewed_commit, record_path), "reviewed maintenance record")
            expected_status = "adopted" if disposition == "APPROVED" else "changes-requested"
            expected_review = attempt if disposition == "APPROVED" else None
            expected_projection = {
                **reviewed_record,
                "status": expected_status,
                "reviewAttempts": attempts[:index],
                "review": expected_review,
            }
            allowed_projections = [expected_projection]
            reviewed_remediation = reviewed_record.get("remediation")
            if disposition == "CHANGES_REQUESTED" and isinstance(reviewed_remediation, dict):
                allowed_projections.append(
                    {
                        **expected_projection,
                        "remediation": {
                            **reviewed_remediation,
                            "priorReviewId": review_id,
                            "priorReviewPath": review_path,
                            "priorReviewSha256": attempt.get("sha256"),
                        },
                    }
                )
            if (
                resolve_commit(repo, f"{introduction}^") != reviewed_commit
                or commit_paths(repo, introduction) != {record_path, review_path}
                or blob(repo, introduction, review_path) != review_payload
                or projection not in allowed_projections
                or any(not is_ancestor(repo, introduction, item) for item in implementation_commit_ids)
            ):
                errors.append("pre-UI gate maintenance review projection or ordering is invalid")
            if disposition == "CHANGES_REQUESTED":
                open_findings.update(str(item) for item in finding_ids)
            prior_review_commit = introduction
            final_review_introduction = introduction
        final_candidate = resolve_commit(repo, str(attempts[-1].get("reviewedCommit")))
        maintenance_evidence_paths = {record_path} | {
            f"{root}/{maintenance_id}.review-R{index:02d}.json" for index in range(1, len(attempts) + 1)
        }
        historical_control_paths: set[str] = set()
        try:
            cutover = resolve_commit(repo, MAINTENANCE_CONTROL_ENVELOPE_CUTOVER)
            if (
                final_review_introduction is not None
                and final_review_introduction != cutover
                and is_ancestor(repo, final_review_introduction, cutover)
                and isinstance(initial_changed_paths, list)
            ):
                historical_control_paths = {str(path) for path in initial_changed_paths}
        except ValueError:
            pass
        maintenance_control_paths = MAINTENANCE_CONTROL_PATHS | historical_control_paths | maintenance_evidence_paths
        net_non_control_paths = sorted(
            path
            for path in changed_paths(repo, predecessor, final_candidate)
            if path not in maintenance_control_paths
            and path not in authorized_intermediate_paths
            and maintenance_path_semantics_changed(repo, predecessor, final_candidate, path)
        )
        if net_non_control_paths:
            errors.append(
                "pre-UI gate maintenance must be control-only and cannot retain product paths: "
                + net_non_control_paths[0]
            )
        if final_review_introduction is None or blob(repo, head, record_path) != blob(
            repo, final_review_introduction, record_path
        ):
            errors.append("pre-UI gate maintenance adopted record changed after its final review")
        remediation = record.get("remediation")
        if open_findings and (
            not isinstance(remediation, dict)
            or set(remediation.get("resolvedFindingIds") or []) != open_findings
            or not all(remediation.get(field) for field in ("rootCause", "resolution", "recurrenceControl"))
        ):
            errors.append("pre-UI gate maintenance remediation does not close every adverse finding")
    except (KeyError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(f"invalid pre-UI gate maintenance provenance: {exc}")
    return errors


def maintenance_proposed_adr_paths(repo: Path, predecessor: str, candidate: str) -> set[str]:
    """Admit documentary association only inside an authenticated maintenance chain.

    Proposed records confer no architecture authority. Prior decisions, registry
    entries and the ordinary correction path policy remain immutable.
    """
    sequence = git(repo, "rev-list", "--reverse", f"{predecessor}..{candidate}").decode().splitlines()
    touches = {
        commit: {path for path in commit_paths(repo, commit) if path.startswith("docs/adr/")} for commit in sequence
    }
    touches = {commit: paths for commit, paths in touches.items() if paths}
    if not touches:
        return set()
    if len(touches) != 1:
        raise ValueError("associated ADR and registry must have one immutable joint introduction")
    introduction, paths = next(iter(touches.items()))
    index_path = "docs/adr/index.json"
    records = paths - {index_path}
    if index_path not in paths or len(records) != 1:
        raise ValueError("maintenance may associate only one new Proposed ADR and its index entry")
    path = next(iter(records))
    if re.fullmatch(r"docs/adr/ADR-[0-9]{4}-[a-z0-9]+(?:-[a-z0-9]+)*\.md", path) is None:
        raise ValueError("associated ADR path is not canonical")
    parents = git(repo, "rev-list", "--parents", "-n", "1", introduction).decode().split()
    if (
        len(parents) != 2
        or tree_entry(repo, predecessor, path) is not None
        or tree_entry(repo, parents[1], path) is not None
        or any(tree_entry(repo, introduction, item) != ("100644", "blob") for item in paths)
        or tree_entry(repo, predecessor, index_path) != ("100644", "blob")
    ):
        raise ValueError("associated ADR requires new regular non-executable bytes in a sole-parent commit")
    before = json_object(blob(repo, predecessor, index_path), "prior ADR index")
    after = json_object(blob(repo, candidate, index_path), "associated ADR index")
    prior, current = before.get("records"), after.get("records")
    if (
        not isinstance(prior, list)
        or not isinstance(current, list)
        or len(current) != len(prior) + 1
        or current[:-1] != prior
        or {key: value for key, value in before.items() if key != "records"}
        != {key: value for key, value in after.items() if key != "records"}
    ):
        raise ValueError("associated ADR index must append one entry without altering prior order or metadata")
    text = blob(repo, candidate, path).decode("utf-8")
    parts = text.split("---", 2)
    if len(parts) != 3 or parts[0].strip():
        raise ValueError("associated ADR lacks canonical front matter")
    metadata = yaml.safe_load(parts[1])
    required = {
        "id",
        "title",
        "status",
        "date",
        "deciders",
        "linked_tasks",
        "decision_scope",
        "affected_paths",
        "supersedes",
        "superseded_by",
    }
    if (
        not isinstance(metadata, dict)
        or set(metadata) != required
        or metadata["status"] != "Proposed"
        or metadata["deciders"] != []
        or metadata["supersedes"] != []
        or metadata["superseded_by"] is not None
        or not isinstance(metadata["title"], str)
        or not metadata["title"]
        or not isinstance(metadata["decision_scope"], str)
        or not metadata["decision_scope"]
        or re.fullmatch(r"ADR-[0-9]{4}", str(metadata["id"])) is None
        or not path.startswith(f"docs/adr/{metadata['id']}-")
        or any(not isinstance(item, dict) or item.get("id") == metadata["id"] for item in prior)
    ):
        raise ValueError("associated ADR must be a new Proposed record without decision authority")
    date.fromisoformat(str(metadata["date"]))
    expected = {
        "id": metadata["id"],
        "path": path,
        "title": metadata["title"],
        "status": "Proposed",
        "linkedTasks": metadata["linked_tasks"],
    }
    slug = re.sub(r"[^a-z0-9]+", "-", metadata["title"].lower()).strip("-")
    if (
        path != f"docs/adr/{metadata['id']}-{slug}.md"
        or current[-1] != expected
        or any(
            f"## {section}" not in parts[2].splitlines()
            for section in ("Context", "Candidates", "Decision", "Consequences", "Verification", "Task links")
        )
    ):
        raise ValueError("associated ADR must match its indexed identity and contain all review sections")
    data = yaml_object(blob(repo, predecessor, "planning/backlog.yaml"), "maintenance predecessor backlog")
    ordinary_ids = {
        task["id"]
        for capability in data.get("capabilities", [])
        for slice_ in capability.get("slices", [])
        for task in slice_.get("tasks", [])
    }
    links = metadata["linked_tasks"]
    if (
        not isinstance(links, list)
        or not links
        or any(not isinstance(item, str) for item in links)
        or (len(links) != len(set(links)) or set(links) - ordinary_ids)
    ):
        raise ValueError("associated ADR must link existing ordinary tasks")
    actual = set(changed_paths(repo, predecessor, candidate)) & LEGACY_GOVERNANCE_CONTROL_PATHS
    corrections = [
        task for task in backlog_tasks(data) if task.get("correction") and task.get("status") == "IN_PROGRESS"
    ]
    if len(corrections) > 1:
        raise ValueError("associated ADR cannot select among competing corrections")
    if corrections:
        correction = corrections[0]
        if correction["correction"]["origin_task_id"] not in links or not is_ancestor(
            repo, correction["base_sha"], predecessor
        ):
            raise ValueError("associated ADR must link the active correction's exact origin")
        actual.update(
            set(changed_paths(repo, correction["base_sha"], predecessor))
            & set(correction["correction"]["changed_paths"])
        )
    policy = json_object(blob(repo, predecessor, "architecture-protected-paths.json"), "protected path policy")
    protected = {item for item in actual if any(fnmatch.fnmatchcase(item, rule["pattern"]) for rule in policy["paths"])}
    affected = metadata["affected_paths"]
    if (
        not isinstance(affected, list)
        or not affected
        or any(
            not isinstance(item, str)
            or re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+", item) is None
            or any(part in {".", ".."} for part in item.split("/"))
            for item in affected
        )
        or len(affected) != len(set(affected))
        or set(affected) - protected
    ):
        raise ValueError("associated ADR affected paths must be exact actually changed protected interfaces")
    return paths


def legacy_control_maintenance_errors(
    repo: Path, commit: str, head: str, cutoff: str, *, authenticated: dict[str, set[str]] | None = None
) -> list[str]:
    """Read the existing pre-correction maintenance protocol, without inventing adoption.

    Only filename-qualified review records are discovered. Their immutable
    candidate/evidence/review chain must already precede the authenticated
    correction task boundary; this cannot approve new resumed-task changes.
    """
    try:
        inventory = git(repo, "ls-tree", "-r", "--name-only", "-z", head, "--", "artifacts/evidence")
        candidates = []
        for name in inventory.split(b"\0"):
            if not re.fullmatch(rb"artifacts/evidence/[A-Za-z0-9_-]+\.review-[0-9]{2}\.json", name):
                continue
            path = name.decode("ascii")
            if tree_entry(repo, head, path) != ("100644", "blob"):
                continue
            record = json_object(blob(repo, head, path), "historical maintenance review")
            if (
                record.get("documentType") == "bounded-governance-maintenance-independent-review"
                and record.get("reviewedCommit") == commit
            ):
                candidates.append(path)
        if len(candidates) != 1:
            return ["historical control maintenance lacks one exact independent review"]
        review_path = candidates[0]
        review, introduction = immutable_record(repo, head, review_path)
        independence = review.get("independence") or {}
        implementer = independence.get("implementer")
        if (
            review.get("schemaVersion") != "1.0"
            or review.get("reviewId") != PurePosixPath(review_path).stem
            or review.get("disposition") != "ACCEPTED"
            or review.get("findings") != []
            or not review.get("reviewedAt")
            or independence.get("implementationAuthoredByReviewer") is not False
            or not isinstance(implementer, str)
            or AGENT_ID.fullmatch(implementer) is None
            or not independent_identity(review.get("reviewer"), implementer)
            or not is_ancestor(repo, introduction, cutoff)
            or not is_ancestor(repo, cutoff, head)
        ):
            return ["historical control maintenance lacks independent accepted pre-correction authority"]
        reference = review["evidence"]
        evidence_path = str(reference["path"])
        stem = review_path.rsplit(".review-", 1)[0]
        if not re.fullmatch(re.escape(stem) + r"\.evidence-[0-9]{2}\.json", evidence_path):
            return ["historical control maintenance evidence namespace differs"]
        evidence, delivery = immutable_record(repo, head, evidence_path, reference["sha256"])
        predecessor = review["predecessorCommit"]
        for child, parent in ((delivery, commit), (introduction, delivery)):
            if git(repo, "rev-list", "--parents", "-n", "1", child).decode().split() != [child, parent]:
                return ["historical control maintenance requires sole-parent candidate/evidence/review delivery"]
        if (
            reference.get("introductionCommit") != delivery
            or git(repo, "rev-parse", f"{delivery}:{evidence_path}").decode().strip() != reference.get("gitBlob")
            or commit_paths(repo, delivery) != {evidence_path}
            or commit_paths(repo, introduction) != {review_path}
            or evidence.get("schemaVersion") != "1.0"
            or evidence.get("documentType") != "bounded-governance-maintenance-evidence"
            or evidence.get("candidateCommit") != commit
            or evidence.get("predecessorCommit") != predecessor
            or evidence.get("implementer") != implementer
            or type(evidence.get("riskTier")) is not int
            or evidence.get("riskTier") != 2
            or evidence.get("selectedChecksStatus") != "PASS"
        ):
            return ["historical control maintenance evidence identity or delivery differs"]
        contract_path = str(evidence.get("contract"))
        if not re.fullmatch(re.escape(stem) + r"\.maintenance-[0-9]{2}\.md", contract_path):
            return ["historical control maintenance contract namespace differs"]
        associated_adr_paths = maintenance_proposed_adr_paths(repo, predecessor, commit)
        control_paths = LEGACY_GOVERNANCE_CONTROL_PATHS | associated_adr_paths
        source_paths = {commit: commit_paths(repo, commit)}
        if "sourceCommits" in evidence or "sourceCommits" in review:
            rows = evidence.get("sourceCommits")
            sequence = git(repo, "rev-list", "--reverse", f"{predecessor}..{commit}").decode().splitlines()
            if (
                not isinstance(rows, list)
                or not rows
                or len(rows) > 64
                or rows != review.get("sourceCommits")
                or [row.get("commit") for row in rows if isinstance(row, dict)] != sequence
                or len(rows) != len(sequence)
                or sequence[-1] != commit
            ):
                return ["maintenance source sequence differs from the exact reviewed Git range"]
            source_paths = {}
            parent = predecessor
            for row in rows:
                source = row["commit"]
                paths = commit_paths(repo, source)
                if (
                    set(row) != {"commit", "changedFiles"}
                    or git(repo, "rev-list", "--parents", "-n", "1", source).decode().split() != [source, parent]
                    or paths - (control_paths | {contract_path})
                ):
                    return ["maintenance source sequence is not linear and control-only"]
                bindings = row["changedFiles"]
                if (
                    not isinstance(bindings, list)
                    or [item.get("path") for item in bindings if isinstance(item, dict)] != sorted(paths)
                    or len(bindings) != len(paths)
                ):
                    return ["maintenance intermediate source inventory differs"]
                for item in bindings:
                    path = item["path"]
                    if (
                        set(item) != {"path", "gitBlob", "sha256"}
                        or tree_entry(repo, source, path) not in {("100644", "blob"), ("100755", "blob")}
                        or git(repo, "rev-parse", f"{source}:{path}").decode().strip() != item["gitBlob"]
                        or hashlib.sha256(blob(repo, source, path)).hexdigest() != item["sha256"]
                    ):
                        return ["maintenance intermediate source binding differs"]
                source_paths[source] = paths
                parent = source
        elif git(repo, "rev-list", "--parents", "-n", "1", commit).decode().split() != [commit, predecessor]:
            return ["historical control maintenance requires sole-parent candidate/evidence/review delivery"]
        paths = set().union(*source_paths.values())
        if contract_path not in paths or paths - (control_paths | {contract_path}):
            return ["historical control maintenance must remain control-only"]
        artifacts, declared = review.get("reviewedArtifacts"), evidence.get("changedFiles")
        if not isinstance(artifacts, list) or not isinstance(declared, list):
            return ["historical control maintenance requires exact source inventories"]
        for inventory_rows, blob_key in ((artifacts, "gitBlob"), (declared, "blob")):
            names = [row.get("path") for row in inventory_rows if isinstance(row, dict)]
            if len(names) != len(inventory_rows) or len(names) != len(paths) or set(names) != paths:
                return ["historical control maintenance source inventory differs from its candidate"]
            for row in inventory_rows:
                path = row["path"]
                if tree_entry(repo, commit, path) not in {("100644", "blob"), ("100755", "blob")}:
                    return ["historical control maintenance source is not a regular Git blob"]
                payload = blob(repo, commit, path)
                if git(repo, "rev-parse", f"{commit}:{path}").decode().strip() != row.get(blob_key) or hashlib.sha256(
                    payload
                ).hexdigest() != row.get("sha256"):
                    return ["historical control maintenance source binding differs"]
        if authenticated is not None:
            authenticated.update({**source_paths, delivery: {evidence_path}, introduction: {review_path}})
        return []
    except (KeyError, TypeError, ValueError, UnicodeError, json.JSONDecodeError, yaml.YAMLError) as exc:
        return [f"invalid historical control maintenance: {exc}"]


def reviewed_control_maintenance_commits(repo: Path, base: str, head: str) -> dict[str, set[str]]:
    """Exact reviewed control-only chains; never a reusable filename allowance.

    The caller authenticates correction authority separately. Historical callers
    of the legacy validator retain their original pre-correction cutoff.
    """
    commits = git(repo, "rev-list", f"{base}..{head}").decode().splitlines()
    admitted: dict[str, set[str]] = {}
    for commit in commits:
        if not commit_paths(repo, commit) & LEGACY_GOVERNANCE_CONTROL_PATHS:
            continue
        chain: dict[str, set[str]] = {}
        if legacy_control_maintenance_errors(repo, commit, head, head, authenticated=chain):
            continue
        if set(chain) - set(commits) or set(chain) & set(admitted):
            raise ValueError("control maintenance chain is outside the correction range or overlaps another chain")
        admitted.update(chain)
    return admitted


def corrective_path_admitted(task: dict[str, Any], path: object) -> bool:
    if not isinstance(path, str):
        return False
    delivery = {
        "planning/backlog.yaml",
        "docs/planning-implementation-plan.md",
        "planning/status-summary.md",
        "planning/review-site/index.html",
        "planning/review-site/manifest.json",
        f"planning/review-site/waves/{task['wave']}.html",
    }
    if corrective_ui_paths(task):
        delivery.add(f"artifacts/evidence/ui-change/{task['id']}.json")
    return path in set(task["correction"]["changed_paths"]) | delivery or path.startswith(
        f"artifacts/evidence/{task['id']}."
    )


def corrective_interruption_note(task: dict[str, Any], path: object) -> bool:
    """A non-authoritative handoff namespace, requiring separate Git admission."""
    if not isinstance(path, str):
        return False
    match = re.fullmatch(rf"artifacts/evidence/{re.escape(str(task['wave']))}\.resume-(\d{{8}})-[0-9]{{2}}\.md", path)
    if match is None:
        return False
    try:
        date.fromisoformat(match[1])
    except ValueError:
        return False
    return True


def immutable_interruption_notes(repo: Path, task: dict[str, Any], paths_by_commit: dict[str, set[str]]) -> set[str]:
    notes = {path for paths in paths_by_commit.values() for path in paths if corrective_interruption_note(task, path)}
    for path in notes:
        touches = [commit for commit, paths in paths_by_commit.items() if path in paths]
        if len(touches) != 1:
            raise ValueError("interruption notes must be immutable additions")
        commit = touches[0]
        lineage = git(repo, "rev-list", "--parents", "-n", "1", commit).decode().split()
        if (
            len(lineage) != 2
            or tree_entry(repo, lineage[1], path) is not None
            or tree_entry(repo, commit, path) != ("100644", "blob")
        ):
            raise ValueError("interruption notes must add regular non-executable Markdown blobs")
    return notes


def corrective_scope_errors(
    repo: Path, task: dict[str, Any], candidate: str, declared: list[object] | None = None
) -> list[str]:
    """Shared UI/submission boundary: full history, not just net filenames."""
    try:
        base = task["base_sha"]
        paths_by_commit = {
            commit: commit_paths(repo, commit)
            for commit in git(repo, "rev-list", f"{base}..{candidate}").decode().splitlines()
        }
        notes = immutable_interruption_notes(repo, task, paths_by_commit)
        extra_commits = {
            commit: paths
            for commit, paths in paths_by_commit.items()
            if any(not corrective_path_admitted(task, path) and path not in notes for path in paths)
        }
        extra = [path for path in (declared or []) if not corrective_path_admitted(task, path) and path not in notes]
        if not extra_commits and not extra:
            return []
        maintenance = reviewed_control_maintenance_commits(repo, base, candidate)
        if any(maintenance.get(commit) != paths for commit, paths in extra_commits.items()):
            raise ValueError("out-of-scope commit lacks exact independent control-only review")
        covered = {path for paths in maintenance.values() for path in paths}
        if any(not isinstance(path, str) or path not in covered for path in extra):
            raise ValueError("extra changedFiles are not reviewed maintenance delivery")
        return []
    except (KeyError, TypeError, ValueError, UnicodeError) as exc:
        return [f"corrective changedFiles exceeds the exact admitted scope: {exc}"]


def inherited_control_commits(
    repo: Path, base: str, head: str, scope: dict[str, Any], policy: dict[str, Any]
) -> tuple[set[str], str]:
    """Classify only internally authenticated correction ranges, not contract declarations."""
    ranges = scope["correctionSubmissionRanges"]
    activation = scope["reactivationCommit"]
    # Reuse the exact linear, no-hidden-path, original-range boundary.
    restoration_segments(repo, base, head, activation, ranges, policy)
    commits = [base, *git(repo, "rev-list", "--reverse", f"{base}..{head}").decode().splitlines()]
    positions = {commit: index for index, commit in enumerate(commits)}
    if not ranges:
        raise ValueError("inherited controls require authenticated correction submissions")
    cutoff = min((item["base"] for item in ranges), key=positions.__getitem__)
    admitted: set[str] = set()
    for commit in commits[1:]:
        paths = commit_paths(repo, commit)
        if not paths & GATE_CONTROL_PATHS:
            continue
        matches = [
            item for item in ranges if positions[item["base"]] < positions[commit] <= positions[item["candidate"]]
        ]
        if len(matches) > 1 or (matches and not paths.issubset(matches[0]["paths"])):
            raise ValueError("inherited control commit has overlapping authority or unreviewed extra paths")
        if matches:
            admitted.add(commit)
    return admitted, cutoff


def application_activation_errors(
    repo: Path,
    base: str,
    head: str,
    protected_changes: list[str],
    contract: dict[str, Any],
    policy: dict[str, Any],
    *,
    resumed_scope: dict[str, Any] | None = None,
) -> list[str]:
    errors: list[str] = []
    if contract.get("changeKind") != "approved-reference-implementation" and not (
        contract.get("schemaVersion") == "1.1"
        and contract.get("changeKind") == "defect-restoration"
        and isinstance(contract.get("amendmentAuthority"), dict)
    ):
        return ["UI implementation cannot change its own design-first gate controls in the same range"]
    inherited: set[str] = set()
    cutoff: str | None = None
    if resumed_scope is not None:
        try:
            inherited, cutoff = inherited_control_commits(repo, base, head, resumed_scope, policy)
        except (KeyError, TypeError, ValueError) as exc:
            return [f"invalid inherited correction control authority: {exc}"]
    commits = git(repo, "rev-list", "--reverse", "--topo-order", f"{base}..{head}").decode("ascii").splitlines()
    protected_positions: list[int] = []
    implementation_positions: list[int] = []
    paths_by_position: dict[int, set[str]] = {}
    for position, commit in enumerate(commits):
        paths = commit_paths(repo, commit)
        paths_by_position[position] = paths
        if paths & GATE_CONTROL_PATHS:
            protected_positions.append(position)
        if any(is_implementation_path(path, policy) for path in paths):
            implementation_positions.append(position)
    first_implementation = min(implementation_positions) if implementation_positions else None
    implementation_commit_ids = [commits[position] for position in implementation_positions]
    late_protected = (
        [position for position in protected_positions if position >= first_implementation]
        if first_implementation is not None
        else []
    )
    activation_positions = [position for position in protected_positions if position not in late_protected]
    activation_errors: list[str] = []
    for position in activation_positions:
        if commits[position] in inherited:
            continue
        if cutoff is not None and not legacy_control_maintenance_errors(repo, commits[position], head, cutoff):
            continue
        quality_errors = additive_preimplementation_quality_scope_errors(repo, commits[position], policy)
        if quality_errors:
            maintenance_errors = reviewed_preimplementation_maintenance_errors(
                repo,
                commits[position],
                head,
                paths_by_position[position],
                implementation_commit_ids,
            )
            if maintenance_errors:
                activation_errors.extend(quality_errors)
                activation_errors.extend(maintenance_errors)
    if late_protected:
        for position in late_protected:
            if commits[position] in inherited:
                continue
            if cutoff is not None and not legacy_control_maintenance_errors(repo, commits[position], head, cutoff):
                continue
            if not additive_preimplementation_quality_scope_errors(repo, commits[position], policy):
                continue
            maintenance_errors = reviewed_preimplementation_maintenance_errors(
                repo,
                commits[position],
                head,
                paths_by_position[position],
                [],
            )
            if not maintenance_errors:
                continue
            try:
                parent = resolve_commit(repo, f"{commits[position]}^")
                if commit_paths(repo, parent) != REVIEW_RECORD_ENVELOPE:
                    raise ValueError("immediate parent is not the exact planning-only review-record commit")
                grandparent = resolve_commit(repo, f"{parent}^")
                backlog = yaml_object(blob(repo, parent, "planning/backlog.yaml"), "parent backlog")
                previous_backlog = yaml_object(
                    blob(repo, grandparent, "planning/backlog.yaml"), "pre-review parent backlog"
                )
                hardening_errors = independent_review_hardening_errors(
                    backlog, previous_backlog, str(contract.get("taskId")), paths_by_position[position]
                )
                if hardening_errors and commits[position] in REVIEWED_HISTORICAL_HARDENING:
                    hardening_errors = reviewed_historical_hardening_errors(
                        repo,
                        commits[position],
                        head,
                        str(contract.get("taskId")),
                        paths_by_position[position],
                    )
                if hardening_errors:
                    errors.extend(maintenance_errors)
                    errors.extend(hardening_errors)
            except (UnicodeDecodeError, ValueError, yaml.YAMLError) as exc:
                errors.extend(maintenance_errors)
                errors.append(f"invalid post-implementation gate-hardening provenance: {exc}")
    if resumed_scope is None and set(protected_changes) == APPLICATION_ACTIVATION_PATHS:
        try:
            base_activation = json_object(
                blob(repo, base, "verification/extensions/desktop-ui.json"), "base desktop UI activation"
            )
            head_activation = json_object(
                blob(repo, head, "verification/extensions/desktop-ui.json"), "desktop UI activation"
            )
        except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"invalid first-application activation: {exc}")
            return errors
        expected_head = dict(base_activation)
        expected_head.update(
            {
                "mode": "approved-reference-application",
                "targetRoot": "apps/desktop/dist",
                "applicationRoot": "apps/desktop",
                "applicationManifestPath": "apps/desktop/dist/application-manifest.json",
            }
        )
        if base_activation.get("mode") != "approved-reference-fixture" or base_activation.get("targetRoot") != str(
            policy["referenceRoot"]
        ):
            errors.append("first-application activation requires the governed fixture mode at the task base")
        if head_activation != expected_head:
            errors.append(
                "first-application activation may only retarget the unchanged approved reference to the desktop build"
            )
        invalid_order = (
            not activation_positions
            or not implementation_positions
            or max(activation_positions) >= min(implementation_positions)
        )
        if invalid_order:
            errors.append("first-application gate activation must be committed before every UI implementation commit")
    elif len(late_protected) + len(activation_positions) != len(protected_positions) or activation_errors or errors:
        errors.extend(activation_errors)
        errors.append(
            "UI implementation cannot change its own design-first gate controls without an exact independently "
            "reviewed post-implementation hardening commit"
        )
    return errors


def git(repo: Path, *args: str, allowed: tuple[int, ...] = (0,)) -> bytes:
    completed = subprocess.run(["git", *args], cwd=repo, capture_output=True, check=False, timeout=30)
    if completed.returncode not in allowed:
        message = completed.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(f"git {' '.join(args)} failed: {message or completed.returncode}")
    return completed.stdout


def resolve_commit(repo: Path, value: str) -> str:
    resolved = git(repo, "rev-parse", "--verify", "--end-of-options", f"{value}^{{commit}}")
    commit = resolved.decode("ascii").strip()
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError(f"Git reference did not resolve to a full commit: {value!r}")
    return commit


def canonical_path(value: str) -> str:
    pure = PurePosixPath(value)
    if not value or value.startswith("/") or "\\" in value or any(part in {"", ".", ".."} for part in pure.parts):
        raise ValueError(f"noncanonical repository path: {value!r}")
    return pure.as_posix()


def blob(repo: Path, commit: str, path: str) -> bytes:
    canonical = canonical_path(path)
    return git(repo, "cat-file", "blob", f"{commit}:{canonical}")


def json_object(payload: bytes, name: str) -> dict[str, Any]:
    loaded = json.loads(payload.decode("utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{name} must contain a JSON object")
    return loaded


def require_canonical_policy(policy: dict[str, Any]) -> None:
    for field, scalar_expected in EXPECTED_POLICY_SCALARS.items():
        if policy.get(field) != scalar_expected:
            raise ValueError(f"ui-change-policy {field} must equal {scalar_expected!r}")
    expected_sets: dict[str, set[str]] = {
        "implementationRoots": EXPECTED_IMPLEMENTATION_ROOTS,
        "implementationExtensions": EXPECTED_IMPLEMENTATION_EXTENSIONS,
        "ignoredImplementationSuffixes": EXPECTED_IGNORED_SUFFIXES,
    }
    for field, expected in expected_sets.items():
        raw = policy.get(field)
        if not isinstance(raw, list) or any(not isinstance(item, str) for item in raw) or set(raw) != expected:
            raise ValueError(f"ui-change-policy {field} must equal the canonical inventory")


def yaml_object(payload: bytes, name: str) -> dict[str, Any]:
    loaded = yaml.safe_load(payload.decode("utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{name} must contain a YAML mapping")
    return loaded


def changed_paths(repo: Path, base: str, head: str) -> set[str]:
    fields = git(repo, "diff", "--name-status", "-z", "--find-renames", "--find-copies", base, head, "--").split(b"\0")
    paths: set[str] = set()
    index = 0
    while index < len(fields) and fields[index]:
        status = fields[index].decode("ascii", errors="replace")
        index += 1
        count = 2 if status[:1] in {"R", "C"} else 1
        if index + count > len(fields):
            raise ValueError("Git returned a truncated name-status record")
        for raw in fields[index : index + count]:
            paths.add(canonical_path(raw.decode("utf-8")))
        index += count
    return paths


def tree_entry(repo: Path, commit: str, path: str) -> tuple[str, str] | None:
    canonical = canonical_path(path)
    records = [
        record for record in git(repo, "ls-tree", "-z", "--full-tree", commit, "--", canonical).split(b"\0") if record
    ]
    if not records:
        return None
    if len(records) != 1:
        raise ValueError(f"Git returned multiple tree entries for {canonical}")
    metadata, separator, raw_path = records[0].partition(b"\t")
    parts = metadata.decode("ascii", errors="replace").split()
    observed_path = raw_path.decode("utf-8") if separator else ""
    if len(parts) != 3 or observed_path != canonical:
        raise ValueError(f"Git returned a malformed tree entry for {canonical}")
    mode, kind, _ = parts
    return mode, kind


def implementation_object_errors(repo: Path, base: str, head: str, paths: list[str]) -> list[str]:
    errors: list[str] = []
    for path in paths:
        observed = 0
        for label, commit in (("base", base), ("head", head)):
            entry = tree_entry(repo, commit, path)
            if entry is None:
                continue
            observed += 1
            mode, kind = entry
            if kind != "blob" or mode not in {"100644", "100755"}:
                errors.append(
                    f"governed UI implementation path must be a regular Git blob at {label}: {path} ({mode} {kind})"
                )
        if observed == 0:
            errors.append(f"governed UI implementation path is absent from both base and head: {path}")
    return errors


def is_ancestor(repo: Path, ancestor: str, descendant: str) -> bool:
    completed = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=repo,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if completed.returncode not in {0, 1}:
        raise ValueError(completed.stderr.decode("utf-8", errors="replace").strip() or "git merge-base failed")
    return completed.returncode == 0


def is_implementation_path(path: str, policy: dict[str, Any]) -> bool:
    roots = policy.get("implementationRoots")
    extensions = policy.get("implementationExtensions")
    ignored = policy.get("ignoredImplementationSuffixes")
    if not isinstance(roots, list) or not isinstance(extensions, list) or not isinstance(ignored, list):
        raise ValueError("ui-change-policy implementation path fields must be arrays")
    inside = any(path == root or path.startswith(f"{root}/") for root in roots if isinstance(root, str))
    return (
        inside
        and any(path.endswith(extension) for extension in extensions if isinstance(extension, str))
        and not any(path.endswith(suffix) for suffix in ignored if isinstance(suffix, str))
    )


def corrective_ui_paths(task: dict[str, Any]) -> set[str]:
    """Classify admitted paths using the same non-configurable UI gate policy."""
    correction = task.get("correction")
    if not isinstance(correction, dict) or LINKED_CORRECTION_ID.fullmatch(str(task.get("id"))) is None:
        return set()
    paths = correction.get("changed_paths")
    if not isinstance(paths, list):
        return set()
    policy = {
        "implementationRoots": sorted(EXPECTED_IMPLEMENTATION_ROOTS),
        "implementationExtensions": sorted(EXPECTED_IMPLEMENTATION_EXTENSIONS),
        "ignoredImplementationSuffixes": sorted(EXPECTED_IGNORED_SUFFIXES),
    }
    return {path for path in paths if isinstance(path, str) and is_implementation_path(path, policy)}


def linked_correction_admission(
    repo: Path, base: str, head: str, backlog: dict[str, Any], task: dict[str, Any]
) -> dict[str, Any]:
    """Consume taskctl's existing admission, never synthesize experience authority."""
    import taskctl

    if head != resolve_commit(repo, "HEAD"):
        raise ValueError("linked correction UI authority requires current HEAD")
    if not any(task is item for item in taskctl.corrective_tasks(backlog)):
        raise ValueError("linked correction must be an admitted campaign corrective task")
    if "experience_change" in task or "review_gate" in task:
        raise ValueError("linked correction cannot introduce or borrow experience/review metadata")
    if task.get("status") not in {"IN_PROGRESS", "REVIEW"} or task.get("base_sha") != base:
        raise ValueError("linked UI correction must retain its active full claim base")
    if task.get("branch") != git(repo, "branch", "--show-current").decode().strip() or task.get("worktree") != ".":
        raise ValueError("linked UI correction branch/worktree differs from the current claim")
    if Path(git(repo, "rev-parse", "--show-toplevel").decode().strip()).resolve() != repo:
        raise ValueError("linked UI correction requires the canonical claimed repository root")
    try:
        taskctl.require_active_lease(task, str(task.get("owner") or ""), "Linked UI correction")
        indexed = taskctl.index_backlog(copy.deepcopy(backlog))
        errors = taskctl.corrective_task_errors(indexed[0], indexed[3], repo)
    except (SystemExit, KeyError, TypeError) as exc:
        raise ValueError(f"invalid linked correction admission: {exc}") from exc
    if errors:
        raise ValueError("invalid linked correction admission: " + "; ".join(errors))
    predecessor = yaml_object(blob(repo, base, "planning/backlog.yaml"), "correction predecessor backlog")
    if find_task(predecessor, str(task["id"])) is not None:
        raise ValueError("linked correction base must precede its admission")
    if (
        taskctl.canonical_json_sha256(taskctl.corrective_paused_snapshot(predecessor))
        != task["correction"]["paused_state_sha256"]
    ):
        raise ValueError("linked correction paused predecessor differs from admission")
    prior = taskctl.corrective_tasks(predecessor)
    retained = [item for item in taskctl.corrective_tasks(backlog) if item["id"] != task["id"]]
    if prior != retained:
        raise ValueError("linked correction must preserve prior corrective history")
    return indexed[3][task["correction"]["origin_task_id"]]


def linked_correction_authority(
    repo: Path, base: str, head: str, backlog: dict[str, Any], task: dict[str, Any]
) -> dict[str, Any]:
    origin = linked_correction_admission(repo, base, head, backlog, task)
    if not corrective_ui_paths(task):
        raise ValueError("linked UI correction must have admitted governed UI scope")
    if origin.get("review_gate") != "human-and-agent-review":
        errors = linked_amendment_origin_errors(repo, head, backlog, task, origin)
        if errors:
            conformance_errors = linked_conformance_origin_errors(repo, head, backlog, task, origin)
            if conformance_errors:
                raise ValueError(
                    "linked UI correction origin lacks inherited human-and-agent-review, "
                    "authenticated amendment or governed conformance authority: "
                    + "; ".join(errors + conformance_errors)
                )
    return origin


def linked_conformance_origin_errors(
    repo: Path, head: str, backlog: dict[str, Any], task: dict[str, Any], origin: dict[str, Any]
) -> list[str]:
    """Authenticate the installed-verifier alternative in ADR-0003, not its proof."""
    import taskctl

    try:
        binding = task["correction"]
        if (
            origin.get("review_gate") != "agent-review"
            or origin.get("experience_change") is not None
            or origin.get("amendment_id") is not None
            or binding.get("origin_amendment_id") is not None
            or taskctl.canonical_json_sha256(taskctl.corrective_origin_snapshot(origin)) != binding["origin_sha256"]
            or not independent_identity(origin.get("review", {}).get("reviewer"), origin.get("owner"))
        ):
            raise ValueError("conformance origin must be the exact independently reviewed ordinary task")
        wave = next(item for item in backlog["waves"] if item["id"] == task["wave"])
        approval = wave["approval"]
        packet = str(approval.get("approved_commit"))
        if (
            approval.get("status") != "APPROVED"
            or HUMAN_ID.fullmatch(str(approval.get("approved_by"))) is None
            or resolve_commit(repo, packet) != packet
            or not is_ancestor(repo, packet, binding["origin_commit"])
        ):
            raise ValueError("conformance origin requires the immutable human-approved Wave packet")
        original = yaml_object(blob(repo, packet, "planning/backlog.yaml"), "approved Wave packet")
        original_task = find_task(original, str(origin["id"]))
        if (
            original_task is None
            or original_task.get("status") != "NOT_STARTED"
            or original_task.get("review_gate") != origin.get("review_gate")
            or original_task.get("experience_change") is not None
            or taskctl.corrective_contract(original, original_task) != taskctl.corrective_contract(backlog, origin)
        ):
            raise ValueError("conformance origin scope differs from the approved Wave packet")
        original_wave = next(item for item in original["waves"] if item["id"] == task["wave"])
        if original_wave.get("approval", {}).get("status") == "APPROVED":
            raise ValueError("conformance packet must precede its distinct approval record")
        introductions = (
            git(
                repo,
                "rev-list",
                "--reverse",
                "--ancestry-path",
                f"{packet}..{binding['origin_commit']}",
                "--",
                "planning/backlog.yaml",
            )
            .decode()
            .splitlines()
        )
        if not introductions:
            raise ValueError("conformance Wave approval has no committed introduction")
        introduced = introductions[0]
        approved = yaml_object(blob(repo, introduced, "planning/backlog.yaml"), "Wave approval introduction")
        if (
            git(repo, "rev-list", "--parents", "-n", "1", introduced).decode().split() != [introduced, packet]
            or next(item for item in approved["waves"] if item["id"] == task["wave"])["approval"] != approval
        ):
            raise ValueError("conformance Wave approval differs from its actual packet-child introduction")
        if not is_ancestor(repo, introduced, str(origin.get("base_sha"))):
            raise ValueError("conformance Wave approval must precede the original claim")
        slices = [
            (capability["id"], slice_)
            for capability in original["capabilities"]
            for slice_ in capability.get("slices", [])
            if slice_.get("wave") == task["wave"]
        ]
        if approval.get("capability_ids") != sorted({identity for identity, _ in slices}) or approval.get(
            "slice_ids"
        ) != [slice_["id"] for _, slice_ in slices]:
            raise ValueError("conformance Wave approval inventory differs from its packet")
        selected = [
            (identity, slice_)
            for identity, slice_ in slices
            if any(item["id"] == origin["id"] for item in slice_["tasks"])
        ]
        if len(selected) != 1:
            raise ValueError("conformance origin must belong to exactly one approved Wave slice")
        capability_id, slice_ = selected[0]
        plan_paths = git(repo, "ls-tree", "-r", "--name-only", packet, "--", f"planning/slice-plans/{capability_id}")
        plans = [
            path for path in plan_paths.decode().splitlines() if PurePosixPath(path).name.startswith(f"{slice_['id']}-")
        ]
        if len(plans) != 1:
            raise ValueError("conformance origin lacks its exact approved slice plan")
        before = blob(repo, packet, plans[0]).decode("utf-8").replace("\r\n", "\n").split("---", 2)
        after = blob(repo, head, plans[0]).decode("utf-8").replace("\r\n", "\n").split("---", 2)
        old_meta, new_meta = yaml.safe_load(before[1]), yaml.safe_load(after[1])
        expected_approval = {
            "status": "approved",
            **{key: approval[key] for key in ("approved_by", "approved_at", "approved_commit")},
        }
        if (
            before[0].strip()
            or after[0].strip()
            or before[2] != after[2]
            or new_meta.get("approval") != expected_approval
            or new_meta.get("status") != "approved"
            or {key: value for key, value in old_meta.items() if key not in {"approval", "status"}}
            != {key: value for key, value in new_meta.items() if key not in {"approval", "status"}}
            or origin["id"] not in old_meta.get("task_ids", [])
        ):
            raise ValueError("conformance slice scope is not the unchanged approved packet")
        verifier = find_task(backlog, "CAP-00.S06.T04") or {}
        installed = find_task(original, "CAP-00.S06.T04") or {}
        if (
            taskctl.corrective_origin_snapshot(verifier) != taskctl.corrective_origin_snapshot(installed)
            or installed.get("status") != "DONE"
            or installed.get("review", {}).get("result") != "approved"
            or not independent_identity(installed.get("review", {}).get("reviewer"), installed.get("owner"))
            or not installed.get("evidence")
            or tree_entry(repo, head, "tools/ui_conformance.py") != ("100644", "blob")
        ):
            raise ValueError("conformance verifier was not independently installed before Wave approval")
        for reference in installed["evidence"]:
            if (
                not is_ancestor(repo, reference["commit"], packet)
                or hashlib.sha256(blob(repo, packet, reference["path"])).hexdigest() != reference["sha256"]
            ):
                raise ValueError("installed conformance evidence is not authenticated to the approved packet")
        # Actual product conformance is required separately for the current
        # correction; the old verifier's DONE flag is never a substitute.
        if git(repo, "diff", "--name-only", packet, head, "--", "design/ui-reference").strip():
            raise ValueError("conformance origin cannot borrow a later changed reference")
        ranges = correction_submission_ranges(repo, binding["origin_commit"], {"tasks": [origin]}, ordinary_origin=True)
        if not ranges or not is_ancestor(repo, ranges[-1]["candidate"], binding["origin_commit"]):
            raise ValueError("conformance origin independent review is not ancestral")
        return []
    except (KeyError, IndexError, StopIteration, TypeError, ValueError, UnicodeError, yaml.YAMLError) as exc:
        return [str(exc)]


def linked_conformance_classification_errors(
    repo: Path, base: str, head: str, contract: dict[str, Any], task: dict[str, Any], policy: dict[str, Any]
) -> list[str]:
    if not isinstance(contract.get("restorationClassification"), dict):
        return ["linked conformance restoration requires independent classification and current product captures"]
    commits = implementation_commits(repo, base, head, policy)
    files: set[str] = set()
    for commit in commits:
        if len(git(repo, "rev-list", "--parents", "-n", "1", commit).decode().split()) != 2:
            return ["linked conformance restoration does not support merged UI history"]
        files.update(path for path in commit_paths(repo, commit) if is_implementation_path(path, policy))
    if not commits or files - corrective_ui_paths(task):
        return ["linked conformance classification exceeds the admitted UI history"]
    scope = {
        "taskDefinitionSha256": task["correction"]["origin_sha256"],
        "resumedUiFiles": sorted(files),
        "resumedUiCommits": commits,
        "reactivationCommit": base,
        "correctionProductPaths": task["correction"]["changed_paths"],
    }
    return restoration_classification_errors(repo, base, head, contract, scope, policy)


def linked_amendment_origin_errors(
    repo: Path, head: str, backlog: dict[str, Any], task: dict[str, Any], origin: dict[str, Any]
) -> list[str]:
    """Consume approved amendment authority without adding forbidden task fields."""
    import taskctl

    try:
        binding = task["correction"]
        identity = binding["origin_amendment_id"]
        experience = origin.get("experience_change") or {}
        if (
            not identity
            or origin.get("amendment_id") != identity
            or origin.get("id") != binding["origin_task_id"]
            or taskctl.canonical_json_sha256(taskctl.corrective_origin_snapshot(origin)) != binding["origin_sha256"]
            or experience.get("kind") != "approved-reference-implementation"
            or experience.get("contract_path") != f"artifacts/evidence/ui-change/{origin['id']}.json"
        ):
            raise ValueError("origin is not the exact bound amendment approved-reference implementation")
        amendment = amendment_record(taskctl.serializable_backlog(backlog), identity)
        if amendment.get("lifecycle", {}).get("status") != "ADOPTED":
            raise ValueError("origin amendment is not adopted")
        approved_amendment_packet(repo, head, amendment)
        ranges = correction_submission_ranges(repo, head, {"tasks": [origin]})
        candidate = ranges[-1]["candidate"]
        if not is_ancestor(repo, candidate, binding["origin_commit"]):
            raise ValueError("reviewed origin candidate is outside the admitted origin history")
        original = validate(repo, origin["base_sha"], candidate)
        if not original["ok"] or original["changeKind"] != "approved-reference-implementation":
            raise ValueError("reviewed origin UI contract does not authenticate: " + "; ".join(original["errors"]))
        return []
    except (KeyError, IndexError, TypeError, ValueError, UnicodeError, yaml.YAMLError) as exc:
        return [str(exc)]


def authenticated_active_corrections(repo: Path, head: str, backlog: dict[str, Any]) -> list[dict[str, Any]]:
    """Authenticate correction-shaped records before inventory or scope can omit UI work."""
    import taskctl

    campaign_tasks = taskctl.corrective_tasks(backlog)
    active = [
        task
        for task in backlog_tasks(backlog)
        if task.get("status") in {"IN_PROGRESS", "REVIEW"}
        and (
            "correction" in task
            or LINKED_CORRECTION_ID.fullmatch(str(task.get("id"))) is not None
            or any(task is admitted for admitted in campaign_tasks)
        )
    ]
    for task in active:
        raw_base = task.get("base_sha")
        if not isinstance(raw_base, str) or not re.fullmatch(r"[0-9a-f]{40}", raw_base):
            raise ValueError(f"active correction {task.get('id')} lacks a canonical base_sha")
        base = resolve_commit(repo, raw_base)
        if base == head or not is_ancestor(repo, base, head):
            raise ValueError(f"active correction {task.get('id')} has an invalid base_sha range")
        linked_correction_admission(repo.resolve(), base, head, backlog, task)
    return active


def linked_correction_range_errors(
    repo: Path, base: str, head: str, task: dict[str, Any], policy: dict[str, Any]
) -> list[str]:
    errors: list[str] = []
    permitted = corrective_ui_paths(task)
    spec_path = task["correction"]["spec"]["path"]
    for commit in git(repo, "rev-list", f"{base}..{head}").decode().splitlines():
        paths = commit_paths(repo, commit)
        ui_paths = {path for path in paths if is_implementation_path(path, policy)}
        if ui_paths - permitted:
            errors.append(
                f"linked correction commit {commit} exceeds admitted UI paths: {sorted(ui_paths - permitted)}"
            )
        if spec_path in paths or any(path.startswith(f"{policy['referenceRoot']}/") for path in paths):
            errors.append(f"linked correction commit {commit} touches immutable spec or approved UI reference")
        for parent in git(repo, "rev-list", "--parents", "-n", "1", commit).decode().split()[1:]:
            errors.extend(implementation_object_errors(repo, parent, commit, sorted(ui_paths)))
    return errors


def tree_files(repo: Path, commit: str, root: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    files: list[str] = []
    output = git(repo, "ls-tree", "-r", "-z", commit, "--", root)
    for record in output.split(b"\0"):
        if not record:
            continue
        metadata, separator, raw_path = record.partition(b"\t")
        parts = metadata.decode("ascii", errors="replace").split()
        path = raw_path.decode("utf-8") if separator else ""
        if len(parts) != 3 or not path:
            errors.append("Git returned a malformed UI-reference tree entry")
            continue
        mode, kind, _ = parts
        relative = PurePosixPath(path).relative_to(PurePosixPath(root)).as_posix()
        if relative.startswith("previews/") or "__pycache__" in relative or relative in REFERENCE_EXCLUSIONS:
            continue
        if mode == "120000" or kind != "blob":
            errors.append(f"UI-reference tree contains a redirected or non-file entry: {relative}")
            continue
        files.append(relative)
    return sorted(files), errors


def canonical_payload(path: str, payload: bytes) -> bytes:
    return payload.replace(b"\r\n", b"\n") if Path(path).suffix.lower() in TEXT_SUFFIXES else payload


def reference_state(repo: Path, commit: str, policy: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    approval_path = str(policy.get("approvalPath", ""))
    manifest_path = str(policy.get("manifestPath", ""))
    root = str(policy.get("referenceRoot", ""))
    try:
        approval_payload = blob(repo, commit, approval_path)
        manifest_payload = blob(repo, commit, manifest_path)
        approval = yaml_object(approval_payload, approval_path)
        manifest = yaml_object(manifest_payload, manifest_path)
    except (OSError, UnicodeDecodeError, ValueError, yaml.YAMLError) as exc:
        return {}, [f"cannot load UI-reference state at {commit[:8]}: {exc}"]
    if approval.get("reference_id") != manifest.get("reference_id"):
        errors.append("UI-reference approval and manifest IDs differ")
    if approval.get("version") != manifest.get("version"):
        errors.append("UI-reference approval and manifest versions differ")
    if approval.get("status") != "approved" or manifest.get("status") != "approved":
        errors.append("UI-reference approval and manifest must both be approved")
    governed = manifest.get("governed_files")
    expected_hashes = manifest.get("file_hashes")
    if not isinstance(governed, list) or any(not isinstance(item, str) for item in governed):
        errors.append("UI-reference governed_files must be a string array")
        governed = []
    if not isinstance(expected_hashes, dict) or any(
        not isinstance(key, str) or not isinstance(value, str) for key, value in expected_hashes.items()
    ):
        errors.append("UI-reference file_hashes must be a string map")
        expected_hashes = {}
    inventory, inventory_errors = tree_files(repo, commit, root)
    errors.extend(inventory_errors)
    if sorted(governed) != inventory or set(expected_hashes) != set(governed):
        errors.append("UI-reference governed files and Git-tree inventory differ")
    observed: dict[str, str] = {}
    for relative in governed:
        try:
            payload = blob(repo, commit, f"{root}/{relative}")
        except ValueError as exc:
            errors.append(str(exc))
            continue
        digest = hashlib.sha256(canonical_payload(relative, payload)).hexdigest()
        observed[relative] = digest
        if expected_hashes.get(relative) != digest:
            errors.append(f"UI-reference governed hash mismatch: {relative}")
    package_sha = hashlib.sha256(
        json.dumps(observed, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "approval": approval,
        "manifest": manifest,
        "approvalPayload": approval_payload,
        "manifestPayload": manifest_payload,
        "referenceId": approval.get("reference_id"),
        "version": approval.get("version"),
        "packageSha256": package_sha,
    }, errors


def find_task(backlog: dict[str, Any], task_id: str) -> dict[str, Any] | None:
    return backlog_task(backlog, task_id)


def automatic_base(repo: Path, head_ref: str) -> str:
    """Use the sole active UI task's full base, including admitted corrections."""
    head = resolve_commit(repo, head_ref)
    try:
        backlog = yaml_object(blob(repo, head, "planning/backlog.yaml"), "planning/backlog.yaml")
    except (UnicodeDecodeError, ValueError, yaml.YAMLError) as exc:
        raise ValueError(f"cannot select UI change base from the authoritative backlog: {exc}") from exc
    authenticated_active_corrections(repo, head, backlog)
    resumed_parents = {
        str(item["correction"].get("id"))
        for item in backlog.get("wave_amendments", [])
        if isinstance(item.get("correction"), dict) and item.get("lifecycle", {}).get("status") == "ADOPTED"
    }
    active = [
        task
        for task in backlog_tasks(backlog)
        if task.get("status") in {"IN_PROGRESS", "REVIEW"}
        and (
            isinstance(task.get("experience_change"), dict)
            or task.get("amendment_id") in resumed_parents
            or (
                task.get("id") == INTENTIONAL_AMENDMENT_TASK_ID and task.get("amendment_id") == INTENTIONAL_AMENDMENT_ID
            )
            or task.get("id") == ADOPTED_CONTINUATION_TASK_ID
            or bool(corrective_ui_paths(task))
        )
    ]
    if len(active) > 1:
        identities = sorted(str(task.get("id")) for task in active)
        raise ValueError(f"ambiguous active UI experience tasks; supply an explicit immutable base: {identities}")
    if len(active) == 1:
        raw_base = active[0].get("base_sha")
        if not isinstance(raw_base, str) or not re.fullmatch(r"[0-9a-f]{40}", raw_base):
            raise ValueError(f"active UI experience task {active[0].get('id')} lacks a canonical base_sha")
        candidate = resolve_commit(repo, raw_base)
        if candidate == head or not is_ancestor(repo, candidate, head):
            raise ValueError(f"active UI experience task {active[0].get('id')} has an invalid base_sha range")
        if corrective_ui_paths(active[0]):
            linked_correction_authority(repo.resolve(), candidate, head, backlog, active[0])
        if active[0].get("id") == ADOPTED_CONTINUATION_TASK_ID:
            from taskctl import require_active_lease, wave_resume_record_errors

            task = active[0]
            owner = task.get("owner")
            branch = git(repo, "branch", "--show-current").decode().strip()
            wave = next((item for item in backlog.get("waves", []) if item.get("id") == "W2"), None)
            if (
                candidate != ADOPTED_CONTINUATION_BASE
                or wave is None
                or wave.get("campaign", {}).get("status") != "ACTIVE"
                or not isinstance(owner, str)
                or not owner
                or task.get("branch") != branch
                or task.get("worktree") != "."
                or wave.get("campaign", {}).get("owner") != owner
                or wave.get("campaign", {}).get("scope") != "wave"
                or wave.get("campaign", {}).get("branch") != branch
                or wave.get("campaign", {}).get("worktree") != "."
                or wave.get("campaign", {}).get("profile") != "LOC"
                or wave.get("campaign", {}).get("platform") != "windows-x64"
                or backlog.get("control_plane", {}).get("active_amendment") is not None
            ):
                raise ValueError("active adopted continuation T01 lacks its exact original claim/W2 campaign")
            try:
                require_active_lease(wave["campaign"], owner, "W2 campaign")
                require_active_lease(task, owner, ADOPTED_CONTINUATION_TASK_ID)
                if wave_resume_record_errors(backlog, "W2", wave["campaign"], repo.resolve()):
                    raise ValueError("active adopted continuation W2 resume history is invalid")
                adopted_continuation_original_task(repo.resolve(), head, backlog, task)
                amendment = amendment_record(backlog, "W2.A02")
                packet, _, _ = approved_amendment_packet(repo.resolve(), head, amendment)
                adopted_continuation_adoption(repo.resolve(), head, backlog, amendment, packet)
            except (SystemExit, KeyError, StopIteration) as exc:
                raise ValueError(
                    f"active adopted continuation T01 has invalid amendment/lease authority: {exc}"
                ) from exc
        return candidate
    return f"{head_ref}^"


def implementation_commits(repo: Path, base: str, head: str, policy: dict[str, Any]) -> list[str]:
    commits = git(repo, "rev-list", "--reverse", "--topo-order", f"{base}..{head}").decode("ascii").splitlines()
    result: list[str] = []
    for commit in commits:
        paths = commit_paths(repo, commit)
        if any(is_implementation_path(path, policy) for path in paths):
            result.append(commit)
    return result


@lru_cache(maxsize=16384)
def _committed_paths(repo: Path, commit: str) -> frozenset[str]:
    """Cache immutable Git path inventories during long original-base scans."""

    raw = git(repo, "diff-tree", "--root", "--no-commit-id", "--name-only", "-z", "-r", "-m", commit, "--")
    return frozenset(canonical_path(item.decode("utf-8")) for item in raw.split(b"\0") if item)


def commit_paths(repo: Path, commit: str) -> set[str]:
    return set(_committed_paths(repo, commit))


def restoration_segments(
    repo: Path,
    base: str,
    head: str,
    activation: str,
    reviewed_ranges: list[dict[str, Any]],
    policy: dict[str, Any],
) -> dict[str, list[str]]:
    """Attribute every UI-changing commit, never just the final path union.

    Callers must authenticate the supplied correction submissions first. This
    deliberately recognizes one linear correction/return, not a general DAG.
    """
    commits = git(repo, "rev-list", "--reverse", "--topo-order", "--parents", f"{base}..{head}").decode().splitlines()
    previous = base
    ordered: list[str] = []
    for row in commits:
        values = row.split()
        if len(values) != 2 or values[1] != previous:
            raise ValueError("resumed amendment UI history must be linear")
        previous = values[0]
        ordered.append(previous)
    if not ordered or activation not in ordered or previous != head:
        raise ValueError("resumed amendment lacks its exact activation in the original range")
    positions = {commit: index for index, commit in enumerate([base, *ordered])}
    for item in reviewed_ranges:
        if not (
            item["base"] in positions
            and item["candidate"] in positions
            and positions[item["base"]] < positions[item["candidate"]] < positions[activation]
        ):
            raise ValueError("correction UI submission range is outside its ordered segment")
        if item["paths"] != sorted(changed_paths(repo, item["base"], item["candidate"])):
            raise ValueError("correction submission changed paths differ from Git")
    inherited: set[str] = set()
    resumed: set[str] = set()
    inherited_commits: list[str] = []
    resumed_commits: list[str] = []
    resumed_net = {path for path in changed_paths(repo, activation, head) if is_implementation_path(path, policy)}
    for commit in ordered:
        paths = {path for path in commit_paths(repo, commit) if is_implementation_path(path, policy)}
        if not paths:
            continue
        parent = resolve_commit(repo, f"{commit}^")
        object_errors = implementation_object_errors(repo, parent, commit, sorted(paths))
        if object_errors:
            raise ValueError(object_errors[0])
        delta = git(repo, "diff", "--name-status", "--find-renames", parent, commit, "--", *sorted(paths))
        if any(row[:1] in {b"R", b"C", b"T"} for row in delta.splitlines()):
            raise ValueError("resumed amendment UI range does not support rename/copy/type changes")
        if positions[commit] <= positions[activation]:
            matches = [
                item
                for item in reviewed_ranges
                if positions[item["base"]] < positions[commit] <= positions[item["candidate"]]
            ]
            if len(matches) != 1 or not paths.issubset(matches[0]["paths"]):
                raise ValueError("UI commit has a gap, overlap or hidden path outside reviewed correction ranges")
            inherited.update(paths)
            inherited_commits.append(commit)
        else:
            if not paths.issubset(resumed_net):
                raise ValueError("resumed UI commit contains a hidden add/revert outside its net inventory")
            resumed.update(paths)
            resumed_commits.append(commit)
    if not inherited_commits or not resumed_commits:
        raise ValueError("resumed amendment contract requires both correction and restoration UI segments")
    return {
        "inheritedCorrectionUiFiles": sorted(inherited),
        "resumedUiFiles": sorted(resumed),
        "inheritedUiCommits": inherited_commits,
        "resumedUiCommits": resumed_commits,
    }


def intentional_amendment_delivery_path(path: str, contract_path: str, policy: dict[str, Any]) -> bool:
    """Keep T02 in renderer/reference/evidence scope; deny native and policy work."""
    if path in {
        "planning/backlog.yaml",
        "planning/status-summary.md",
        "docs/planning-implementation-plan.md",
        INTENTIONAL_AMENDMENT_REFERENCE_APPROVAL_PATH,
        contract_path,
    }:
        return True
    if path in {
        "planning/review-site/index.html",
        "planning/review-site/enablers/index.html",
        "planning/review-site/enablers/ECR-0009.html",
        "planning/review-site/waves/W2.html",
        "planning/review-site/manifest.json",
    }:
        return True
    if path.startswith(f"{policy['referenceRoot']}/"):
        return True
    if path.startswith("artifacts/evidence/W2.A01.T02") and (
        path == "artifacts/evidence/W2.A01.T02.json"
        or path.startswith("artifacts/evidence/W2.A01.T02.")
        or path.startswith("artifacts/evidence/W2.A01.T02/")
    ):
        return True
    if path.startswith("apps/desktop/src/"):
        return is_implementation_path(path, policy) or path.endswith(
            (".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx", ".d.ts")
        )
    if path.startswith("packages/ui-components/src/"):
        return is_implementation_path(path, policy)
    if path.startswith("packages/ui-components/tests/"):
        return path.endswith((".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx"))
    if path.startswith("tests/desktop/"):
        return path.endswith((".py", ".ts", ".tsx"))
    return False


def intentional_amendment_typed_product_path(path: str) -> bool:
    """Classify exact-lane typed source without changing governed UI inventory."""
    return path.endswith(".d.ts") and path.startswith(("apps/desktop/src/", "packages/ui-components/src/"))


def intentional_amendment_reference_projection(
    repo: Path, base: str, parent: str, commit: str, publication: str, path: str, policy: dict[str, Any]
) -> bool:
    """Admit only the mechanical active-reference text refresh of an existing ECR page."""
    if (
        re.fullmatch(r"planning/review-site/enablers/ECR-[0-9]{4}\.html", path) is None
        or tree_entry(repo, base, path) != ("100644", "blob")
        or not is_ancestor(repo, publication, parent)
    ):
        return False
    approval = yaml_object(blob(repo, publication, str(policy["approvalPath"])), "published reference approval")
    previous, current = approval.get("supersedes"), approval.get("reference_id")
    if (
        not all(
            isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", value)
            for value in (previous, current)
        )
        or previous == current
    ):
        return False
    before, after = blob(repo, parent, path), blob(repo, commit, path)
    old = f"The current published reference is <code>{previous}</code>;".encode()
    new = f"The current published reference is <code>{current}</code>;".encode()
    return before.count(old) == 1 and after == before.replace(old, new, 1)


def intentional_amendment_segments(
    repo: Path,
    base: str,
    head: str,
    publication: str,
    contract_path: str,
    reference_paths: set[str],
    policy: dict[str, Any],
) -> dict[str, list[str]]:
    """Check every T02 commit, including changes erased from the final diff."""
    rows = git(repo, "rev-list", "--reverse", "--topo-order", "--parents", f"{base}..{head}").decode().splitlines()
    previous = base
    ordered: list[str] = []
    for row in rows:
        values = row.split()
        if len(values) != 2 or values[1] != previous:
            raise ValueError("intentional amendment UI history must be linear")
        previous = values[0]
        ordered.append(previous)
    if not ordered or previous != head or publication not in ordered:
        raise ValueError("intentional amendment publication is absent from the exact task range")

    reference_root = f"{policy['referenceRoot']}/"
    contract_root = f"{policy['contractRoot']}/"
    net = changed_paths(repo, base, head)
    net_ui = {path for path in net if is_implementation_path(path, policy)}
    net_typed = {path for path in net if intentional_amendment_typed_product_path(path)}
    net_reference = {path for path in net if path.startswith(reference_root)}
    touched_ui: set[str] = set()
    touched_typed: set[str] = set()
    touched_reference: set[str] = set()
    ui_commits: list[str] = []
    typed_commits: list[str] = []
    reference_commits: list[str] = []
    seen_publication = False
    for commit in ordered:
        parent = resolve_commit(repo, f"{commit}^")
        paths = commit_paths(repo, commit)
        if paths & (MAINTENANCE_CONTROL_PATHS | INTENTIONAL_AMENDMENT_CONTROL_PATHS):
            raise ValueError("intentional amendment product range touched a design-first control or reviewed ADR")
        if any(path.startswith(contract_root) and path != contract_path for path in paths):
            raise ValueError("intentional amendment product range touched an extra UI contract")
        extra_delivery = sorted(
            path
            for path in paths
            if not intentional_amendment_delivery_path(path, contract_path, policy)
            and not intentional_amendment_reference_projection(repo, base, parent, commit, publication, path, policy)
        )
        if extra_delivery:
            raise ValueError(f"intentional amendment product range touched out-of-scope files: {extra_delivery}")
        for path in paths:
            for point in (parent, commit):
                entry = tree_entry(repo, point, path)
                if entry is not None and entry != ("100644", "blob"):
                    raise ValueError(f"intentional amendment delivery path is redirected or executable: {path}")
        ui_paths = {path for path in paths if is_implementation_path(path, policy)}
        typed_paths = {path for path in paths if intentional_amendment_typed_product_path(path)}
        product_paths = ui_paths | typed_paths
        reference_delta = {path for path in paths if path.startswith(reference_root)}
        if "planning/backlog.yaml" in paths and (product_paths or reference_delta):
            raise ValueError(
                "intentional amendment backlog transition cannot share a reference or renderer product commit"
            )
        if product_paths and not seen_publication:
            raise ValueError("human reference publication must strictly precede every product-source commit")
        if reference_delta:
            if commit != publication or seen_publication or product_paths:
                raise ValueError("intentional amendment reference may change only in its separate publication commit")
            if not reference_delta.issubset(reference_paths):
                raise ValueError("intentional amendment publication touched an unreviewed reference file")
            seen_publication = True
            reference_commits.append(commit)
            touched_reference.update(reference_delta)
        elif commit == publication:
            raise ValueError("cited intentional amendment publication did not change the reference")
        statuses = git(repo, "diff", "--name-status", "--find-renames", "--find-copies", parent, commit, "--")
        if any(line[:1] in {b"R", b"C", b"T"} for line in statuses.splitlines()):
            raise ValueError("intentional amendment range does not support rename/copy/type changes")
        if ui_paths:
            touched_ui.update(ui_paths)
            ui_commits.append(commit)
        if typed_paths:
            touched_typed.update(typed_paths)
            typed_commits.append(commit)
    if reference_commits != [publication] or not ui_commits:
        raise ValueError("intentional amendment requires one publication and later renderer work")
    if tree_entry(repo, head, contract_path) != ("100644", "blob"):
        raise ValueError("intentional amendment final UI evidence contract is not a regular blob")
    if touched_ui != net_ui or touched_typed != net_typed or touched_reference != net_reference:
        raise ValueError("intentional amendment range contains hidden add/revert UI, typed source or reference history")
    return {
        "uiFiles": sorted(touched_ui),
        "uiCommits": ui_commits,
        "typedProductFiles": sorted(touched_typed),
        "typedProductCommits": typed_commits,
        "referenceFiles": sorted(touched_reference),
    }


def immutable_record(
    repo: Path, head: str, path: str, digest: str | None = None, *, evidence: bool = False
) -> tuple[dict[str, Any], str]:
    """Authenticate one named record; do not enumerate unrelated evidence."""
    if tree_entry(repo, head, path) != ("100644", "blob"):
        raise ValueError(f"authority record is not a regular Git file: {path}")
    payload = blob(repo, head, path)
    hash_payload = payload.replace(b"\r\n", b"\n").replace(b"\r", b"\n") if evidence else payload
    if digest is not None and hashlib.sha256(hash_payload).hexdigest() != digest:
        raise ValueError(f"authority record hash mismatch: {path}")
    changes = git(repo, "log", "--format=%H", head, "--", path).decode().splitlines()
    if len(changes) != 1 or tree_entry(repo, f"{changes[0]}^", path) is not None:
        raise ValueError(f"authority record must have one immutable introduction: {path}")
    return json_object(payload, path), changes[0]


def amendment_record(backlog: dict[str, Any], identity: str) -> dict[str, Any]:
    matches = [item for item in backlog.get("wave_amendments", []) if item.get("id") == identity]
    if len(matches) != 1:
        raise ValueError("amendment authority identity is absent or duplicated")
    return matches[0]


def approved_amendment_packet(repo: Path, head: str, amendment: dict[str, Any]) -> tuple[dict[str, Any], str, str]:
    # This existing narrow helper checks only the named approval, packet,
    # proposal/schema/review inputs. Never call aggregate historical validators.
    from planctl import _approved_experience_packet_commit

    identity = str(amendment["id"])
    path = f"planning/wave-amendment-approvals/{identity}.json"
    reference = amendment["approval_reference"]
    if reference.get("path") != path:
        raise ValueError("amendment approval selector differs from its canonical path")
    approval, introduction = immutable_record(repo, head, path, reference.get("sha256"))
    if reference.get("introduction_commit") != introduction or approval.get("status") != "APPROVED":
        raise ValueError("amendment approval introduction/status differs")
    packet_path = f"planning/enabler-change-requests/{amendment['change_request_id']}.packet.json"
    packet = json_object(blob(repo, head, packet_path), packet_path)
    packet_commit, errors = _approved_experience_packet_commit(repo, packet)
    if errors or packet_commit is None:
        raise ValueError("amendment packet authentication failed: " + "; ".join(errors))
    if packet.get("proposedAmendmentId") != identity or packet.get("targetWave") != amendment.get("target_wave"):
        raise ValueError("approved amendment packet identity differs")
    from taskctl import materialized_amendment_task

    approved_tasks = packet.get("taskInventory", [])
    backlog_schema = json_object(blob(repo, head, "planning/backlog.schema.json"), "backlog schema")
    task_validator = Draft202012Validator({"$ref": "#/$defs/enablerTask", "$defs": backlog_schema["$defs"]})
    if [item.get("id") for item in approved_tasks] != [item.get("id") for item in amendment.get("tasks", [])]:
        raise ValueError("approved amendment task inventory differs")
    for approved, actual in zip(approved_tasks, amendment["tasks"], strict=True):
        if list(task_validator.iter_errors(actual)):
            raise ValueError("approved amendment task no longer satisfies the enabler task schema")
        expected = materialized_amendment_task(identity, approved)
        for field in (
            "id",
            "amendment_id",
            "title",
            "objective",
            "dependencies",
            "acceptance_criteria",
            "verification_commands",
            "packet_task_sha256",
        ):
            if actual.get(field) != expected[field]:
                raise ValueError(f"immutable approved task field differs: {actual.get('id')}/{field}")
    return packet, packet_commit, introduction


def intentional_amendment_control_predecessor(
    repo: Path, head: str, base: str, amendment: dict[str, Any]
) -> dict[str, str]:
    """Require the exact T01 source and ADR to be independently reviewed and retained."""
    control = next(
        (task for task in amendment["tasks"] if task.get("id") == INTENTIONAL_AMENDMENT_CONTROL_TASK_ID), None
    )
    if control is None or control.get("status") != "DONE" or control.get("review", {}).get("result") != "approved":
        raise ValueError("intentional amendment T01 lacks an approved independent task review")
    ranges = correction_submission_ranges(repo, head, {"tasks": [control]})
    if not ranges or not independent_identity(control["review"].get("reviewer"), control.get("owner")):
        raise ValueError("intentional amendment T01 review is absent or self-reviewed")
    for reviewed_range in ranges:
        if reviewed_range["paths"] != sorted(changed_paths(repo, reviewed_range["base"], reviewed_range["candidate"])):
            raise ValueError("intentional amendment T01 reviewed changed paths differ from actual Git history")
    candidate = ranges[-1]["candidate"]
    ledger = control["review_control"]["attempts"][-1]["ledger"]
    _record, review_introduction = immutable_record(repo, head, ledger["path"], ledger["sha256"], evidence=True)
    control_base = control.get("base_sha")
    if (
        not isinstance(control_base, str)
        or resolve_commit(repo, control_base) != control_base
        or any(
            left == right or not is_ancestor(repo, left, right)
            for left, right in pairwise((control_base, candidate, review_introduction, base))
        )
    ):
        raise ValueError("intentional amendment T01 review must strictly precede the T02 claim base")
    control_paths = changed_paths(repo, control_base, candidate)
    if not INTENTIONAL_AMENDMENT_CONTROL_PATHS.issubset(control_paths):
        raise ValueError("intentional amendment T01 reviewed candidate lacks its gate/schema/ADR/index change")
    for path in INTENTIONAL_AMENDMENT_CONTROL_PATHS:
        if tree_entry(repo, candidate, path) != ("100644", "blob"):
            raise ValueError(f"intentional amendment T01 reviewed control is not a regular blob: {path}")
    index_path = "docs/adr/index.json"
    candidate_index = json_object(blob(repo, candidate, index_path), "reviewed T01 ADR index")
    candidate_records = candidate_index.get("records")
    if not isinstance(candidate_records, list):
        raise ValueError("intentional amendment reviewed T01 ADR index has no records")

    def unique_adr_records(records: object) -> bool:
        if not isinstance(records, list) or not all(
            isinstance(record, dict) and isinstance(record.get("id"), str) and isinstance(record.get("path"), str)
            for record in records
        ):
            return False
        return len({record["id"] for record in records}) == len(records) and len(
            {record["path"] for record in records}
        ) == len(records)

    if (
        not unique_adr_records(candidate_records)
        or sum(
            isinstance(record, dict)
            and record.get("id") == "ADR-0035"
            and record.get("path") == "docs/adr/ADR-0035-admit-exact-intentional-amendment-ui-lineage.md"
            and record.get("status") == "Proposed"
            and isinstance(record.get("linkedTasks"), list)
            and INTENTIONAL_AMENDMENT_CONTROL_TASK_ID in record["linkedTasks"]
            for record in candidate_records
        )
        != 1
    ):
        raise ValueError("intentional amendment reviewed T01 ADR index lacks its proposed decision")
    previous_index = candidate_index
    for commit in git(repo, "rev-list", "--reverse", f"{candidate}..{head}").decode().splitlines():
        touched = commit_paths(repo, commit) & INTENTIONAL_AMENDMENT_CONTROL_PATHS
        if touched - {index_path}:
            raise ValueError(
                "intentional amendment reviewed T01 gate/schema/ADR/tests/procedure was touched after review"
            )
        if index_path not in touched:
            continue
        if tree_entry(repo, commit, index_path) != ("100644", "blob"):
            raise ValueError("intentional amendment post-review ADR index is redirected or missing")
        current_index = json_object(blob(repo, commit, index_path), "post-review ADR index")
        records = current_index.get("records")
        prior_records = previous_index["records"]
        if (
            not isinstance(records, list)
            or not unique_adr_records(records)
            or len(records) <= len(prior_records)
            or records[: len(prior_records)] != prior_records
            or {key: value for key, value in current_index.items() if key != "records"}
            != {key: value for key, value in candidate_index.items() if key != "records"}
        ):
            raise ValueError(
                "intentional amendment post-review ADR index must append records without changing reviewed entries"
            )
        previous_index = current_index
    return {"candidate": candidate, "reviewIntroduction": review_introduction}


def intentional_amendment_live_claim(
    repo: Path, base: str, head: str, contract: dict[str, Any], policy: dict[str, Any]
) -> dict[str, Any]:
    """Bind T02 to its live taskctl claim before reading reference authority."""
    from taskctl import require_active_lease

    if head != resolve_commit(repo, "HEAD"):
        raise ValueError("intentional amendment UI authority requires current HEAD")
    expected_selector = {
        "amendmentId": INTENTIONAL_AMENDMENT_ID,
        "changeRequestId": INTENTIONAL_AMENDMENT_CHANGE_REQUEST_ID,
        "controlTaskId": INTENTIONAL_AMENDMENT_CONTROL_TASK_ID,
        "referenceApprovalPath": INTENTIONAL_AMENDMENT_REFERENCE_APPROVAL_PATH,
    }
    if (
        contract.get("schemaVersion") != "1.2"
        or contract.get("taskId") != INTENTIONAL_AMENDMENT_TASK_ID
        or contract.get("changeKind") != "intentional-design-change"
        or contract.get("intentionalAmendmentAuthority") != expected_selector
    ):
        raise ValueError("intentional amendment contract selector is not the exact approved W2.A01.T02 lane")
    backlog = yaml_object(blob(repo, head, "planning/backlog.yaml"), "intentional amendment backlog")
    amendment = amendment_record(backlog, INTENTIONAL_AMENDMENT_ID)
    task = backlog_task(backlog, INTENTIONAL_AMENDMENT_TASK_ID)
    if task is None or task not in amendment.get("tasks", []):
        raise ValueError("intentional amendment T02 is absent from its materialized task inventory")
    campaign = amendment.get("campaign") or {}
    wave_matches = [wave for wave in backlog.get("waves", []) if wave.get("id") == "W2"]
    if len(wave_matches) != 1:
        raise ValueError("intentional amendment requires exactly one paused W2 campaign")
    ordinary_campaign = wave_matches[0].get("campaign") or {}
    ordinary_active = [
        task
        for task in backlog_tasks(backlog)
        if task.get("wave") == "W2"
        and task.get("amendment_id") is None
        and task.get("status") in {"IN_PROGRESS", "REVIEW"}
    ]
    competing = [
        other
        for other in backlog.get("wave_amendments", [])
        if other.get("id") != INTENTIONAL_AMENDMENT_ID and (other.get("campaign") or {}).get("status") == "ACTIVE"
    ]
    if (
        ordinary_campaign.get("status") != "PAUSED"
        or ordinary_campaign.get("scope") != "amendment-hold"
        or ordinary_campaign.get("lease") is not None
        or ordinary_active
        or competing
    ):
        raise ValueError("intentional amendment requires the exclusive paused W2 activation boundary")
    owner = task.get("owner")
    current_branch = git(repo, "branch", "--show-current").decode().strip()
    repository_root = Path(git(repo, "rev-parse", "--show-toplevel").decode().strip()).resolve()
    if (
        amendment.get("change_request_id") != INTENTIONAL_AMENDMENT_CHANGE_REQUEST_ID
        or amendment.get("target_wave") != "W2"
        or amendment.get("lifecycle", {}).get("status") != "ACTIVE"
        or campaign.get("status") != "ACTIVE"
        or campaign.get("scope") != "wave-amendment"
        or backlog.get("control_plane", {}).get("active_amendment") != INTENTIONAL_AMENDMENT_ID
        or task.get("amendment_id") != INTENTIONAL_AMENDMENT_ID
        or task.get("status") not in {"IN_PROGRESS", "REVIEW"}
        or task.get("base_sha") != base
        or not isinstance(owner, str)
        or not owner
        or campaign.get("owner") != owner
        or task.get("branch") != current_branch
        or campaign.get("branch") != current_branch
        or task.get("worktree") != "."
        or campaign.get("worktree") != "."
        or repository_root != repo
        or contract.get("implementationAgent") != f"agent:{owner}"
    ):
        raise ValueError(
            "intentional amendment T02 does not hold the exact current campaign/claim/base/branch/worktree"
        )
    try:
        require_active_lease(amendment, owner, "Intentional amendment campaign")
        require_active_lease(task, owner, "Intentional amendment task")
    except SystemExit as exc:
        raise ValueError(f"intentional amendment lease is stale or foreign: {exc}") from exc
    prior = yaml_object(blob(repo, base, "planning/backlog.yaml"), "intentional amendment claim base")
    prior_task = backlog_task(prior, INTENTIONAL_AMENDMENT_TASK_ID) or {}
    if (
        prior_task.get("status") != "READY"
        or prior_task.get("base_sha") is not None
        or prior_task.get("owner") is not None
        or prior_task.get("lease") is not None
    ):
        raise ValueError("intentional amendment T02 base does not precede an eligible claim")
    ordered = git(repo, "rev-list", "--reverse", f"{base}..{head}").decode().splitlines()
    if not ordered or resolve_commit(repo, f"{ordered[0]}^") != base:
        raise ValueError("intentional amendment T02 claim does not descend directly from its base")
    claimed_state = yaml_object(blob(repo, ordered[0], "planning/backlog.yaml"), "intentional amendment claim")
    claimed_task = backlog_task(claimed_state, INTENTIONAL_AMENDMENT_TASK_ID) or {}
    if (
        claimed_task.get("status") != "IN_PROGRESS"
        or claimed_task.get("owner") != owner
        or claimed_task.get("branch") != current_branch
        or claimed_task.get("worktree") != "."
        or claimed_task.get("base_sha") != base
        or (claimed_task.get("lease") or {}).get("claimed_by") != owner
        or not claimed_task.get("started_at")
        or any(
            claimed_task.get(field) != prior_task.get(field)
            for field in (
                "id",
                "amendment_id",
                "title",
                "objective",
                "dependencies",
                "acceptance_criteria",
                "verification_commands",
                "packet_task_sha256",
            )
        )
        or any(
            is_implementation_path(path, policy) or path.startswith(f"{policy['referenceRoot']}/")
            for path in commit_paths(repo, ordered[0])
        )
    ):
        raise ValueError("intentional amendment T02 has no exact pre-product task claim transition")
    return {"backlog": backlog, "amendment": amendment, "task": task, "owner": owner, "claimCommit": ordered[0]}


def intentional_amendment_authority(
    repo: Path, base: str, head: str, contract: dict[str, Any], policy: dict[str, Any]
) -> dict[str, Any]:
    """Authenticate the only approved intentional amendment without task-label authority."""
    from planctl import _reference_publication_content_errors

    live = intentional_amendment_live_claim(repo, base, head, contract, policy)
    amendment = live["amendment"]
    owner = live["owner"]
    packet, packet_commit, approval_introduction = approved_amendment_packet(repo, head, amendment)
    approval_path = amendment["approval_reference"]["path"]
    approval, _ = immutable_record(repo, head, approval_path, amendment["approval_reference"]["sha256"])
    human = approval.get("approvedBy")
    if (
        packet.get("authorizedTaskIds") != [INTENTIONAL_AMENDMENT_CONTROL_TASK_ID, INTENTIONAL_AMENDMENT_TASK_ID]
        or packet.get("governedExperience", {}).get("referenceId") != INTENTIONAL_AMENDMENT_REFERENCE_ID
        or not isinstance(human, str)
        or HUMAN_ID.fullmatch(human) is None
        or human.removeprefix("human:").casefold() == owner.casefold()
        or not is_ancestor(repo, approval_introduction, base)
    ):
        raise ValueError("intentional amendment packet/human approval is missing, substituted or self-approved")
    predecessor = intentional_amendment_control_predecessor(repo, head, base, amendment)

    proposal_root = "planning/W2-reference-1.8"
    proposal_items = packet.get("governedExperience", {}).get("files")
    if not isinstance(proposal_items, list) or not proposal_items:
        raise ValueError("intentional amendment approved reference proposal inventory is absent")
    proposal_paths: set[str] = set()
    for item in proposal_items:
        path = item.get("path") if isinstance(item, dict) else None
        if not isinstance(path, str) or not path.startswith(f"{proposal_root}/") or path in proposal_paths:
            raise ValueError("intentional amendment proposal contains an extra, duplicate or redirected path")
        proposal_paths.add(path)
        if tree_entry(repo, packet_commit, path) != ("100644", "blob") or hashlib.sha256(
            blob(repo, packet_commit, path)
        ).hexdigest() != item.get("sha256"):
            raise ValueError(f"intentional amendment proposal differs from its immutable packet blob: {path}")
    immutable_sources = {
        f"planning/enabler-change-requests/{INTENTIONAL_AMENDMENT_CHANGE_REQUEST_ID}.packet.json",
        approval["packet"]["proposalPath"],
        *proposal_paths,
    }
    for commit in git(repo, "rev-list", f"{packet_commit}..{head}").decode().splitlines():
        if commit_paths(repo, commit) & immutable_sources:
            raise ValueError(
                "intentional amendment reviewed packet/proposal source was touched after approval candidate"
            )
    proposed_manifest = yaml_object(
        blob(repo, packet_commit, f"{proposal_root}/REFERENCE_MANIFEST.yaml"), "intentional amendment proposal manifest"
    )
    governed = proposed_manifest.get("governed_files")
    if (
        proposed_manifest.get("status") != "proposed"
        or not isinstance(governed, list)
        or any(not isinstance(name, str) or canonical_path(name) != name for name in governed)
        or proposal_paths != {f"{proposal_root}/{name}" for name in [*governed, "REFERENCE_MANIFEST.yaml"]}
    ):
        raise ValueError("intentional amendment proposal manifest does not enumerate the exact reviewed files")
    proposal_hashes = {
        name: hashlib.sha256(canonical_payload(name, blob(repo, packet_commit, f"{proposal_root}/{name}"))).hexdigest()
        for name in governed
    }
    if proposed_manifest.get("file_hashes") != proposal_hashes:
        raise ValueError("intentional amendment proposal manifest hashes differ from packet-bound files")
    proposal_package_sha = hashlib.sha256(
        json.dumps(proposal_hashes, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    proposed_approval = yaml_object(
        blob(repo, packet_commit, f"{proposal_root}/APPROVAL.yaml"), "intentional amendment proposed approval"
    )
    if (
        proposed_approval.get("reference_id") != INTENTIONAL_AMENDMENT_REFERENCE_ID
        or proposed_approval.get("version") != "1.8"
        or proposed_approval.get("supersedes") != "RO-UI-ACADEMIC-MINIMAL-1.7"
        or proposed_approval.get("status") != "proposed"
    ):
        raise ValueError("intentional amendment proposed reference identity differs from approved packet")

    record_path = INTENTIONAL_AMENDMENT_REFERENCE_APPROVAL_PATH
    design_approval, record_introduction = immutable_record(repo, head, record_path)
    expected_design_approval = {
        "schemaVersion": "1.0",
        "kind": "ui-reference-design-approval",
        "referenceId": INTENTIONAL_AMENDMENT_REFERENCE_ID,
        "approvedBy": human,
        "approvedAt": approval.get("approvedAt"),
        "scope": "reference-publication-and-plan-binding-only",
        "proposal": {
            "commit": packet_commit,
            "path": proposal_root,
            "packageSha256": proposal_package_sha,
        },
        "amendmentApproval": {
            "path": approval_path,
            "sha256": amendment["approval_reference"]["sha256"],
            "introductionCommit": approval_introduction,
        },
    }
    if (
        any(design_approval.get(key) != value for key, value in expected_design_approval.items())
        or set(design_approval) != set(expected_design_approval) | {"basis"}
        or not isinstance(design_approval.get("basis"), str)
        or "ECR-0009" not in design_approval["basis"]
    ):
        raise ValueError(
            "intentional amendment reference approval record does not bind the exact human decision/proposal"
        )
    publication = contract["reference"]["approvalCommit"]
    anchors = (approval_introduction, base, live["claimCommit"], record_introduction, publication, head)
    if resolve_commit(repo, publication) != publication or any(
        (left == right and not (left == record_introduction and right == publication))
        or (left != right and not is_ancestor(repo, left, right))
        for left, right in pairwise(anchors)
    ):
        raise ValueError("intentional amendment human decision/reference publication ancestry is invalid")
    publication_state, publication_errors = reference_state(repo, publication, policy)
    head_state, head_errors = reference_state(repo, head, policy)
    base_state, base_errors = reference_state(repo, base, policy)
    publication_errors.extend(head_errors)
    publication_errors.extend(base_errors)
    publication_errors.extend(_reference_publication_content_errors(repo, packet, packet_commit, publication))
    published_approval = publication_state.get("approval", {})
    expected_authority = {
        "amendment_id": INTENTIONAL_AMENDMENT_ID,
        "change_request_id": INTENTIONAL_AMENDMENT_CHANGE_REQUEST_ID,
        "approval_record": approval_path,
        "approval_record_sha256": amendment["approval_reference"]["sha256"],
        "approval_record_introduction_commit": approval_introduction,
    }
    if (
        publication_errors
        or base_state.get("referenceId") != "RO-UI-ACADEMIC-MINIMAL-1.7"
        or publication_state != head_state
        or publication_state.get("referenceId") != INTENTIONAL_AMENDMENT_REFERENCE_ID
        or publication_state.get("version") != "1.8"
        or published_approval.get("supersedes") != base_state.get("referenceId")
        or published_approval.get("approval_kind") != "human"
        or published_approval.get("approved_by") != human
        or published_approval.get("approved_at") != approval.get("approvedAt")
        or published_approval.get("authority") != expected_authority
    ):
        raise ValueError(
            "intentional amendment published reference differs from approved 1.8 authority: "
            + "; ".join(publication_errors)
        )
    reference_paths = {path.replace(f"{proposal_root}/", f"{policy['referenceRoot']}/", 1) for path in proposal_paths}
    segments = intentional_amendment_segments(
        repo, base, head, publication, str(contract["contractPath"]), reference_paths, policy
    )
    if segments["uiFiles"] != contract.get("changedFiles"):
        raise ValueError("intentional amendment contract omits a governed renderer path")
    return {
        **segments,
        "packetCommit": packet_commit,
        "approvalIntroduction": approval_introduction,
        "controlCandidate": predecessor["candidate"],
        "controlReviewIntroduction": predecessor["reviewIntroduction"],
        "referenceApprovalIntroduction": record_introduction,
        "publicationCommit": publication,
    }


def independent_identity(reviewer: object, owner: object) -> bool:
    """Match supported local agent task names without claiming human identity proof."""
    if not isinstance(reviewer, str) or AGENT_ID.fullmatch(reviewer) is None:
        return False

    def canonical(value: object) -> str:
        return re.sub(r"[^a-z0-9]", "", str(value).removeprefix("agent:").casefold())

    return canonical(reviewer) != canonical(owner)


def require_ordinary_submission_lineage(
    repo: Path,
    task: dict[str, Any],
    packet: dict[str, Any],
    previous: dict[str, Any] | None,
    delivery: str,
    introduction: str,
) -> None:
    expected_base = previous["candidate_commit"] if previous else task["base_sha"]
    base, candidate = packet.get("base_commit"), packet.get("candidate_commit")
    if (
        base != expected_base
        or packet.get("branch") != task.get("branch")
        or not isinstance(base, str)
        or not isinstance(candidate, str)
        or resolve_commit(repo, base) != base
        or resolve_commit(repo, candidate) != candidate
        or base == candidate
        or not is_ancestor(repo, base, candidate)
        or candidate == delivery
        or not is_ancestor(repo, candidate, delivery)
        or not is_ancestor(repo, delivery, introduction)
    ):
        raise ValueError("ordinary origin submission must preserve claim branch and strict candidate/delivery lineage")


def canonical_correction_evidence_path(identity: str, path: str) -> bool:
    prefix = re.escape(f"artifacts/evidence/{identity}")
    suffix = r"(?:-R(?:0[1-9]|[1-9][0-9]+))?(?:\.[A-Za-z0-9_-]+)*\.json"
    return re.fullmatch(prefix + suffix, path) is not None


def reference_activation_completion_segment(repo: Path, head: str, *, require_review: bool) -> dict[str, Any]:
    """Authenticate the one separately owner-approved final A05 source delivery."""
    prefix = "artifacts/evidence/W2.A05.S01.addendum-01"
    owner_path = "planning/wave-amendment-approvals/W2.A05.S01.addendum-01.json"
    paths = {
        "tools/ui_change_gate.py",
        "tests/foundation/test_ui_change_gate.py",
        "docs/automation/design-first-ui-changes.md",
        REFERENCE_ACTIVATION_REPAIR_ADR,
    }
    owner, owner_intro = immutable_record(repo, head, owner_path)
    if (
        owner.get("schemaVersion") != "1.0"
        or owner.get("documentType") != "wave-amendment-completion-scope-addendum"
        or owner.get("amendmentId") != "W2.A05"
        or owner.get("contributionId") != "W2.A05.S01"
        or owner.get("status") != "APPROVED"
        or HUMAN_ID.fullmatch(str(owner.get("approvedBy"))) is None
        or owner.get("baseApprovalCommit") != "b54f24c222f631700056574a08056f660696d305"
        or owner.get("authorizedSourcePaths") != sorted(paths)
        or commit_paths(repo, owner_intro) != {owner_path}
    ):
        raise ValueError("A05 completion has no exact independent owner source-delivery grant")
    proposal_ref, readiness_ref = owner.get("proposal"), owner.get("readinessReview")
    if (
        not isinstance(proposal_ref, dict)
        or proposal_ref.get("path") != prefix + ".proposal.json"
        or not isinstance(readiness_ref, dict)
        or readiness_ref.get("path") != prefix + ".readiness-review-01.json"
    ):
        raise ValueError("A05 completion owner grant has foreign proposal/readiness references")
    proposal, proposal_intro = immutable_record(
        repo, head, proposal_ref["path"], proposal_ref.get("sha256"), evidence=True
    )
    readiness, readiness_intro = immutable_record(
        repo, head, readiness_ref["path"], readiness_ref.get("sha256"), evidence=True
    )
    if (
        proposal.get("documentType") != "wave-amendment-completion-scope-addendum-proposal"
        or proposal.get("amendmentId") != "W2.A05"
        or proposal.get("contextCommit") != "a242167fdb73f958181ee45d8e83a134daf94caa"
        or set(proposal.get("authorizedSourcePaths", [])) != paths
        or readiness.get("documentType") != "wave-amendment-completion-addendum-readiness-review"
        or readiness.get("result") != "approved"
        or readiness.get("findings") != []
        or readiness.get("proposal") != proposal_ref
        or readiness.get("reviewedCandidateCommit") != proposal_intro
        or not independent_identity(readiness.get("reviewer"), "codex-w2-implementation")
        or proposal_intro == readiness_intro
        or not is_ancestor(repo, proposal_intro, readiness_intro)
        or owner.get("candidateAtDecision") != readiness_intro
        or resolve_commit(repo, f"{owner_intro}^") != readiness_intro
    ):
        raise ValueError("A05 completion proposal/readiness/owner order or binding differs")
    patch_ref = proposal.get("sourcePatch")
    if not isinstance(patch_ref, dict) or patch_ref.get("path") != prefix + ".source.patch":
        raise ValueError("A05 completion lacks its exact inert reviewed patch")
    patch_changes = git(repo, "log", "--format=%H", head, "--", patch_ref["path"]).decode().splitlines()
    if (
        patch_changes != [proposal_intro]
        or tree_entry(repo, head, patch_ref["path"]) != ("100644", "blob")
        or tree_entry(repo, f"{proposal_intro}^", patch_ref["path"]) is not None
        or hashlib.sha256(blob(repo, head, patch_ref["path"])).hexdigest() != patch_ref.get("sha256")
    ):
        raise ValueError("A05 completion patch was not frozen with its proposal")
    touches = (
        git(repo, "rev-list", "--reverse", f"{proposal['contextCommit']}..{head}", "--", *sorted(paths))
        .decode()
        .splitlines()
    )
    if len(touches) != 1:
        raise ValueError("A05 completion requires one source delivery and denies hidden add/revert")
    source = touches[0]
    if resolve_commit(repo, f"{source}^") != owner_intro or commit_paths(repo, source) != paths:
        raise ValueError("A05 completion source must separately follow its owner grant with the exact four paths")
    bindings = proposal.get("sourceBindings")
    if not isinstance(bindings, list) or [b.get("path") for b in bindings] != sorted(paths):
        raise ValueError("A05 completion source inventory differs")
    for binding in bindings:
        path = binding["path"]
        before, after = blob(repo, owner_intro, path), blob(repo, source, path)
        if (
            binding.get("mode") != "100644"
            or tree_entry(repo, source, path) != ("100644", "blob")
            or git(repo, "rev-parse", f"{owner_intro}:{path}").decode().strip() != binding.get("beforeGitBlob")
            or hashlib.sha256(before).hexdigest() != binding.get("beforeSha256")
            or hashlib.sha256(after).hexdigest() != binding.get("afterSha256")
            or before != blob(repo, proposal["contextCommit"], path)
            or blob(repo, head, path) != after
        ):
            raise ValueError("A05 completion substituted a reviewed source blob or mode")
    if blob(repo, source, "planning/backlog.yaml") != blob(repo, owner_intro, "planning/backlog.yaml"):
        raise ValueError("A05 completion source mixed a task or campaign mutation")
    if not blob(repo, source, REFERENCE_ACTIVATION_REPAIR_ADR).startswith(
        blob(repo, owner_intro, REFERENCE_ACTIVATION_REPAIR_ADR)
    ):
        raise ValueError("A05 completion rewrote its Proposed ADR history")
    if require_review:
        manifest_path, ledger_path = prefix + ".execution.json", prefix + ".execution.review-01.json"
        manifest, delivery = immutable_record(repo, head, manifest_path, evidence=True)
        ledger, review_intro = immutable_record(repo, head, ledger_path, evidence=True)
        expected = {
            "path": manifest_path,
            "introductionCommit": delivery,
            "gitBlob": git(repo, "rev-parse", f"{delivery}:{manifest_path}").decode().strip(),
            "sha256": hashlib.sha256(blob(repo, delivery, manifest_path).replace(b"\r\n", b"\n")).hexdigest(),
        }
        if (
            manifest.get("documentType") != "wave-amendment-completion-source-evidence"
            or manifest.get("amendmentId") != "W2.A05"
            or manifest.get("candidateCommit") != source
            or manifest.get("sourceBindings") != bindings
            or not isinstance(manifest.get("checks"), list)
            or not manifest["checks"]
            or any(c.get("result") != "passed" or c.get("exitCode") != 0 for c in manifest["checks"])
            or ledger.get("documentType") != "wave-amendment-completion-source-independent-review"
            or ledger.get("amendmentId") != "W2.A05"
            or ledger.get("reviewedManifest") != expected
            or ledger.get("result") != "approved"
            or ledger.get("findings") != []
            or not independent_identity(ledger.get("reviewer"), "codex-w2-implementation")
            or source == delivery
            or delivery == review_intro
            or not is_ancestor(repo, source, delivery)
            or not is_ancestor(repo, delivery, review_intro)
        ):
            raise ValueError("A05 completion source lacks separate exact-candidate evidence and independent review")
    return {"commits": {source: paths}, "sourceCommit": source, "ownerCommit": owner_intro}


def reference_activation_completion_review_commit(
    repo: Path, head: str, task: dict[str, Any], packet: dict[str, Any], introduction: str, index: int
) -> str:
    """Recognize only the two exact authentic ledger-first A05 R01 histories."""
    pairs = {
        "W2.A05.T01": ("e0580f8e6b33be13c6ee515ea20ea4e7b6133535", "a1105c306178b6c5f10d0107f244d3e14e2d401d"),
        "W2.A05.T02": ("381f1e992bfc60aebfe2f73f2470e6710ceba935", "a242167fdb73f958181ee45d8e83a134daf94caa"),
    }
    pair = pairs.get(str(task["id"]))
    if pair is None or index != 1 or introduction != pair[0]:
        return introduction
    reference_activation_completion_segment(repo, head, require_review=False)
    if resolve_commit(repo, f"{pair[1]}^") != introduction or not is_ancestor(repo, pair[1], head):
        raise ValueError("A05 completion review is not its exact direct-child publication")
    before = reference_activation_repair_state(repo, introduction)
    after = reference_activation_repair_state(repo, pair[1])
    introduced = backlog_task(before, task["id"]) or {}
    published = backlog_task(after, task["id"]) or {}
    if (
        introduced.get("status") != "REVIEW"
        or introduced.get("review_control", {}).get("current_submission") != packet
        or introduced.get("review_control", {}).get("attempts") != []
        or published.get("status") != "DONE"
        or published.get("lease") is not None
        or published.get("review_control", {}).get("current_submission") is not None
        or published.get("review_control", {}).get("attempts") != task["review_control"]["attempts"][:1]
        or any(
            introduced.get(k) != published.get(k) or published.get(k) != task.get(k)
            for k in (
                "id",
                "amendment_id",
                "owner",
                "branch",
                "worktree",
                "base_sha",
                "packet_task_sha256",
                "acceptance_criteria",
            )
        )
    ):
        raise ValueError("A05 completion review changed its frozen packet, prefix, identity or exact disposition")
    frozen_before, frozen_after = copy.deepcopy(before), copy.deepcopy(after)
    if task["id"] == "W2.A05.T01":
        before_sibling = backlog_task(frozen_before, "W2.A05.T02") or {}
        after_sibling = backlog_task(frozen_after, "W2.A05.T02") or {}
        if before_sibling.get("status") != "NOT_STARTED" or after_sibling.get("status") != "READY":
            raise ValueError("A05 completion changed the exact derived T02 readiness transition")
        for sibling in (before_sibling, after_sibling):
            sibling.pop("status")
            sibling.pop("updated_at")
    for state in (frozen_before, frozen_after):
        child = amendment_record(state, "W2.A05")
        child["tasks"] = [t for t in child["tasks"] if t["id"] != task["id"]]
    if frozen_before != frozen_after:
        raise ValueError("A05 completion review changed unrelated authority or sibling records")
    return pair[1]


def correction_submission_ranges(
    repo: Path, head: str, correction: dict[str, Any], *, ordinary_origin: bool = False
) -> list[dict[str, Any]]:
    from taskctl import task_review_control_errors

    ranges: list[dict[str, Any]] = []
    for task in correction["tasks"]:
        identity = str(task["id"])
        attempts = (task.get("review_control") or {}).get("attempts") or []
        if (
            task.get("status") != "DONE"
            or not attempts
            or task_review_control_errors(task, None)
            or task.get("review", {}).get("result") != "approved"
        ):
            raise ValueError("correction requires completed independently approved task submissions")
        for index, attempt in enumerate(attempts, start=1):
            packet, review = attempt["submission"], attempt["review"]
            if not independent_identity(review.get("reviewer"), task.get("owner")):
                raise ValueError("correction task review is not independent")
            ledger_ref = attempt["ledger"]
            ledger_path = f"artifacts/evidence/{identity}.review-R{index:02d}.json"
            if ledger_ref.get("path") != ledger_path:
                raise ValueError("correction task review path is not canonical")
            ledger, introduction = immutable_record(repo, head, ledger_path, ledger_ref.get("sha256"), evidence=True)
            expected = {
                "task_id": identity,
                "attempt_id": packet["id"],
                "candidate_commit": packet["candidate_commit"],
                "reviewer": review["reviewer"],
                "result": review["result"],
                "notes": review["notes"],
                "findings": attempt["findings"],
                "closures": attempt["closures"],
            }
            if any(ledger.get(key) != value for key, value in expected.items()):
                raise ValueError("correction task ledger differs from its frozen review")
            publication = reference_activation_completion_review_commit(repo, head, task, packet, introduction, index)
            before = yaml_object(
                blob(repo, resolve_commit(repo, f"{publication}^"), "planning/backlog.yaml"), "review predecessor"
            )
            after = yaml_object(blob(repo, publication, "planning/backlog.yaml"), "review projection")
            prior_task = backlog_task(before, identity) or {}
            reviewed_task = backlog_task(after, identity) or {}
            separately_submitted = (
                prior_task.get("status") == "REVIEW"
                and (prior_task.get("review_control") or {}).get("current_submission") == packet
            )
            # Ordinary taskctl submit/review may be committed together. Its
            # immutable packet and independent ledger still bind the candidate;
            # the historical amendment lane keeps its distinct-commit rule.
            ordinary_delivery = (
                ordinary_origin
                and re.fullmatch(r"CAP-[0-9]{2}\.S[0-9]{2}\.T[0-9]{2}", identity) is not None
                and task.get("amendment_id") is None
                and prior_task.get("status") == "IN_PROGRESS"
                and prior_task.get("owner") == task.get("owner")
                and prior_task.get("base_sha") == task.get("base_sha")
                and all(
                    prior_task.get(field) == task.get(field)
                    for field in (
                        "branch",
                        "worktree",
                        "platform_targets",
                        "deployment_profiles",
                        "verification_profiles",
                        "review_gate",
                        "experience_change",
                        "title",
                        "objective",
                        "dependencies",
                        "acceptance_criteria",
                        "verification_commands",
                    )
                )
                and (prior_task.get("review_control") or {}).get("current_submission") is None
                and (prior_task.get("review_control") or {}).get("attempts", []) == attempts[: index - 1]
            )
            if (
                not (separately_submitted or ordinary_delivery)
                or (reviewed_task.get("review_control") or {}).get("attempts") != attempts[:index]
                or not is_ancestor(repo, packet["candidate_commit"], introduction)
            ):
                raise ValueError("correction task review is not its actual frozen-submission transition")
            reference = packet["evidence_reference"]
            path = str(reference.get("path"))
            if not canonical_correction_evidence_path(identity, path):
                raise ValueError("correction task evidence path is outside its exact namespace")
            manifest, delivery = immutable_record(repo, head, path, reference.get("sha256"), evidence=True)
            if ordinary_origin:
                require_ordinary_submission_lineage(
                    repo, task, packet, attempts[index - 2]["submission"] if index > 1 else None, delivery, introduction
                )
            if (
                not is_ancestor(repo, delivery, introduction)
                or any(
                    manifest.get(key) != packet.get(other)
                    for key, other in (
                        ("taskId", "task_id"),
                        ("commit", "candidate_commit"),
                        ("baseCommit", "base_commit"),
                        ("changedFiles", "changed_paths"),
                        ("branch", "branch"),
                    )
                    if key != "taskId"
                )
                or manifest.get("taskId") != identity
            ):
                raise ValueError("correction task evidence differs from its reviewed submission")
            ranges.append(
                {
                    "base": packet["base_commit"],
                    "candidate": packet["candidate_commit"],
                    "paths": packet["changed_paths"],
                }
            )
    return ranges


def correction_exit_errors(repo: Path, head: str, correction: dict[str, Any], packet: dict[str, Any]) -> list[str]:
    from taskctl import amendment_exit_submission_errors

    identity = str(correction["id"])
    completion = correction.get("completion") or {}
    control = completion.get("exit_review_control") or {}
    attempts = control.get("attempts") or []
    if completion.get("status") != "APPROVED" or not attempts or control.get("current_submission") is not None:
        return ["correction lacks completed independent exit qualification"]
    errors: list[str] = []
    open_findings: dict[str, dict[str, Any]] = {}
    previous: dict[str, Any] | None = None
    for index, attempt in enumerate(attempts, start=1):
        submission, review = attempt["submission"], attempt["review"]
        state_commit = review["reviewed_state_commit"]
        state = yaml_object(blob(repo, state_commit, "planning/backlog.yaml"), "exit frozen state")
        historical = amendment_record(state, identity)
        if historical["completion"]["exit_review_control"][
            "current_submission"
        ] != submission or not independent_identity(review.get("reviewer"), correction["campaign"].get("owner")):
            errors.append("correction exit does not bind an independently reviewed frozen state")
        expected_path = f"artifacts/evidence/{identity}.exit-review-R{index:02d}.json"
        if attempt["ledger"].get("path") != expected_path:
            errors.append("correction exit ledger path is not canonical")
            continue
        ledger, introduction = immutable_record(
            repo, head, expected_path, attempt["ledger"].get("sha256"), evidence=True
        )
        if not is_ancestor(repo, state_commit, introduction) or any(
            ledger.get(key) != value
            for key, value in {
                "amendment_id": identity,
                "attempt_id": submission["id"],
                "reviewed_state_commit": state_commit,
                "candidate_commit": submission["candidate_commit"],
                "reviewer": review["reviewer"],
                "result": review["result"],
                "findings": attempt["findings"],
                "closures": attempt["closures"],
            }.items()
        ):
            errors.append("correction exit ledger identity, finding or candidate substitution")
        introduced = amendment_record(
            yaml_object(blob(repo, introduction, "planning/backlog.yaml"), "exit disposition"), identity
        )
        if introduced["completion"]["exit_review_control"]["attempts"] != attempts[:index]:
            errors.append("correction exit review is not its actual introduced projection")
        evidence_path = str(submission["evidence_reference"].get("path"))
        if not evidence_path.startswith(f"artifacts/evidence/{identity}.exit") or not evidence_path.endswith(".json"):
            errors.append("correction exit evidence is outside its namespace")
            continue
        immutable_record(repo, head, evidence_path, submission["evidence_reference"].get("sha256"), evidence=True)
        errors.extend(
            amendment_exit_submission_errors(
                state,
                historical,
                packet,
                submission,
                expected_id=f"R{index:02d}",
                expected_prior_id=previous["id"] if previous else None,
                expected_prior_submission=previous,
                expected_open_ids=sorted(open_findings),
                repo=repo,
                strict_state=True,
            )
        )
        for closure in attempt["closures"]:
            if closure["finding_id"] not in open_findings:
                errors.append("correction exit closure does not name an open finding")
            open_findings.pop(closure["finding_id"], None)
        for finding in attempt["findings"]:
            if finding["id"] in open_findings:
                errors.append("correction exit finding identity is duplicated")
            open_findings[finding["id"]] = finding
        if review["result"] == "approved" and any(item.get("blocking") for item in open_findings.values()):
            errors.append("correction exit approval retains a blocking finding")
        previous = submission
    if attempts[-1]["review"].get("result") != "approved":
        errors.append("correction latest exit is not approved")
    return errors


def require_resumed_hold(
    backlog: dict[str, Any],
    parent: dict[str, Any],
    correction_id: str,
    owner: object,
    projections: list[dict[str, Any]],
) -> None:
    """The current campaign and derived hold must agree, not just old anchors."""
    identity = parent["id"]
    campaign = parent.get("campaign") or {}
    relation = [item for item in projections if item.get("correctionId") == correction_id]
    expected_relation = {
        "parentId": identity,
        "correctionId": correction_id,
        "phase": "returned",
        "holdOwner": identity,
        "parentFrozen": False,
    }
    active = [
        item.get("id")
        for item in backlog.get("wave_amendments", [])
        if (item.get("campaign") or {}).get("status") in {"ACTIVE", "REVIEW"}
    ]
    if (
        parent.get("lifecycle", {}).get("status") != "ACTIVE"
        or campaign.get("status") != "ACTIVE"
        or campaign.get("scope") != "wave-amendment"
        or not isinstance(owner, str)
        or not owner
        or campaign.get("owner") != owner
        or (campaign.get("lease") or {}).get("claimed_by") != owner
        or backlog.get("control_plane", {}).get("active_amendment") != identity
        or relation != [expected_relation]
        or active != [identity]
    ):
        raise ValueError("resumed amendment current lifecycle, owner, lease and derived hold must agree")


def resumed_amendment_authority(
    repo: Path, base: str, head: str, contract: dict[str, Any], policy: dict[str, Any]
) -> dict[str, Any]:
    """Authenticate the bounded existing correction relation, without mutation.

    Narrow planctl helpers currently resolve clean authority at HEAD, so this
    opt-in lane intentionally requires HEAD. Legacy historical ranges do not.
    """
    from governance_kernel import project_paused_corrections, validate_returned_predecessor_history
    from planctl import _adoption_transition_errors, _paused_predecessor_errors, _reference_publication_content_errors
    from taskctl import amendment_adoption_checkpoints, amendment_adoption_reference_errors

    if head != resolve_commit(repo, "HEAD") or contract.get("changeKind") != "defect-restoration":
        raise ValueError("resumed amendment restoration requires current HEAD and defect-restoration")
    authority = contract["amendmentAuthority"]
    cache: dict[str, dict[str, Any]] = {}

    def state(commit: str) -> dict[str, Any]:
        if commit not in cache:
            cache[commit] = yaml_object(blob(repo, commit, "planning/backlog.yaml"), "amendment state")
        return cache[commit]

    backlog = state(head)
    task = backlog_task(backlog, contract["taskId"])
    if task is None or not task.get("amendment_id") or task.get("base_sha") != base:
        raise ValueError("resumed authority requires the original claimed amendment task/base")
    parent = amendment_record(backlog, task["amendment_id"])
    correction = amendment_record(backlog, authority["correctionId"])
    projections = project_paused_corrections(backlog["wave_amendments"])
    require_resumed_hold(backlog, parent, correction["id"], task.get("owner"), [dict(item) for item in projections])
    wave_id = parent["target_wave"]
    wave_amendments = [item for item in backlog["wave_amendments"] if item["target_wave"] == wave_id]
    if wave_amendments[-2:] != [parent, correction] or "correction" in parent:
        raise ValueError("resumed authority supports one immediate correction only")
    parent_packet, parent_packet_commit, parent_approval = approved_amendment_packet(repo, head, parent)
    packet, packet_commit, correction_approval = approved_amendment_packet(repo, head, correction)
    binding = packet.get("authorityChain", {}).get("pausedPredecessor")
    if (
        not isinstance(binding, dict)
        or binding != correction.get("correction")
        or binding.get("id") != parent["id"]
        or binding.get("packetCommit") != parent_packet_commit
        or not is_ancestor(repo, parent_approval, base)
    ):
        raise ValueError("correction does not bind the existing approved paused parent")
    pause = binding["effectiveStateCommit"]
    adoption, activation = authority["adoptionCommit"], authority["reactivationCommit"]
    anchors = [base, pause, packet_commit, correction_approval, adoption, activation, head]
    if any(resolve_commit(repo, value) != value for value in anchors) or any(
        left == right or not is_ancestor(repo, left, right) for left, right in pairwise(anchors)
    ):
        raise ValueError("resumed amendment anchors are not strictly ordered canonical ancestors")
    paused = amendment_record(state(pause), parent["id"])
    returned = amendment_record(state(adoption), parent["id"])
    errors = _paused_predecessor_errors(repo, binding, correction["id"], returned_parent=returned)
    errors.extend(_adoption_transition_errors(repo, correction["id"], adoption))
    if errors:
        raise ValueError("; ".join(errors))
    if returned != paused or amendment_record(state(adoption), correction["id"]) != correction:
        raise ValueError("correction adoption did not return the exact PAUSED parent or retained correction changed")
    if correction["lifecycle"].get("status") != "ADOPTED":
        raise ValueError("correction is not actually adopted")
    active = amendment_record(state(activation), parent["id"])
    prior_active = amendment_record(state(resolve_commit(repo, f"{activation}^")), parent["id"])
    active_task = backlog_task(state(activation), task["id"]) or {}
    if (
        prior_active != returned
        or active["lifecycle"].get("status") != "ACTIVE"
        or active["campaign"].get("status") != "ACTIVE"
        or active_task.get("status") != "IN_PROGRESS"
        or active_task.get("base_sha") != base
        or active_task.get("owner") != task.get("owner")
        or active["campaign"].get("base_sha") != adoption
    ):
        raise ValueError("missing exact explicit parent activation and original task reopen")
    for current in (active, parent):
        validate_returned_predecessor_history(paused, current)
        for field in ("id", "change_request_id", "target_wave", "kind", "approval_reference", "contributions"):
            if current.get(field) != paused.get(field):
                raise ValueError("resumed parent immutable authority/contribution changed")
        current_task = next(item for item in current["tasks"] if item["id"] == task["id"])
        paused_task = next(item for item in paused["tasks"] if item["id"] == task["id"])
        for field in (
            "packet_task_sha256",
            "title",
            "objective",
            "dependencies",
            "acceptance_criteria",
            "verification_commands",
            "base_sha",
            "started_at",
            "owner",
            "branch",
            "worktree",
        ):
            if current_task.get(field) != paused_task.get(field):
                raise ValueError(f"resumed task immutable field changed: {field}")
        prior_evidence = paused_task.get("evidence", [])
        if current_task.get("evidence", [])[: len(prior_evidence)] != prior_evidence:
            raise ValueError("resumed task removed prior evidence")
    original_wave = next(item for item in state(pause)["waves"] if item["id"] == wave_id)
    for commit in (adoption, activation, head):
        document = state(commit)
        wave = next(item for item in document["waves"] if item["id"] == wave_id)
        if (
            wave["campaign"] != original_wave["campaign"]
            or document.get("gates") != state(pause).get("gates")
            or document.get("capabilities") != state(pause).get("capabilities")
        ):
            raise ValueError("resumed amendment changed ordinary Wave/task/release authority")
    adopted_wave = next(item for item in state(adoption)["waves"] if item["id"] == wave_id)
    checkpoints = amendment_adoption_checkpoints(adopted_wave, correction["id"])
    if len(checkpoints) != 1:
        raise ValueError("correction adoption requires exactly one bound checkpoint")
    references = [item for item in checkpoints[0]["evidence"] if item.get("amendment_id") == correction["id"]]
    if len(references) != 1 or references[0].get("path") != f"artifacts/evidence/{correction['id']}.adoption.json":
        raise ValueError("correction adoption evidence namespace differs")
    _adoption_record, delivery = immutable_record(
        repo, head, references[0]["path"], references[0].get("sha256"), evidence=True
    )
    if not is_ancestor(repo, delivery, adoption) or delivery == adoption:
        raise ValueError("correction checkpoint evidence must precede adoption")
    errors = amendment_adoption_reference_errors(repo, references[0], correction)
    errors.extend(correction_exit_errors(repo, head, correction, packet))
    if errors:
        raise ValueError("; ".join(errors))
    ranges = correction_submission_ranges(repo, head, correction)
    segments = restoration_segments(repo, base, head, activation, ranges, policy)
    for field in ("inheritedCorrectionUiFiles", "resumedUiFiles"):
        if authority.get(field) != segments[field]:
            raise ValueError(f"resumed authority {field} differs from per-commit attribution")

    publication = contract["reference"]["approvalCommit"]
    publication_state, errors = reference_state(repo, publication, policy)
    errors.extend(_reference_publication_content_errors(repo, packet, packet_commit, publication))
    current_reference, current_errors = reference_state(repo, head, policy)
    errors.extend(current_errors)
    reference_commits = (
        git(repo, "log", "--format=%H", f"{base}..{head}", "--", policy["referenceRoot"]).decode().splitlines()
    )
    published_authority = publication_state.get("approval", {}).get("authority", {})
    approval_record = json_object(blob(repo, head, correction["approval_reference"]["path"]), "correction approval")
    publication_approval = publication_state.get("approval", {})
    expected_approver = "human:" + str(approval_record.get("approvedBy")).removeprefix("human:")
    expected_authority = {
        "amendment_id": correction["id"],
        "change_request_id": correction["change_request_id"],
        "approval_record": correction["approval_reference"]["path"],
        "approval_record_sha256": correction["approval_reference"]["sha256"],
        "approval_record_introduction_commit": correction_approval,
    }
    if (
        errors
        or reference_commits != [publication]
        or publication_state != current_reference
        or published_authority != expected_authority
        or publication_approval.get("approval_kind") != "human"
        or publication_approval.get("approved_by") != expected_approver
        or HUMAN_ID.fullmatch(expected_approver) is None
        or publication_state.get("referenceId") != packet.get("governedExperience", {}).get("referenceId")
        or publication_approval.get("supersedes") != parent_packet.get("governedExperience", {}).get("referenceId")
        or not is_ancestor(repo, correction_approval, publication)
        or any(
            commit == publication or not is_ancestor(repo, publication, commit)
            for commit in segments["inheritedUiCommits"] + segments["resumedUiCommits"]
        )
    ):
        raise ValueError("correction reference publication/content/order is not authentic: " + "; ".join(errors))
    # The superseded parent's package is read from its approved Git snapshot;
    # it is never rewritten to make its old task look newly approved.
    for reference in parent_packet.get("governedExperience", {}).get("files", []):
        path = str(reference["path"])
        if path.startswith(f"{policy['referenceRoot']}/"):
            payload = blob(repo, parent_packet_commit, path)
            if hashlib.sha256(payload).hexdigest() != reference["sha256"] or blob(repo, base, path) != payload:
                raise ValueError("superseded parent reference no longer matches its approved original base")
    return {
        **segments,
        "correctionSubmissionRanges": ranges,
        "parentPacketCommit": parent_packet_commit,
        "correctionPacketCommit": packet_commit,
        "adoptionCommit": adoption,
        "reactivationCommit": activation,
        "taskDefinitionSha256": task["packet_task_sha256"],
    }


def restoration_classification_errors(
    repo: Path, base: str, head: str, contract: dict[str, Any], scope: dict[str, Any], policy: dict[str, Any]
) -> list[str]:
    """Bind independent semantic judgment; hashes alone cannot classify a UX fix."""
    reference = (
        contract["restorationClassification"]
        if "restorationClassification" in contract
        else contract["amendmentAuthority"]["classification"]
    )
    identity = contract["taskId"]
    path = str(reference["path"])
    if not re.fullmatch(re.escape(f"artifacts/evidence/{identity}.ui-classification-R") + r"[0-9]{2}\.json", path):
        return ["restoration classification must use the exact task namespace"]
    record, introduction = immutable_record(repo, head, path, reference["sha256"])
    candidate = str(record.get("candidateCommit"))
    expected = {
        "schemaVersion": "1.0",
        "documentType": "independent-ui-restoration-disposition",
        "taskId": identity,
        "baseCommit": base,
        "disposition": "approved",
        "taskDefinitionSha256": scope["taskDefinitionSha256"],
        "referencePackageSha256": contract["reference"]["packageSha256"],
        "resumedUiFiles": scope["resumedUiFiles"],
        "resumedUiCommits": scope["resumedUiCommits"],
        "approvedTaskAllowsRestoration": True,
        "authorityPreserved": True,
        "formalTaskApproval": False,
    }
    if (
        reference["commit"] != introduction
        or not independent_identity(record.get("reviewer"), contract["implementationAgent"])
        or any(record.get(key) != value for key, value in expected.items())
        or record.get("approvedTaskAllowsRestoration") is not True
        or record.get("authorityPreserved") is not True
        or record.get("formalTaskApproval") is not False
        or not str(record.get("normativeRationale") or "").strip()
        or not is_ancestor(repo, scope["reactivationCommit"], candidate)
        or candidate == introduction
        or not is_ancestor(repo, candidate, introduction)
    ):
        return ["restoration lacks exact independent approved-task/source classification"]
    # Reverted edits also invalidate an old classification. Later control-only
    # commits are permitted, but any later UI or reference edit needs a new one.
    for commit in git(repo, "rev-list", f"{candidate}..{head}").decode().splitlines():
        if any(
            is_implementation_path(item, policy)
            or item.startswith(f"{policy['referenceRoot']}/")
            or item in scope.get("correctionProductPaths", [])
            for item in commit_paths(repo, commit)
        ):
            return ["restoration classification is stale after a product/reference change"]
    capture = record.get("captures") or {}
    visual = record.get("visualReview") or {}
    if not re.fullmatch(
        re.escape(f"artifacts/evidence/{identity}.captures-") + r"[0-9]{2}/manifest\.json", str(capture.get("path"))
    ) or not re.fullmatch(
        re.escape(f"artifacts/evidence/{identity}.visual-review-") + r"[0-9]{2}\.json", str(visual.get("path"))
    ):
        return ["restoration classification capture/visual evidence namespace is invalid"]
    manifest, capture_intro = immutable_record(repo, head, capture["path"], capture.get("sha256"))
    disposition, visual_intro = immutable_record(repo, head, visual["path"], visual.get("sha256"))
    visual_findings = disposition.get("findings")
    if not isinstance(visual_findings, list) or any(
        not isinstance(finding, dict) or finding.get("blockingVisualAcceptance") is not False
        for finding in visual_findings
    ):
        return ["restoration visual disposition retains blocking or unclassified findings"]
    producer = manifest.get("producer") or {}
    bindings = disposition.get("bindings") or {}
    if (
        capture.get("deliveryCommit") != capture_intro
        or visual.get("commit") != visual_intro
        or not is_ancestor(repo, capture_intro, visual_intro)
        or not is_ancestor(repo, visual_intro, introduction)
        or producer.get("producerCommit") != candidate
        or manifest.get("documentType") != "product-style-capture-bundle"
        or manifest.get("schemaVersion") != "1.0"
        or producer.get("referencePackageSha256") != expected["referencePackageSha256"]
        or disposition.get("documentType") != "independent-product-visual-disposition"
        or disposition.get("taskId") != identity
        or disposition.get("disposition") != "approved"
        or not independent_identity(disposition.get("reviewer"), contract["implementationAgent"])
        or bindings.get("producerCommit") != candidate
        or bindings.get("manifest") != capture["path"]
        or bindings.get("manifestSha256") != capture["sha256"]
        or bindings.get("captureDeliveryCommit") != capture_intro
        or bindings.get("referencePackageSha256") != expected["referencePackageSha256"]
    ):
        return ["restoration visual/capture disposition is not bound to the classified producer/reference"]
    for item in scope["resumedUiFiles"]:
        entry = git(repo, "rev-parse", f"{candidate}:{item}").decode().strip()
        if producer.get("inputGitBlobs", {}).get(item) != entry or blob(repo, candidate, item) != blob(
            repo, head, item
        ):
            return ["restoration captures do not contain the classified current product inputs"]
    from desktop_app_check import qualification_capture_contract, qualification_report_errors
    from product_style_check import read_capture_bundle

    # Reuse the existing confined, locked, delivery-bound PNG inventory reader;
    # do not invent a weaker second capture validator in this authority guard.
    authenticated = read_capture_bundle(
        repo, repo / capture["path"], capture_intro, qualification_capture_contract(repo)
    )
    if authenticated != manifest:
        return ["restoration capture snapshot differs from its immutable record"]
    if "restorationClassification" in contract:
        from product_style_check import capture_producer_snapshot

        # This includes the real Core, generated/companion contracts, renderer,
        # build and checker inputs. A retained PNG inventory alone is not the
        # current producer's conformance proof. Intermediate add/revert edits
        # also invalidate the independent judgment, even if final bytes match.
        if producer != capture_producer_snapshot(repo, candidate):
            return ["linked restoration capture producer differs from current authenticated inputs"]
        inputs = set(producer.get("inputGitBlobs", {})) | set(scope.get("correctionProductPaths", []))
        for commit in git(repo, "rev-list", f"{candidate}..{head}").decode().splitlines():
            if commit_paths(repo, commit) & inputs:
                return ["linked restoration classification is stale after a dependent input change"]
    measurement_errors = qualification_report_errors(repo, authenticated["report"])
    if measurement_errors:
        return ["restoration capture measurements fail conformance: " + "; ".join(measurement_errors)]
    if any(
        is_implementation_path(item, policy) or item in GATE_CONTROL_PATHS for item in commit_paths(repo, introduction)
    ):
        return ["independent classification introduction must not implement product or gate changes"]
    return []


def adopted_continuation_reviewed_maintenance(repo: Path, head: str) -> dict[str, set[str]]:
    """Return only the two exact independently reviewed historical control chains."""

    verifier_path = "artifacts/evidence/W2.reference-approval-verifier-repair.review.md"
    verifier_review = blob(repo, head, verifier_path)
    verifier_introductions = git(repo, "log", "--format=%H", head, "--", verifier_path).decode().splitlines()
    verifier_source_paths = {
        "artifacts/evidence/W2.reference-approval-verifier-repair.md",
        "docs/adr/ADR-0036-verify-exact-amendment-reference-approval-metadata.md",
        "docs/adr/index.json",
        "tests/desktop/test_ui_conformance.py",
        "tools/ui_conformance.py",
    }
    if (
        verifier_introductions != [ADOPTED_CONTINUATION_VERIFIER_REVIEW]
        or hashlib.sha256(verifier_review).hexdigest() != ADOPTED_CONTINUATION_VERIFIER_REVIEW_SHA256
        or commit_paths(repo, ADOPTED_CONTINUATION_VERIFIER_CANDIDATE) != verifier_source_paths
        or commit_paths(repo, ADOPTED_CONTINUATION_VERIFIER_REVIEW) != {verifier_path}
        or not is_ancestor(repo, ADOPTED_CONTINUATION_VERIFIER_CANDIDATE, ADOPTED_CONTINUATION_VERIFIER_REVIEW)
        or not is_ancestor(repo, ADOPTED_CONTINUATION_VERIFIER_REVIEW, head)
    ):
        raise ValueError("adopted continuation lacks exact independent verifier repair review")

    gate_path = "artifacts/evidence/W2.A01.T02.ui-gate-active-maintenance.review-01.json"
    gate_review, gate_introduction = immutable_record(repo, head, gate_path, ADOPTED_CONTINUATION_GATE_REVIEW_SHA256)
    gate_base = "f306579cd802ae22576db35a735101a4d92c1215"
    if (
        gate_introduction != ADOPTED_CONTINUATION_GATE_REVIEW
        or gate_review.get("documentType") != "bounded-control-maintenance-independent-review"
        or gate_review.get("result") != "approved"
        or gate_review.get("findings") != []
        or gate_review.get("candidateCommit") != ADOPTED_CONTINUATION_GATE_CHAIN[-1]
        or gate_review.get("baseCommit") != gate_base
        or (gate_review.get("scope") or {}).get("commits") != list(ADOPTED_CONTINUATION_GATE_CHAIN)
        or not independent_identity(gate_review.get("reviewer"), "codex-w2-implementation")
        or git(repo, "rev-list", "--reverse", f"{gate_base}..{ADOPTED_CONTINUATION_GATE_CHAIN[-1]}")
        .decode()
        .splitlines()
        != list(ADOPTED_CONTINUATION_GATE_CHAIN)
        or not is_ancestor(repo, ADOPTED_CONTINUATION_GATE_CHAIN[-1], gate_introduction)
    ):
        raise ValueError("adopted continuation lacks exact independently reviewed active UI gate chain")
    gate_paths = set().union(*(commit_paths(repo, commit) for commit in ADOPTED_CONTINUATION_GATE_CHAIN))
    if sorted(gate_paths) != (gate_review.get("scope") or {}).get("changedPaths"):
        raise ValueError("adopted continuation gate-chain paths differ from independent review")
    admitted = {ADOPTED_CONTINUATION_VERIFIER_CANDIDATE: verifier_source_paths}
    admitted.update({commit: commit_paths(repo, commit) for commit in ADOPTED_CONTINUATION_GATE_CHAIN})
    return admitted


def reference_activation_historical_t03_authority(
    repo: Path, head: str, backlog: dict[str, Any]
) -> dict[str, set[str]]:
    """Admit three frozen, reviewed T03 product/control commits across its R01-R03 range."""

    identity = "CAP-04.S05.T03"
    task = backlog_task(backlog, identity)
    frozen = yaml_object(
        blob(repo, REFERENCE_ACTIVATION_PACKET_COMMIT, "planning/backlog.yaml"), "ECR-0011 T03 predecessor"
    )
    if task is None or task != backlog_task(frozen, identity):
        raise ValueError("reference activation changed the ECR-0011-frozen CAP-04.S05.T03 task")
    attempts = (task.get("review_control") or {}).get("attempts") or []
    if (
        task.get("status") != "DONE"
        or task.get("review", {}).get("result") != "approved"
        or [(item["submission"]["id"], item["review"]["result"]) for item in attempts]
        != [("R01", "changes-requested"), ("R02", "changes-requested"), ("R03", "approved")]
    ):
        raise ValueError("reference activation lacks the frozen independently reviewed T03 disposition")
    ranges = correction_submission_ranges(repo, head, {"tasks": [task]}, ordinary_origin=True)
    if [(item["base"], item["candidate"]) for item in ranges] != list(REFERENCE_ACTIVATION_T03_RANGES):
        raise ValueError("reference activation T03 R01-R03 ranges differ from frozen history")
    for attempt in attempts:
        review_path = attempt["ledger"]["path"]
        _, introduction = immutable_record(repo, head, review_path, attempt["ledger"]["sha256"], evidence=True)
        if not is_ancestor(repo, introduction, REFERENCE_ACTIVATION_PACKET_COMMIT):
            raise ValueError("reference activation T03 review postdates the approved packet")
    commits: dict[str, set[str]] = {}
    expected_lengths = (6, 3, 3)
    for (base, candidate), reviewed, length in zip(
        REFERENCE_ACTIVATION_T03_RANGES, ranges, expected_lengths, strict=True
    ):
        rows = git(repo, "rev-list", "--reverse", "--parents", f"{base}..{candidate}").decode().splitlines()
        if len(rows) != length or reviewed["paths"] != sorted(changed_paths(repo, base, candidate)):
            raise ValueError("reference activation T03 reviewed path inventory differs from Git")
        previous = base
        for row in rows:
            values = row.split()
            if len(values) != 2 or values[1] != previous:
                raise ValueError("reference activation T03 reviewed history is not linear")
            commit = values[0]
            paths = commit_paths(repo, commit)
            for path in paths:
                entry = tree_entry(repo, commit, path)
                if entry != ("100644", "blob") and not (
                    commit == REFERENCE_ACTIVATION_T03_SOURCE_COMMITS[1]
                    and path in REFERENCE_ACTIVATION_T03_MOVED_PATHS
                    and entry is None
                ):
                    raise ValueError("reference activation T03 source has an unreviewed mode or deletion")
            commits[commit] = paths
            previous = commit
        if previous != candidate:
            raise ValueError("reference activation T03 reviewed candidate is not its range tip")
    initial, moved, indexed = REFERENCE_ACTIVATION_T03_SOURCE_COMMITS
    if (
        not set(REFERENCE_ACTIVATION_T03_SOURCE_COMMITS).issubset(commits)
        or "quality-scope.json" not in commits[initial]
        or "docs/adr/index.json" not in commits[indexed]
        or len(commits[initial]) != 26
        or len(commits[moved]) != 23
        or len(commits[indexed]) != 3
        or {path for path in commits[moved] if tree_entry(repo, moved, path) is None}
        != REFERENCE_ACTIVATION_T03_MOVED_PATHS
    ):
        raise ValueError("reference activation T03 exact mixed source anchors differ")
    for old in REFERENCE_ACTIVATION_T03_MOVED_PATHS:
        new = old.replace("plugins/connectors/sample_repository/", "docs/developer/sample_repository/", 1)
        if (
            tree_entry(repo, resolve_commit(repo, f"{initial}^"), old) is not None
            or blob(repo, initial, old) != blob(repo, moved, new)
            or tree_entry(repo, moved, new) != ("100644", "blob")
        ):
            raise ValueError("reference activation T03 temporary sample source was not moved unchanged")
    relevant = {
        commit
        for commit, paths in commits.items()
        if "quality-scope.json" in paths
        or "docs/adr/index.json" in paths
        or any(
            path.startswith(ADOPTED_CONTINUATION_PRODUCT_ROOTS)
            or path in ADOPTED_CONTINUATION_PRODUCT_TOOLS
            or path == "Cargo.lock"
            for path in paths
        )
    }
    if relevant != set(REFERENCE_ACTIVATION_T03_SOURCE_COMMITS):
        raise ValueError("reference activation T03 has an unbound product/control commit")
    return {commit: commits[commit] for commit in REFERENCE_ACTIVATION_T03_SOURCE_COMMITS}


def reference_activation_historical_authority(repo: Path, head: str, backlog: dict[str, Any]) -> dict[str, set[str]]:
    """Authenticate exact reviewed T03, GOV26 and C10 predecessors named by ECR-0011."""

    import taskctl

    gov_path = "planning/governance-migrations/GOV-MAINT-0026.json"
    gov_review_path = "planning/governance-migrations/GOV-MAINT-0026.review-R01.json"
    gov_paths = {gov_path, "quality-scope.json"}
    if (
        not is_ancestor(repo, REFERENCE_ACTIVATION_GOV26_REVIEW, REFERENCE_ACTIVATION_PACKET_COMMIT)
        or not is_ancestor(repo, REFERENCE_ACTIVATION_GOV26_REVIEW, head)
        or resolve_commit(repo, f"{REFERENCE_ACTIVATION_GOV26_CANDIDATE}^") != REFERENCE_ACTIVATION_GOV26_BASE
        or resolve_commit(repo, f"{REFERENCE_ACTIVATION_GOV26_REVIEW}^") != REFERENCE_ACTIVATION_GOV26_CANDIDATE
        or commit_paths(repo, REFERENCE_ACTIVATION_GOV26_CANDIDATE) != gov_paths
        or commit_paths(repo, REFERENCE_ACTIVATION_GOV26_REVIEW) != {gov_path, gov_review_path}
        or hashlib.sha256(blob(repo, REFERENCE_ACTIVATION_GOV26_CANDIDATE, gov_path)).hexdigest()
        != "4fc41992e622edbddf09cf08ad8181543e3295d05e581461d7ee7eecd5a4ae57"
        or hashlib.sha256(blob(repo, head, gov_path)).hexdigest()
        != "f68067a46653f5362f4a180a80401cf4139b639b2e8b4059028709333c4c873a"
        or blob(repo, head, gov_path) != blob(repo, REFERENCE_ACTIVATION_GOV26_REVIEW, gov_path)
        or blob(repo, head, "quality-scope.json")
        != blob(repo, REFERENCE_ACTIVATION_GOV26_CANDIDATE, "quality-scope.json")
        or tree_entry(repo, head, gov_path) != ("100644", "blob")
        or tree_entry(repo, head, "quality-scope.json") != ("100644", "blob")
    ):
        raise ValueError("reference activation lacks exact adopted GOV-MAINT-0026 predecessor")
    review, introduction = immutable_record(
        repo, head, gov_review_path, "a5603eb1f4ee4dcb279f2f4f298fbb10aa802507ab970fa68bef15d9f6435c94"
    )
    if (
        introduction != REFERENCE_ACTIVATION_GOV26_REVIEW
        or review.get("maintenanceId") != "GOV-MAINT-0026"
        or review.get("reviewedCommit") != REFERENCE_ACTIVATION_GOV26_CANDIDATE
        or review.get("disposition") != "APPROVED"
        or review.get("findings") != []
        or review.get("candidateChangedPaths") != sorted(gov_paths)
        or not independent_identity(review.get("reviewer"), "w2-quality-inventory-prepare")
    ):
        raise ValueError("reference activation lacks independent GOV-MAINT-0026 review")

    correction = next((item for item in taskctl.corrective_tasks(backlog) if item.get("id") == "W2.C10.T01"), None)
    if correction is None or correction.get("status") != "DONE":
        raise ValueError("reference activation lacks completed W2.C10.T01 correction")
    ranges = correction_submission_ranges(repo, head, {"tasks": [correction]})
    source = {
        "services/core-api/src/research_observatory_core/plugin_worker.py",
        "tests/connectors/test_plugin_grant_migration.py",
        "tests/connectors/test_plugin_worker_submission.py",
    }
    if (
        len(ranges) != 1
        or correction.get("base_sha") != REFERENCE_ACTIVATION_C10_BASE
        or ranges[0]["base"] != REFERENCE_ACTIVATION_C10_BASE
        or ranges[0]["candidate"] != REFERENCE_ACTIVATION_C10_CANDIDATE
        or commit_paths(repo, REFERENCE_ACTIVATION_C10_CANDIDATE) != source
        or set(correction.get("correction", {}).get("changed_paths", [])) != source
        or correction.get("review_control", {}).get("attempts", [{}])[0].get("ledger", {}).get("path")
        != "artifacts/evidence/W2.C10.T01.review-R01.json"
        or not is_ancestor(repo, REFERENCE_ACTIVATION_C10_DISPOSITION, REFERENCE_ACTIVATION_PACKET_COMMIT)
        or not is_ancestor(repo, REFERENCE_ACTIVATION_C10_DISPOSITION, head)
        or corrective_scope_errors(repo, correction, REFERENCE_ACTIVATION_C10_CANDIDATE, ranges[0]["paths"])
    ):
        raise ValueError("reference activation lacks exact independently reviewed W2.C10.T01 source")
    frozen = yaml_object(
        blob(repo, REFERENCE_ACTIVATION_PACKET_COMMIT, "planning/backlog.yaml"), "ECR-0011 frozen predecessor"
    )
    frozen_correction = next(
        (item for item in taskctl.corrective_tasks(frozen) if item.get("id") == "W2.C10.T01"), None
    )
    if frozen_correction != correction:
        raise ValueError("reference activation changed the ECR-0011-frozen W2.C10.T01 correction")
    admitted = reference_activation_historical_t03_authority(repo, head, backlog)
    admitted.update(
        {
            REFERENCE_ACTIVATION_GOV26_CANDIDATE: gov_paths,
            REFERENCE_ACTIVATION_C10_CANDIDATE: source,
        }
    )
    return admitted


def reference_activation_bootstrap_authority(
    repo: Path, head: str, amendment: dict[str, Any], packet: dict[str, Any]
) -> None:
    """Bind reviewed B00, separate materialization and bounded A03 activation."""

    from taskctl import bootstrap_packet_errors, immutable_amendment_task_errors

    reference = amendment["approval_reference"]
    approval, _ = immutable_record(repo, head, "planning/wave-amendment-approvals/W2.A03.json", reference["sha256"])
    errors = [
        *bootstrap_packet_errors(repo, amendment, approval, packet),
        *immutable_amendment_task_errors(amendment, packet),
    ]
    if errors:
        raise ValueError("reference activation B00/task packet is invalid: " + "; ".join(errors))
    anchors = (
        REFERENCE_ACTIVATION_BOOTSTRAP_APPROVAL,
        REFERENCE_ACTIVATION_MATERIALIZATION,
        REFERENCE_ACTIVATION_CAMPAIGN_START,
    )
    if (
        not is_ancestor(repo, anchors[-1], head)
        or any(resolve_commit(repo, f"{right}^") != left for left, right in pairwise(anchors))
        or any(commit_paths(repo, commit) != {"planning/backlog.yaml"} for commit in anchors[1:])
    ):
        raise ValueError("reference activation lacks separate exact B00/materialization/activation commits")
    states = [
        yaml_object(blob(repo, commit, "planning/backlog.yaml"), f"A03 {name} state")
        for commit, name in zip(anchors, ("bootstrap", "materialization", "activation"), strict=True)
    ]
    stages = [amendment_record(state, REFERENCE_ACTIVATION_AMENDMENT_ID) for state in states]
    expected_tasks = [REFERENCE_ACTIVATION_CONTROL_TASK_ID, REFERENCE_ACTIVATION_CONSUMER_TASK_ID]
    if (
        stages[0].get("bootstrap", {}).get("status") != "APPROVED"
        or stages[0].get("lifecycle", {}).get("status") != "APPROVED"
        or stages[0].get("tasks") != []
        or stages[1].get("lifecycle", {}).get("status") != "MATERIALIZED"
        or [item.get("id") for item in stages[1].get("tasks", [])] != expected_tasks
        or stages[2].get("lifecycle", {}).get("status") != "ACTIVE"
        or stages[2].get("campaign", {}).get("status") != "ACTIVE"
        or [item.get("id") for item in stages[2].get("tasks", [])] != expected_tasks
        or [state.get("control_plane", {}).get("active_amendment") for state in states]
        != [None, None, REFERENCE_ACTIVATION_AMENDMENT_ID]
        or any(
            next(item for item in state["waves"] if item["id"] == "W2")["campaign"]["status"] != "PAUSED"
            for state in states
        )
    ):
        raise ValueError("reference activation B00/materialization/activation states differ from reviewed order")


def reference_activation_correction_predecessor(
    repo: Path, head: str, binding: dict[str, Any], parent: dict[str, Any]
) -> dict[str, Any]:
    """Authenticate only the approved combined claim/block/pause, never infer a claim."""

    from governance_kernel import validate_returned_predecessor_history
    from planctl import _paused_predecessor_errors

    frozen_packet = json_object(
        blob(repo, REFERENCE_ACTIVATION_CORRECTION_PACKET, "planning/enabler-change-requests/ECR-0012.packet.json"),
        "exact correction packet",
    )
    expected = frozen_packet["authorityChain"]["pausedPredecessor"]
    if (
        binding != expected
        or binding.get("effectiveStateCommit") != REFERENCE_ACTIVATION_COMBINED_PAUSE
        or binding.get("recordSha256") != "f099fd8f6a15dcdcddea9ac6dca1ca5cac62d8692991e2d6e4366b1393c6ac6c"
        or resolve_commit(repo, f"{REFERENCE_ACTIVATION_COMBINED_PAUSE}^") != REFERENCE_ACTIVATION_RETAINED_BASE
        or not is_ancestor(repo, REFERENCE_ACTIVATION_COMBINED_PAUSE, head)
        or commit_paths(repo, REFERENCE_ACTIVATION_COMBINED_PAUSE) & REFERENCE_ACTIVATION_CONSUMER_SOURCE
    ):
        raise ValueError("activation correction substituted the exact combined claim/block/pause")
    errors = _paused_predecessor_errors(repo, binding, REFERENCE_ACTIVATION_CORRECTION_ID, returned_parent=parent)
    if errors:
        raise ValueError("activation correction predecessor is invalid: " + "; ".join(errors))
    frozen = amendment_record(
        yaml_object(blob(repo, REFERENCE_ACTIVATION_COMBINED_PAUSE, "planning/backlog.yaml"), "combined pause"),
        REFERENCE_ACTIVATION_AMENDMENT_ID,
    )
    validate_returned_predecessor_history(frozen, parent)
    for prior, current in zip(frozen["tasks"], parent["tasks"], strict=True):
        for field in (
            "id",
            "amendment_id",
            "packet_task_sha256",
            "title",
            "objective",
            "dependencies",
            "acceptance_criteria",
            "verification_commands",
            "base_sha",
            "started_at",
            "owner",
            "branch",
            "worktree",
        ):
            if current.get(field) != prior.get(field):
                raise ValueError(f"activation correction changed retained task identity: {field}")
    return frozen


def reference_activation_correction_active(
    state: dict[str, Any],
    identity: str,
    task_base: str,
    campaign_base: str,
    owner: str,
    branch: str,
    *,
    observed_at: int | None = None,
) -> bool:
    """Source endpoints require the task and its sole campaign to agree."""

    task = backlog_task(state, identity) or {}
    amendment = amendment_record(state, str(task.get("amendment_id")))
    campaign = amendment.get("campaign") or {}
    wave = next(item for item in state["waves"] if item["id"] == "W2")
    if observed_at is not None:
        try:
            leases = (task.get("lease") or {}, campaign.get("lease") or {})
            expirations = [datetime.fromisoformat(str(lease.get("expires_at"))) for lease in leases]
            if any(value.tzinfo is None or value.timestamp() <= observed_at for value in expirations):
                return False
        except ValueError, TypeError, OverflowError:
            return False
    return (
        task.get("status") == "IN_PROGRESS"
        and task.get("base_sha") == task_base
        and task.get("owner") == owner
        and task.get("branch") == branch
        and task.get("worktree") == "."
        and (task.get("lease") or {}).get("claimed_by") == owner
        and (task.get("lease") or {}).get("expires_at") is not None
        and amendment.get("lifecycle", {}).get("status") == "ACTIVE"
        and campaign.get("status") == "ACTIVE"
        and campaign.get("scope") == "wave-amendment"
        and campaign.get("owner") == owner
        and campaign.get("branch") == branch
        and campaign.get("worktree") == "."
        and campaign.get("base_sha") == campaign_base
        and campaign.get("profile") == "LOC"
        and campaign.get("platform") == "windows-x64"
        and (campaign.get("lease") or {}).get("claimed_by") == owner
        and (campaign.get("lease") or {}).get("expires_at") is not None
        and state.get("control_plane", {}).get("active_amendment") == amendment["id"]
        and wave.get("campaign", {}).get("status") == "PAUSED"
        and wave.get("campaign", {}).get("scope") == "amendment-hold"
        and wave.get("campaign", {}).get("lease") is None
    )


def reference_activation_correction_slice_history(
    repo: Path,
    head: str,
    task: dict[str, Any],
    owner: str,
    exit_candidate: str,
    *,
    amendment_id: str = REFERENCE_ACTIVATION_CORRECTION_ID,
    tasks: list[dict[str, Any]] | None = None,
) -> set[str]:
    """Authenticate every immutable contribution round and its preserved findings."""
    tasks = tasks or [task]
    if amendment_id not in {"W2.A03", "W2.A04", "W2.A05"} or [t["id"] for t in tasks] != (
        [f"{amendment_id}.T01"] if amendment_id == "W2.A04" else [f"{amendment_id}.T01", f"{amendment_id}.T02"]
    ):
        raise ValueError("activation correction has a foreign slice/task inventory")
    prefix = f"artifacts/evidence/{amendment_id}.S01.review-"
    paths = [
        path
        for path in git(repo, "ls-tree", "-r", "--name-only", head, "--", "artifacts/evidence").decode().splitlines()
        if path.startswith(prefix)
    ]
    if any(re.fullmatch(re.escape(prefix) + r"[0-9]{2,}\.json", path) is None for path in paths):
        raise ValueError("activation correction lacks contiguous canonical S01 review history")
    paths.sort(key=lambda path: int(path[len(prefix) : -5]))
    if not paths or paths != [f"{prefix}{number:02d}.json" for number in range(1, len(paths) + 1)]:
        raise ValueError("activation correction lacks contiguous canonical S01 review history")
    approved: dict[tuple[str, str], str] = {}
    for reviewed_task in tasks:
        for attempt in reviewed_task["review_control"]["attempts"]:
            if attempt["review"]["result"] == "approved":
                ledger = attempt["ledger"]
                _, introduction = immutable_record(repo, head, ledger["path"], ledger["sha256"], evidence=True)
                approved[(reviewed_task["id"], attempt["submission"]["candidate_commit"])] = introduction
    latest_bindings = [
        {"taskId": t["id"], "candidateCommit": t["review_control"]["attempts"][-1]["submission"]["candidate_commit"]}
        for t in tasks
    ]
    schema = json_object(blob(repo, head, "planning/backlog.schema.json"), "review finding schema")
    finding_validator = Draft202012Validator(schema["$defs"]["reviewFinding"])
    closure_validator = Draft202012Validator(schema["$defs"]["reviewFindingClosure"])
    open_findings: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()
    previous: str | None = None
    for path in paths:
        record, introduction = immutable_record(repo, head, path, evidence=True)
        bindings = record.get("taskBindings")
        valid_bindings = (
            isinstance(bindings, list)
            and len(bindings) == len(tasks)
            and all(
                isinstance(b, dict)
                and b == {"taskId": t["id"], "candidateCommit": b.get("candidateCommit")}
                and isinstance(b.get("candidateCommit"), str)
                and (t["id"], b.get("candidateCommit")) in approved
                and approved[(t["id"], b["candidateCommit"])] != introduction
                and is_ancestor(repo, approved[(t["id"], b["candidateCommit"])], introduction)
                for b, t in zip(bindings, tasks, strict=True)
            )
        )
        if (
            record.get("schemaVersion") != "1.0"
            or record.get("documentType") != "amendment-contribution-independent-review"
            or record.get("amendmentId") != amendment_id
            or record.get("sliceId") != f"{amendment_id}.S01"
            or record.get("capabilityId") != "CAP-05"
            or not valid_bindings
            or not independent_identity(record.get("reviewer"), owner)
            or (previous is not None and (previous == introduction or not is_ancestor(repo, previous, introduction)))
            or not is_ancestor(repo, introduction, exit_candidate)
        ):
            raise ValueError("activation correction lacks integrated independent S01 review before exit")
        findings, closures = record.get("findings"), record.get("closures", [])
        if not isinstance(findings, list) or not isinstance(closures, list):
            raise ValueError("activation correction S01 findings/closures are malformed")
        for closure in closures:
            identity = closure.get("finding_id") if isinstance(closure, dict) else None
            if (
                list(closure_validator.iter_errors(closure))
                or not isinstance(identity, str)
                or identity not in open_findings
            ):
                raise ValueError("activation correction S01 closure does not name an evidenced open finding")
            open_findings.pop(identity)
        for finding in findings:
            identity = finding.get("id") if isinstance(finding, dict) else None
            if (
                list(finding_validator.iter_errors(finding))
                or not isinstance(identity, str)
                or not identity.strip()
                or identity in seen
            ):
                raise ValueError("activation correction S01 finding identity is missing or reused")
            seen.add(identity)
            open_findings[identity] = finding
        if record.get("openFindingIds") != sorted(open_findings) or record.get("result") not in {
            "approved",
            "changes-requested",
            "blocked",
        }:
            raise ValueError("activation correction S01 disposition differs from preserved findings")
        if record["result"] == "approved" and open_findings:
            raise ValueError("activation correction S01 approval retains open findings")
        if record["result"] in {"changes-requested", "blocked"} and not any(
            finding["blocking"] for finding in open_findings.values()
        ):
            raise ValueError("activation correction adverse S01 review lacks an open blocking finding")
        previous = introduction
    if record["result"] != "approved" or findings or open_findings or bindings != latest_bindings:
        raise ValueError("activation correction latest S01 review is not independently approved for its current task")
    return set(paths)


def reference_activation_correction_checkpoint_reviews(
    repo: Path, head: str, child: dict[str, Any], adoption: str
) -> set[str]:
    """Bind the separate immutable security review to the actual checkpoint."""
    from taskctl import evidence_sha256

    if child.get("id") not in {"W2.A03", "W2.A04", "W2.A05"}:
        raise ValueError("activation correction checkpoint has a foreign amendment")
    manifest_path = f"artifacts/evidence/{child['id']}.adoption.json"
    manifest, manifest_introduction = immutable_record(repo, head, manifest_path, evidence=True)
    reviewed_manifest = {
        "path": manifest_path,
        "introductionCommit": manifest_introduction,
        "gitBlob": git(repo, "rev-parse", f"{manifest_introduction}:{manifest_path}").decode().strip(),
        "sha256": evidence_sha256(blob(repo, manifest_introduction, manifest_path)),
    }
    latest_exit = child["completion"]["exit_review_control"]["attempts"][-1]
    prefix = f"artifacts/evidence/{child['id']}.adoption.review-"
    paths = [
        path
        for path in git(repo, "ls-tree", "-r", "--name-only", head, "--", "artifacts/evidence").decode().splitlines()
        if path.startswith(prefix)
    ]
    if any(re.fullmatch(re.escape(prefix) + r"[0-9]{2,}\.json", path) is None for path in paths):
        raise ValueError("activation correction checkpoint review history is not canonical")
    paths.sort(key=lambda path: int(path[len(prefix) : -5]))
    if not paths or paths != [f"{prefix}{number:02d}.json" for number in range(1, len(paths) + 1)]:
        raise ValueError("activation correction checkpoint review history is missing or noncontiguous")
    schema = json_object(blob(repo, head, "planning/backlog.schema.json"), "checkpoint review finding schema")
    finding_validator = Draft202012Validator(schema["$defs"]["reviewFinding"])
    closure_validator = Draft202012Validator(schema["$defs"]["reviewFindingClosure"])
    open_findings: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()
    previous = manifest_introduction
    for path in paths:
        record, introduction = immutable_record(repo, head, path, evidence=True)
        if (
            record.get("schemaVersion") != "1.0"
            or record.get("documentType") != "wave-amendment-adoption-security-independent-review"
            or record.get("amendmentId") != child["id"]
            or record.get("targetWave") != "W2"
            or record.get("reviewedManifest") != reviewed_manifest
            or not independent_identity(record.get("reviewer"), child["campaign"].get("owner"))
            or not isinstance(record.get("approvedExit"), dict)
            or record["approvedExit"].get("attemptId") != latest_exit["submission"]["id"]
            or record["approvedExit"].get("reviewedCompletionCommit") != manifest.get("reviewedCompletionCommit")
            or introduction in (previous, adoption)
            or not is_ancestor(repo, previous, introduction)
            or not is_ancestor(repo, introduction, adoption)
        ):
            raise ValueError("activation correction checkpoint review identity, manifest, exit or ordering is invalid")
        findings, closures = record.get("findings"), record.get("closures", [])
        if not isinstance(findings, list) or not isinstance(closures, list):
            raise ValueError("activation correction checkpoint review findings/closures are malformed")
        for closure in closures:
            identity = closure.get("finding_id") if isinstance(closure, dict) else None
            if (
                list(closure_validator.iter_errors(closure))
                or not isinstance(identity, str)
                or identity not in open_findings
            ):
                raise ValueError("activation correction checkpoint review closure lacks an evidenced open finding")
            open_findings.pop(identity)
        for finding in findings:
            identity = finding.get("id") if isinstance(finding, dict) else None
            if (
                list(finding_validator.iter_errors(finding))
                or not isinstance(identity, str)
                or not identity.strip()
                or identity in seen
            ):
                raise ValueError("activation correction checkpoint review finding identity is missing or reused")
            seen.add(identity)
            open_findings[identity] = finding
        if (
            ("openFindingIds" in record and record["openFindingIds"] != sorted(open_findings))
            or record.get("result") not in {"approved", "changes-requested", "blocked"}
            or (record.get("result") == "approved" and open_findings)
            or (
                record.get("result") in {"changes-requested", "blocked"}
                and not any(f["blocking"] for f in open_findings.values())
            )
        ):
            raise ValueError("activation correction checkpoint review disposition differs from preserved findings")
        previous = introduction
    if record["result"] != "approved" or findings or open_findings:
        raise ValueError("activation correction latest checkpoint review is not independently approved")
    return set(paths)


def reference_activation_correction_authority(
    repo: Path, head: str, backlog: dict[str, Any], parent: dict[str, Any], *, repair: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Derive the exact reviewed A04 segment and separate return/activate/reopen."""

    from governance_kernel import validate_returned_predecessor_history
    from taskctl import amendment_adoption_checkpoints, bootstrap_packet_errors, immutable_amendment_task_errors

    child = amendment_record(backlog, REFERENCE_ACTIVATION_CORRECTION_ID)
    if head != resolve_commit(repo, "HEAD") or git(repo, "branch", "--show-current").decode().strip() != parent[
        "tasks"
    ][1].get("branch"):
        raise ValueError("activation correction requires current HEAD and the retained claim branch")
    packet, packet_commit, approval_commit = approved_amendment_packet(repo, head, child)
    if (
        packet_commit != REFERENCE_ACTIVATION_CORRECTION_PACKET
        or hashlib.sha256(
            blob(repo, packet_commit, "planning/enabler-change-requests/ECR-0012.packet.json")
        ).hexdigest()
        != REFERENCE_ACTIVATION_CORRECTION_PACKET_SHA
        or child.get("change_request_id") != "ECR-0012"
        or packet.get("authorizedTaskIds") != [REFERENCE_ACTIVATION_CORRECTION_TASK]
        or child.get("correction") != packet.get("authorityChain", {}).get("pausedPredecessor")
    ):
        raise ValueError("activation correction lacks the exact approved ECR-0012 packet")
    frozen = reference_activation_correction_predecessor(repo, head, child["correction"], parent)
    approval, _ = immutable_record(
        repo, head, child["approval_reference"]["path"], child["approval_reference"]["sha256"]
    )
    errors = [*bootstrap_packet_errors(repo, child, approval, packet), *immutable_amendment_task_errors(child, packet)]
    if errors:
        raise ValueError("activation correction B00/task authority is invalid: " + "; ".join(errors))
    cache: dict[str, dict[str, Any]] = {}

    def state(commit: str) -> dict[str, Any]:
        if commit not in cache:
            document = yaml.load(blob(repo, commit, "planning/backlog.yaml"), Loader=yaml.CSafeLoader)
            if not isinstance(document, dict):
                raise ValueError("activation correction backlog is not an object")
            cache[commit] = document
        return cache[commit]

    anchors = (
        REFERENCE_ACTIVATION_CORRECTION_BOOTSTRAP,
        REFERENCE_ACTIVATION_CORRECTION_MATERIALIZATION,
        REFERENCE_ACTIVATION_CORRECTION_ACTIVATION,
        REFERENCE_ACTIVATION_CORRECTION_CLAIM,
    )
    if (
        not is_ancestor(repo, approval_commit, anchors[0])
        or not is_ancestor(repo, anchors[-1], head)
        or any(resolve_commit(repo, f"{right}^") != left for left, right in pairwise(anchors))
        or any(commit_paths(repo, commit) != {"planning/backlog.yaml"} for commit in anchors)
    ):
        raise ValueError("activation correction lacks separate exact bootstrap/materialization/activation/claim")
    stages = [amendment_record(state(commit), child["id"]) for commit in anchors]
    if (
        [stage.get("lifecycle", {}).get("status") for stage in stages]
        != ["APPROVED", "MATERIALIZED", "ACTIVE", "ACTIVE"]
        or stages[0].get("tasks") != []
        or stages[1].get("campaign") is not None
        or [stage["tasks"][0].get("status") for stage in stages[1:]] != ["NOT_STARTED", "READY", "IN_PROGRESS"]
        or stages[0].get("bootstrap") != child.get("bootstrap")
        or stages[-1]["tasks"][0].get("base_sha") != anchors[2]
        or any(amendment_record(state(commit), parent["id"]) != frozen for commit in anchors)
    ):
        raise ValueError("activation correction changed its exact materialized/claimed predecessor state")
    b00_ledger, b00_introduction = immutable_record(
        repo, head, "artifacts/evidence/W2.A04.B00.review-R01.json", evidence=True
    )
    if (
        b00_ledger.get("result") != "approved"
        or b00_ledger.get("findings") != []
        or b00_ledger.get("candidateCommit") != child["bootstrap"].get("implementation_commit")
        or b00_ledger.get("reviewer") != child["bootstrap"].get("review", {}).get("reviewer")
        or not independent_identity(b00_ledger.get("reviewer"), child["bootstrap"].get("implementer"))
        or not is_ancestor(repo, b00_introduction, anchors[0])
    ):
        raise ValueError("activation correction lacks its immutable independent B00 disposition")
    task = child["tasks"][0]
    owner, branch = str(task.get("owner")), str(task.get("branch"))
    if not reference_activation_correction_active(
        state(anchors[-1]),
        task["id"],
        anchors[2],
        anchors[1],
        owner,
        branch,
        observed_at=int(git(repo, "show", "-s", "--format=%ct", anchors[-1]).decode()),
    ):
        raise ValueError("activation correction claim changed owner, lease, branch, worktree or base")
    _ranges, admitted = adopted_continuation_reviewed_task_commits(repo, head, task)
    task_outputs = {"artifacts/evidence/W2.A04.T01.task-start.md"}
    for attempt in task["review_control"]["attempts"]:
        task_outputs.update((attempt["submission"]["evidence_reference"]["path"], attempt["ledger"]["path"]))
    seen: set[str] = set()
    for commit, paths in admitted.items():
        if not paths.issubset(
            REFERENCE_ACTIVATION_CORRECTION_SOURCE | REFERENCE_ACTIVATION_CORRECTION_WORKFLOW | task_outputs
        ):
            raise ValueError("activation correction changed source outside its exact five-path envelope")
        overlap = paths & REFERENCE_ACTIVATION_CORRECTION_SOURCE
        if overlap:
            previous = resolve_commit(repo, f"{commit}^")
            if any(
                not reference_activation_correction_active(
                    state(at),
                    task["id"],
                    anchors[2],
                    anchors[1],
                    owner,
                    branch,
                    observed_at=int(git(repo, "show", "-s", "--format=%ct", at).decode()),
                )
                for at in (previous, commit)
            ):
                raise ValueError("activation correction source lacks both active claim endpoints")
            if any(tree_entry(repo, commit, path) != ("100644", "blob") for path in overlap):
                raise ValueError("activation correction source was deleted, executable or redirected")
            seen.update(overlap)
    if seen != REFERENCE_ACTIVATION_CORRECTION_SOURCE:
        raise ValueError("activation correction does not deliver exactly all five sources")
    if git(repo, "diff", "--name-only", head, "--", *sorted(REFERENCE_ACTIVATION_CORRECTION_SOURCE)).strip() or any(
        repo.joinpath(*PurePosixPath(path).parts).is_symlink()
        or not repo.joinpath(*PurePosixPath(path).parts).resolve().is_relative_to(repo.resolve())
        for path in REFERENCE_ACTIVATION_CORRECTION_SOURCE
    ):
        raise ValueError("activation correction has dirty or redirected working inputs")
    index_path = "docs/adr/index.json"
    before_index = json_object(blob(repo, anchors[2], index_path), "pre-correction ADR registry")
    expected_index = copy.deepcopy(before_index)
    expected_index["records"].append(
        {
            "id": "ADR-0040",
            "path": REFERENCE_ACTIVATION_CORRECTION_ADR,
            "title": "Document protected desktop activation correction",
            "status": "Proposed",
            "linkedTasks": [REFERENCE_ACTIVATION_CORRECTION_TASK, REFERENCE_ACTIVATION_CONSUMER_TASK_ID],
        }
    )
    index_touches = [commit for commit, paths in admitted.items() if index_path in paths]
    adr_touches = [commit for commit, paths in admitted.items() if REFERENCE_ACTIVATION_CORRECTION_ADR in paths]
    if (
        len(index_touches) != 1
        or not adr_touches
        or index_touches[0] != adr_touches[0]
        or tree_entry(repo, f"{adr_touches[0]}^", REFERENCE_ACTIVATION_CORRECTION_ADR) is not None
        or json_object(blob(repo, head, index_path), "correction registry")
        != (repair["index"] if repair else expected_index)
    ):
        raise ValueError("activation correction ADR is not one jointly introduced appended entry")
    for commit in adr_touches:
        parts = blob(repo, commit, REFERENCE_ACTIVATION_CORRECTION_ADR).decode("utf-8").split("---", 2)
        metadata = yaml.safe_load(parts[1]) if len(parts) == 3 and not parts[0].strip() else {}
        if (
            not isinstance(metadata, dict)
            or metadata.get("id") != "ADR-0040"
            or metadata.get("status") != "Proposed"
            or metadata.get("deciders") != []
            or metadata.get("supersedes") != []
            or metadata.get("superseded_by") is not None
            or metadata.get("linked_tasks")
            != [REFERENCE_ACTIVATION_CORRECTION_TASK, REFERENCE_ACTIVATION_CONSUMER_TASK_ID]
            or metadata.get("affected_paths")
            != [
                "tools/ui_change_gate.py",
                "verification/extensions/desktop-ui.json",
                "verification/baselines/desktop-ui.json",
            ]
            or any(
                section not in parts[2]
                for section in (
                    "## Context",
                    "## Candidates",
                    "## Decision",
                    "## Consequences",
                    "## Verification",
                    "## Task links",
                )
            )
            or json_object(blob(repo, commit, index_path), "introduced registry") != expected_index
        ):
            raise ValueError("activation correction changed Proposed companion/registry authority")
    adoption = adopted_continuation_adoption(repo, head, backlog, child, packet)
    exit_attempts = child["completion"]["exit_review_control"]["attempts"]
    slice_outputs = reference_activation_correction_slice_history(
        repo, head, task, owner, exit_attempts[-1]["submission"]["candidate_commit"]
    )
    security_outputs = reference_activation_correction_checkpoint_reviews(repo, head, child, adoption)
    workflow_outputs = (
        task_outputs
        | slice_outputs
        | security_outputs
        | {
            "artifacts/evidence/W2.A04.B00.json",
            "artifacts/evidence/W2.A04.B00.review-R01.json",
            "artifacts/evidence/W2.A04.adoption.json",
        }
    )
    for attempt in exit_attempts:
        workflow_outputs.update((attempt["submission"]["evidence_reference"]["path"], attempt["ledger"]["path"]))
    if (
        amendment_record(state(adoption), parent["id"]) != frozen
        or amendment_record(state(adoption), child["id"]) != child
    ):
        raise ValueError("activation correction did not return the exact paused predecessor")
    for commit in git(repo, "rev-list", f"{adoption}..{head}", "--", "planning/backlog.yaml").decode().splitlines():
        if amendment_record(state(commit), child["id"]) != child:
            raise ValueError("activation correction changed adopted correction history")
    for item in packet["files"]:
        path = item["path"]
        if git(repo, "log", "--format=%H", f"{packet_commit}..{head}", "--", path).strip():
            raise ValueError("activation correction changed a frozen packet input after review")
    consumer = parent["tasks"][1]
    consumer_candidate = consumer["review_control"]["attempts"][-1]["submission"]["candidate_commit"]
    ordered = (
        git(repo, "rev-list", "--reverse", f"{REFERENCE_ACTIVATION_COMBINED_PAUSE}..{consumer_candidate}")
        .decode()
        .splitlines()
    )
    activations: list[str] = []
    reopens: list[str] = []
    frozen_state = state(REFERENCE_ACTIVATION_COMBINED_PAUSE)
    frozen_wave = next(item for item in frozen_state["waves"] if item["id"] == "W2")
    returned_wave = next(item for item in state(adoption)["waves"] if item["id"] == "W2")
    if returned_wave["checkpoints"] != [
        *frozen_wave["checkpoints"],
        *amendment_adoption_checkpoints(returned_wave, child["id"]),
    ]:
        raise ValueError("activation correction appended unrelated adoption checkpoints")

    def ordinary(document: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value for key, value in document.items() if key not in {"control_plane", "wave_amendments", "waves"}
        }

    for commit in ordered:
        paths = commit_paths(repo, commit)
        if "planning/backlog.yaml" not in paths:
            continue
        previous = resolve_commit(repo, f"{commit}^")
        before, after = state(previous), state(commit)
        for at, historical in ((previous, before), (commit, after)):
            historical_wave = next(item for item in historical["waves"] if item["id"] == "W2")
            expected_checkpoints = (
                returned_wave["checkpoints"] if is_ancestor(repo, adoption, at) else frozen_wave["checkpoints"]
            )
            if (
                ordinary(historical) != ordinary(frozen_state)
                or {key: value for key, value in historical["control_plane"].items() if key != "active_amendment"}
                != {key: value for key, value in frozen_state["control_plane"].items() if key != "active_amendment"}
                or [item for item in historical["waves"] if item["id"] != "W2"]
                != [item for item in frozen_state["waves"] if item["id"] != "W2"]
                or {key: value for key, value in historical_wave.items() if key != "checkpoints"}
                != {key: value for key, value in frozen_wave.items() if key != "checkpoints"}
                or historical_wave["checkpoints"] != expected_checkpoints
                or [item for item in historical["wave_amendments"] if item["id"] not in {parent["id"], child["id"]}]
                != [item for item in frozen_state["wave_amendments"] if item["id"] != parent["id"]]
            ):
                raise ValueError("activation correction changed ordinary records or checkpoint history")
        prior_parent, current_parent = amendment_record(before, parent["id"]), amendment_record(after, parent["id"])
        for historical_parent in (prior_parent, current_parent):
            validate_returned_predecessor_history(frozen, historical_parent)
            for field in ("id", "change_request_id", "target_wave", "kind", "approval_reference", "contributions"):
                if historical_parent.get(field) != frozen.get(field):
                    raise ValueError("activation correction changed retained parent authority")
            for field in (
                "id",
                "amendment_id",
                "packet_task_sha256",
                "title",
                "objective",
                "dependencies",
                "acceptance_criteria",
                "verification_commands",
                "base_sha",
                "started_at",
                "owner",
                "branch",
                "worktree",
            ):
                if historical_parent["tasks"][1].get(field) != frozen["tasks"][1].get(field):
                    raise ValueError("activation correction changed intermediate retained consumer identity")
        if not is_ancestor(repo, adoption, commit):
            if prior_parent != frozen or current_parent != frozen:
                raise ValueError("activation correction mutated its frozen predecessor before return")
            continue
        prior, current = prior_parent["tasks"][1], current_parent["tasks"][1]
        if prior_parent["lifecycle"]["status"] == "PAUSED" and current_parent["lifecycle"]["status"] == "ACTIVE":
            campaign = current_parent.get("campaign") or {}
            if (
                prior_parent != frozen
                or commit == adoption
                or not is_ancestor(repo, adoption, previous)
                or paths != {"planning/backlog.yaml"}
                or current != prior
                or current.get("status") != "BLOCKED"
                or campaign.get("base_sha") != previous
                or campaign.get("status") != "ACTIVE"
                or campaign.get("owner") != consumer.get("owner")
                or campaign.get("branch") != consumer.get("branch")
                or campaign.get("worktree") != "."
                or campaign.get("profile") != "LOC"
                or campaign.get("platform") != "windows-x64"
                or (campaign.get("lease") or {}).get("claimed_by") != consumer.get("owner")
                or after.get("control_plane", {}).get("active_amendment") != parent["id"]
            ):
                raise ValueError("activation correction has a premature or foreign A03 activation")
            activations.append(commit)
        if prior.get("status") == "BLOCKED" and current.get("status") == "IN_PROGRESS":
            if (
                len(activations) != 1
                or previous == adoption
                or paths != {"planning/backlog.yaml"}
                or not is_ancestor(repo, activations[0], previous)
                or current.get("base_sha") != REFERENCE_ACTIVATION_RETAINED_BASE
                or current.get("blocker") is not None
                or not reference_activation_correction_active(
                    after,
                    consumer["id"],
                    REFERENCE_ACTIVATION_RETAINED_BASE,
                    resolve_commit(repo, f"{activations[0]}^"),
                    str(consumer.get("owner")),
                    str(consumer.get("branch")),
                    observed_at=int(git(repo, "show", "-s", "--format=%ct", commit).decode()),
                )
            ):
                raise ValueError("activation correction lacks a separate retained-base T02 reopen")
            reopens.append(commit)
    if len(activations) != 1 or len(reopens) != 1:
        raise ValueError("activation correction lacks exactly one separate A03 activation and T02 reopen")
    return {
        "commits": admitted,
        "workflowPaths": workflow_outputs,
        "reopenCommit": reopens[0],
        "reactivationBase": resolve_commit(repo, f"{activations[0]}^"),
        "adoptionCommit": adoption,
    }


def reference_activation_reviewed_tasks(
    repo: Path, head: str, amendment: dict[str, Any]
) -> tuple[dict[str, set[str]], set[str], str]:
    """Attribute A03 source only to its two exact independently reviewed tasks."""

    backlog = yaml_object(blob(repo, head, "planning/backlog.yaml"), "activation task history")
    repair = (
        reference_activation_repair_authority(repo, head)
        if any(item.get("id") == "W2.A05" for item in backlog.get("wave_amendments", []))
        else None
    )
    inert_outputs = reference_activation_inert_projection_map(repo, head) if repair else None
    correction = (
        reference_activation_correction_authority(repo, head, backlog, amendment, repair=repair)
        if any(item.get("id") == REFERENCE_ACTIVATION_CORRECTION_ID for item in backlog.get("wave_amendments", []))
        else None
    )

    def active_amendment_claim(state: dict[str, Any], task: dict[str, Any]) -> bool:
        campaign = amendment_record(state, REFERENCE_ACTIVATION_AMENDMENT_ID).get("campaign") or {}
        wave: dict[str, Any] = next((item for item in state.get("waves", []) if item.get("id") == "W2"), {})
        return (
            (state.get("control_plane") or {}).get("active_amendment") == REFERENCE_ACTIVATION_AMENDMENT_ID
            and (wave.get("campaign") or {}).get("status") == "PAUSED"
            and campaign.get("status") == "ACTIVE"
            and campaign.get("scope") == "wave-amendment"
            and campaign.get("owner") == task.get("owner")
            and campaign.get("branch") == task.get("branch")
            and campaign.get("worktree") == "."
            and campaign.get("base_sha")
            == (
                correction["reactivationBase"]
                if correction is not None and task.get("id") == REFERENCE_ACTIVATION_CONSUMER_TASK_ID
                else REFERENCE_ACTIVATION_MATERIALIZATION
            )
            and campaign.get("profile") == "LOC"
            and campaign.get("platform") == "windows-x64"
            and (campaign.get("lease") or {}).get("claimed_by") == task.get("owner")
        )

    tasks = amendment.get("tasks") or []
    if [item.get("id") for item in tasks] != [
        REFERENCE_ACTIVATION_CONTROL_TASK_ID,
        REFERENCE_ACTIVATION_CONSUMER_TASK_ID,
    ]:
        raise ValueError("reference activation has a foreign task inventory")
    if (
        resolve_commit(repo, f"{REFERENCE_ACTIVATION_CONTROL_CLAIM}^") != REFERENCE_ACTIVATION_CAMPAIGN_START
        or not is_ancestor(repo, REFERENCE_ACTIVATION_CONTROL_CLAIM, head)
        or commit_paths(repo, REFERENCE_ACTIVATION_CONTROL_CLAIM) & REFERENCE_ACTIVATION_CONTROL_SOURCE
    ):
        raise ValueError("reference activation T01 control source preceded its exact claim")
    claimed = yaml_object(blob(repo, REFERENCE_ACTIVATION_CONTROL_CLAIM, "planning/backlog.yaml"), "A03 T01 claim")
    claimed_control = backlog_task(claimed, REFERENCE_ACTIVATION_CONTROL_TASK_ID) or {}
    if (
        claimed_control.get("status") != "IN_PROGRESS"
        or claimed_control.get("base_sha") != REFERENCE_ACTIVATION_CAMPAIGN_START
        or claimed_control.get("owner") != tasks[0].get("owner")
        or claimed_control.get("branch") != tasks[0].get("branch")
        or (claimed_control.get("lease") or {}).get("claimed_by") != claimed_control.get("owner")
        or not active_amendment_claim(claimed, claimed_control)
    ):
        raise ValueError("reference activation T01 claim has a foreign owner, branch or base")
    admitted: dict[str, set[str]] = {}
    consumer_commits: set[str] = set()
    source_seen: dict[str, set[str]] = {}
    for task, source in zip(
        tasks, (REFERENCE_ACTIVATION_CONTROL_SOURCE, REFERENCE_ACTIVATION_CONSUMER_SOURCE), strict=True
    ):
        identity = str(task["id"])
        ranges, commits = adopted_continuation_reviewed_task_commits(repo, head, task, inert_outputs=inert_outputs)
        if not ranges or set(commits) & set(admitted):
            raise ValueError("reference activation reviewed task ranges are absent or overlapping")
        allowed_delivery = {
            "planning/backlog.yaml",
            "docs/planning-implementation-plan.md",
            "planning/status-summary.md",
            "planning/review-site/enablers/ECR-0011.html",
            "planning/review-site/enablers/index.html",
            "planning/review-site/manifest.json",
            "planning/review-site/waves/W2.html",
        }
        seen: set[str] = set()
        for commit, paths in commits.items():
            if correction is not None and identity == REFERENCE_ACTIVATION_CONSUMER_TASK_ID:
                if commit in correction["commits"]:
                    if paths != correction["commits"][commit] or paths & REFERENCE_ACTIVATION_CONSUMER_SOURCE:
                        raise ValueError("activation correction mixed independently reviewed A04 and consumer delivery")
                    admitted[commit] = paths
                    continue
                if paths & source:
                    previous = resolve_commit(repo, f"{commit}^")
                    if not is_ancestor(repo, correction["reopenCommit"], previous) or any(
                        not reference_activation_correction_active(
                            yaml_object(blob(repo, at, "planning/backlog.yaml"), "corrected consumer source"),
                            identity,
                            REFERENCE_ACTIVATION_RETAINED_BASE,
                            correction["reactivationBase"],
                            str(task.get("owner")),
                            str(task.get("branch")),
                            observed_at=int(git(repo, "show", "-s", "--format=%ct", at).decode()),
                        )
                        for at in (previous, commit)
                    ):
                        raise ValueError("activation consumer source preceded reopen or lacks active claim endpoints")
            for path in paths:
                workflow_output = (
                    path in allowed_delivery
                    or path.startswith(f"artifacts/evidence/{identity}.")
                    or path.startswith(f"artifacts/evidence/{identity}-")
                )
                if correction is not None and identity == REFERENCE_ACTIVATION_CONSUMER_TASK_ID:
                    workflow_output = (
                        workflow_output
                        or path in REFERENCE_ACTIVATION_CORRECTION_WORKFLOW
                        or (
                            re.fullmatch(
                                r"planning/enabler-change-requests/ECR-0012(?:-review\.html|\.md|\.packet\.json|"
                                r"\.preflight-01\.json|\.review-R01\.json)",
                                path,
                            )
                            is not None
                            or path == "planning/wave-amendment-approvals/W2.A04.json"
                            or path in correction["workflowPaths"]
                        )
                    )
                if path not in source and not workflow_output:
                    raise ValueError(f"{identity} changed source outside its ECR-0011 packet envelope: {path}")
                if path in source:
                    seen.add(path)
                    if tree_entry(repo, commit, path) != ("100644", "blob"):
                        raise ValueError(f"{identity} source was deleted, executable or redirected: {path}")
            admitted[commit] = paths
        source_seen[identity] = seen
        if identity == REFERENCE_ACTIVATION_CONSUMER_TASK_ID:
            consumer_commits.update(
                commit
                for commit, paths in commits.items()
                if correction is None or paths & REFERENCE_ACTIVATION_CONSUMER_SOURCE
            )
    if REFERENCE_ACTIVATION_WITNESS_PATH not in source_seen[REFERENCE_ACTIVATION_CONTROL_TASK_ID]:
        raise ValueError("reference activation lacks a reviewed 1.8 presentation witness")
    if not REFERENCE_ACTIVATION_CONSUMER_FILES.issubset(source_seen[REFERENCE_ACTIVATION_CONSUMER_TASK_ID]):
        raise ValueError("reference activation lacks reviewed assembler, extension or baseline source")
    control_attempts = tasks[0]["review_control"]["attempts"]
    control_ledger = control_attempts[-1]["ledger"]
    _, control_review_introduction = immutable_record(
        repo, head, control_ledger["path"], control_ledger["sha256"], evidence=True
    )
    consumer_base = tasks[1].get("base_sha")
    if not isinstance(consumer_base, str) or not is_ancestor(repo, control_review_introduction, consumer_base):
        raise ValueError("reference activation consumer began before independent T01 control review")
    base_state = yaml_object(blob(repo, consumer_base, "planning/backlog.yaml"), "A03 T02 claim base")
    base_control = backlog_task(base_state, REFERENCE_ACTIVATION_CONTROL_TASK_ID) or {}
    base_consumer = backlog_task(base_state, REFERENCE_ACTIVATION_CONSUMER_TASK_ID) or {}
    if (
        base_control.get("status") != "DONE"
        or base_control.get("review", {}).get("result") != "approved"
        or base_consumer.get("status") != "READY"
    ):
        raise ValueError("reference activation T02 base predates independent T01 approval or is not READY")
    consumer_candidate = tasks[1]["review_control"]["attempts"][-1]["submission"]["candidate_commit"]
    consumer_range = git(repo, "rev-list", "--reverse", f"{consumer_base}..{consumer_candidate}").decode().splitlines()
    claim_commits: list[str] = []
    if correction is not None:
        if consumer_base != REFERENCE_ACTIVATION_RETAINED_BASE:
            raise ValueError("activation correction shortened or substituted the retained T02 base")
        claim_commits.append(correction["reopenCommit"])
    for commit in consumer_range if correction is None else []:
        paths = commit_paths(repo, commit)
        if "planning/backlog.yaml" not in paths:
            continue
        parent = resolve_commit(repo, f"{commit}^")
        before = yaml_object(blob(repo, parent, "planning/backlog.yaml"), "A03 T02 preclaim")
        after = yaml_object(blob(repo, commit, "planning/backlog.yaml"), "A03 T02 claim")
        prior = backlog_task(before, REFERENCE_ACTIVATION_CONSUMER_TASK_ID) or {}
        current = backlog_task(after, REFERENCE_ACTIVATION_CONSUMER_TASK_ID) or {}
        if prior.get("status") == "READY" and current.get("status") == "IN_PROGRESS":
            if (
                parent != consumer_base
                or current.get("base_sha") != consumer_base
                or current.get("owner") != tasks[1].get("owner")
                or current.get("branch") != tasks[1].get("branch")
                or (current.get("lease") or {}).get("claimed_by") != current.get("owner")
                or not active_amendment_claim(after, current)
                or paths & REFERENCE_ACTIVATION_CONSUMER_SOURCE
            ):
                raise ValueError("reference activation T02 claim mixed source or changed base/owner")
            claim_commits.append(commit)
    if len(claim_commits) != 1:
        raise ValueError("reference activation lacks a single post-T01 T02 claim")
    claim_position = consumer_range.index(claim_commits[0])
    if any(
        commit_paths(repo, commit) & REFERENCE_ACTIVATION_CONSUMER_SOURCE
        for commit in consumer_range[: claim_position + 1]
    ):
        raise ValueError("reference activation T02 source preceded its claim")
    witness, introduction = immutable_record(repo, head, REFERENCE_ACTIVATION_WITNESS_PATH)
    if (
        introduction not in admitted
        or REFERENCE_ACTIVATION_WITNESS_PATH not in admitted[introduction]
        or witness.get("documentType") != "workflow-profile-presentation-compatibility"
        or blob(repo, head, REFERENCE_ACTIVATION_WITNESS_PATH)
        != blob(repo, introduction, REFERENCE_ACTIVATION_WITNESS_PATH)
        or not is_ancestor(repo, introduction, consumer_base)
    ):
        raise ValueError("reference activation witness is not the unchanged reviewed T01 introduction")
    if repair:
        if set(admitted) & set(repair["commits"]):
            raise ValueError("activation repair and original activation review ranges overlap")
        admitted.update(repair["commits"])
    return admitted, consumer_commits, introduction


def reference_activation_source_history(
    repo: Path,
    ordered: list[str],
    positions: dict[str, int],
    adoption: str,
    reactivation: str,
    admitted: dict[str, set[str]],
    original_claim: tuple[str, str, str, str, str],
) -> None:
    """Freeze A03 source; attribute later shared tests to the original active task."""

    source = (
        REFERENCE_ACTIVATION_CONTROL_SOURCE
        | REFERENCE_ACTIVATION_CONSUMER_SOURCE
        | {REFERENCE_ACTIVATION_CORRECTION_ADR, REFERENCE_ACTIVATION_REPAIR_ADR}
    )
    for commit in ordered[positions[REFERENCE_ACTIVATION_CAMPAIGN_START] :]:
        paths = commit_paths(repo, commit)
        overlap = paths & source
        if overlap and commit not in admitted:
            parent = resolve_commit(repo, f"{commit}^")
            original_test_edit = (
                positions[commit] > positions[reactivation]
                and overlap.issubset(REFERENCE_ACTIVATION_SHARED_ORIGINAL_TESTS)
                and all(adopted_continuation_active_at(repo, at, *original_claim) for at in (parent, commit))
            )
            if not original_test_edit:
                raise ValueError("reference activation changed an A03 source outside its reviewed task range")
        if commit in admitted and positions[commit] > positions[adoption]:
            raise ValueError("reference activation reviewed task source postdates amendment adoption")


def reference_activation_consumer_errors(repo: Path, head: str, consumer_base: str) -> list[str]:
    """Check committed 1.8 selectors and the exact pinned 33-page/66-entry shape."""

    from ui_conformance import baseline_document_errors

    errors: list[str] = []
    extension_path = "verification/extensions/desktop-ui.json"
    baseline_path = "verification/baselines/desktop-ui.json"
    prior_extension = json_object(blob(repo, consumer_base, extension_path), "T02 base desktop activation")
    extension = json_object(blob(repo, head, extension_path), "1.8 desktop activation")
    prior_baseline = json_object(blob(repo, consumer_base, baseline_path), "T02 base desktop baseline")
    baseline = json_object(blob(repo, head, baseline_path), "1.8 desktop baseline")
    expected_extension = copy.deepcopy(prior_extension)
    expected_extension["referenceId"] = ADOPTED_CONTINUATION_APPROVED_REFERENCE
    expected_extension["referencePackageSha256"] = "cd8995fdcea2fe44452eaa1fdd258b6f9fab5714cbd443a81a8e5b4251220b94"
    if extension != expected_extension or extension.get("mode") != "approved-reference-application":
        errors.append("reference activation desktop extension changed beyond exact approved 1.8 selectors")
    expected_baseline = copy.deepcopy(prior_baseline)
    expected_baseline.update(
        referenceId=ADOPTED_CONTINUATION_APPROVED_REFERENCE,
        referencePackageSha256=expected_extension["referencePackageSha256"],
        referenceApprovalCommit="acdc67b616f5ecdec448f57a7efe46e4f359aa9f",
        entries=baseline.get("entries"),
    )
    if baseline != expected_baseline or baseline.get("settings") != extension.get("visual"):
        errors.append("reference activation baseline changed renderer settings or lacks exact 1.8 provenance")
    site = json_object(blob(repo, head, "design/ui-reference/SITE_MANIFEST.json"), "approved product routes")
    raw_pages = site.get("pages")
    pages: list[str] = (
        [str(item["file"]) for item in raw_pages if isinstance(item, dict) and isinstance(item.get("file"), str)]
        if isinstance(raw_pages, list)
        else []
    )
    if not isinstance(raw_pages, list) or len(raw_pages) != 33 or len(pages) != 33 or len(set(pages)) != 33:
        errors.append("reference activation approved product page inventory is not exactly 33 unique pages")
    else:
        schema = json_object(
            blob(repo, head, "verification/desktop-ui-baseline.schema.json"), "desktop baseline schema"
        )
        errors.extend(baseline_document_errors(baseline, "approved 1.8 desktop baseline", schema, pages))
    if not isinstance(baseline.get("entries"), dict) or len(baseline["entries"]) != 66:
        errors.append("reference activation baseline requires exactly 66 page/theme entries")
    for path in sorted(REFERENCE_ACTIVATION_CONSUMER_FILES):
        if tree_entry(repo, head, path) != ("100644", "blob"):
            errors.append(f"reference activation consumer source is not a regular Git blob: {path}")
    for path in sorted(REFERENCE_ACTIVATION_CONSUMER_FILES):
        if not path.endswith(".mjs"):
            continue
        source = blob(repo, head, path).decode("utf-8")
        for field, expected in (
            ("referenceId", ADOPTED_CONTINUATION_APPROVED_REFERENCE),
            ("referencePackageSha256", expected_extension["referencePackageSha256"]),
        ):
            observed = re.findall(rf"\b{field}\s*:\s*['\"]([^'\"]+)['\"]", source)
            if observed != [expected]:
                errors.append(f"reference activation {path} lacks its single exact {field} declaration")
    return errors


def adopted_continuation_historical_planning_inputs(
    repo: Path, head: str, inherited_approval: str, continuation_packet_commit: str
) -> set[str]:
    """Separate three packet-bound planning-site test edits from T01 product."""

    review_path = "artifacts/evidence/W2-enabler-review-site-projection-repair.review.md"
    site_paths = {
        "artifacts/evidence/W2-enabler-review-site-projection-repair.md",
        "tests/foundation/test_plan_review_amendments.py",
        "tools/plan_review_site.py",
    }
    review = blob(repo, head, review_path)
    if (
        git(repo, "log", "--format=%H", head, "--", review_path).decode().splitlines()
        != [ADOPTED_CONTINUATION_SITE_REPAIR_REVIEW]
        or hashlib.sha256(review).hexdigest() != ADOPTED_CONTINUATION_SITE_REPAIR_REVIEW_SHA256
        or any(commit_paths(repo, commit) != site_paths for commit in ADOPTED_CONTINUATION_SITE_REPAIR_SOURCE)
        or commit_paths(repo, ADOPTED_CONTINUATION_SITE_REPAIR_REVIEW) != {review_path}
        or not is_ancestor(repo, ADOPTED_CONTINUATION_SITE_REPAIR_SOURCE[0], ADOPTED_CONTINUATION_SITE_REPAIR_SOURCE[1])
        or not is_ancestor(repo, ADOPTED_CONTINUATION_SITE_REPAIR_SOURCE[1], ADOPTED_CONTINUATION_SITE_REPAIR_CANDIDATE)
        or not is_ancestor(repo, ADOPTED_CONTINUATION_SITE_REPAIR_CANDIDATE, ADOPTED_CONTINUATION_SITE_REPAIR_REVIEW)
        or not is_ancestor(repo, ADOPTED_CONTINUATION_SITE_REPAIR_REVIEW, inherited_approval)
    ):
        raise ValueError("adopted continuation lacks exact reviewed planning-site repair history")
    followup_paths = {f"planning/review-site/enablers/ECR-{number:04d}.html" for number in range(1, 10)} | {
        "planning/review-site/enablers/index.html",
        "planning/review-site/manifest.json",
        "planning/review-site/waves/W1.html",
        "planning/review-site/waves/W2.html",
        "tests/foundation/test_plan_review_amendments.py",
        "tools/plan_review_check.py",
        "tools/plan_review_site.py",
    }
    followup = ADOPTED_CONTINUATION_BOOTSTRAP_FOLLOWUP
    disposition = "167dc7a457eecf85ebf1f64fb014329491a6c55f"
    bootstrap_state = yaml_object(blob(repo, disposition, "planning/backlog.yaml"), "A01 bootstrap disposition")
    bootstrap_amendment = amendment_record(bootstrap_state, "W2.A01")
    bootstrap = bootstrap_amendment.get("bootstrap") or {}
    if (
        commit_paths(repo, followup) != followup_paths
        or git(repo, "rev-parse", f"{followup}^{{tree}}").decode().strip()
        != ADOPTED_CONTINUATION_BOOTSTRAP_FOLLOWUP_TREE
        or git(repo, "rev-list", "--parents", "-n", "1", followup).decode().split()
        != [followup, "5d60cb40a28ad37cf8b903b87dc1ceed4536b402"]
        or bootstrap.get("status") != "APPROVED"
        or bootstrap.get("implementation_commit") != "68d36d6722202cc2e9a497755596cb629bb32174"
        or followup[:8] not in str((bootstrap.get("review") or {}).get("notes") or "")
        or not is_ancestor(repo, followup, disposition)
        or not is_ancestor(repo, disposition, "468cb390")
        or not is_ancestor(repo, disposition, continuation_packet_commit)
        or not is_ancestor(repo, followup, head)
    ):
        raise ValueError("adopted continuation inherited planning-site follow-up differs from packet-bound history")
    # The 907 source is exact inherited context; its separate review occurs in
    # this A02.T01 control task, not in the earlier B00 independent ledger.
    return {*ADOPTED_CONTINUATION_SITE_REPAIR_SOURCE, followup}


REFERENCE_ACTIVATION_REPAIR_ID = "W2.A05"
REFERENCE_ACTIVATION_REPAIR_PACKET = "55c6389ce39a656f4da3851cae32ae12ac80e796"
REFERENCE_ACTIVATION_REPAIR_PAUSE = "771e54a3657cdc5ff308d3a53d7b71eb48bb9214"
REFERENCE_ACTIVATION_REPAIR_ADR = "docs/adr/ADR-0041-authenticate-reviewed-activation-control-repairs.md"
REFERENCE_ACTIVATION_REPAIR_SOURCE = (
    frozenset(
        {
            "tools/ui_change_gate.py",
            "tests/foundation/test_ui_change_gate.py",
            "docs/automation/design-first-ui-changes.md",
            "docs/adr/index.json",
            REFERENCE_ACTIVATION_REPAIR_ADR,
        }
    ),
    frozenset(
        {
            "tools/ui_conformance.py",
            "tests/desktop/test_ui_conformance.py",
            "docs/automation/ui-conformance-verification.md",
            REFERENCE_ACTIVATION_REPAIR_ADR,
        }
    ),
)


def reference_activation_repair_state(repo: Path, commit: str) -> dict[str, Any]:
    document = yaml.load(blob(repo, commit, "planning/backlog.yaml"), Loader=yaml.CSafeLoader)
    if not isinstance(document, dict):
        raise ValueError("activation repair backlog is not an object")
    return document


def reference_activation_repair_packet(repo: Path, head: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Authenticate the exact approved repair and immutable completed bootstrap."""
    import taskctl

    current = reference_activation_repair_state(repo, head)
    child = amendment_record(current, REFERENCE_ACTIVATION_REPAIR_ID)
    packet, packet_commit, owner_commit = approved_amendment_packet(repo, head, child)
    frozen = reference_activation_repair_state(repo, REFERENCE_ACTIVATION_REPAIR_PAUSE)
    parent = amendment_record(frozen, "W2.A03")
    sibling = amendment_record(frozen, "W2.A04")
    approved = amendment_record(
        reference_activation_repair_state(repo, "cc2e61b55ebf0802845a217a78ccf49966e9bfd8"), child["id"]
    )
    ledger, introduction = immutable_record(
        repo,
        head,
        "artifacts/evidence/W2.A05.B00.review-R01.json",
        "b2afdd29ad541055438ec8c67d8fa014a41c8e1ae715fbb9b288c9d1d45a2c7c",
        evidence=True,
    )
    if (
        packet_commit != REFERENCE_ACTIVATION_REPAIR_PACKET
        or hashlib.sha256(
            blob(repo, packet_commit, "planning/enabler-change-requests/ECR-0013.packet.json")
        ).hexdigest()
        != "56f521d708266021121b2a3391506cc771c7d32e32442d29dc5e58ba356f20c1"
        or owner_commit != "b54f24c222f631700056574a08056f660696d305"
        or child.get("change_request_id") != "ECR-0013"
        or packet.get("authorizedTaskIds") != ["W2.A05.T01", "W2.A05.T02"]
        or child.get("correction") != packet["authorityChain"]["pausedPredecessor"]
        or taskctl.canonical_json_sha256(parent) != "bdad5e81327e32ee322db436dc569898ce314d29058e53b0cfe67ed6192e0b03"
        or taskctl.canonical_json_sha256(sibling) != "c15d980f77933ba92e926980d6bc57b0f918430a4d0272952b922889a97e9ffc"
        or amendment_record(current, "W2.A03").get("tasks") != parent["tasks"]
        or amendment_record(current, "W2.A04") != sibling
        or child.get("bootstrap") != approved.get("bootstrap")
        or any(
            child.get(field) != approved.get(field)
            for field in (
                "id",
                "kind",
                "target_wave",
                "change_request_id",
                "approval_reference",
                "correction",
                "contributions",
            )
        )
        or child["bootstrap"].get("status") != "APPROVED"
        or ledger.get("result") != "approved"
        or ledger.get("findings") != []
        or ledger.get("candidateCommit") != child["bootstrap"].get("implementation_commit")
        or ledger.get("submissionCommit") != "2a90fddc193ec93bf26f448f813d7ee0c4ca007a"
        or ledger.get("reviewer") != child["bootstrap"].get("review", {}).get("reviewer")
        or not independent_identity(ledger.get("reviewer"), child["bootstrap"].get("implementer"))
        or introduction != "10f0d06e220b43272bfe2f54f791530b634f8b8b"
        or not is_ancestor(repo, introduction, "cc2e61b55ebf0802845a217a78ccf49966e9bfd8")
        or not is_ancestor(repo, "cc2e61b55ebf0802845a217a78ccf49966e9bfd8", head)
    ):
        raise ValueError("activation repair packet, frozen predecessor/A04 or independent B00 differs")
    for path, digest in (
        (
            "planning/enabler-change-requests/ECR-0013.preflight-01.json",
            "140350618878d3f73f921f092054c75c7cb7352fb3ed9a0ebc9bea646918a991",
        ),
        (
            "planning/enabler-change-requests/ECR-0013.maintenance-binding.json",
            "d550768944a0b142035270af47e2dcace88c7021edd0251d0a30e5ffc3e09be5",
        ),
    ):
        _, introduced = immutable_record(repo, head, path, digest)
        if not is_ancestor(repo, introduced, packet_commit):
            raise ValueError("activation repair planning binding postdates its owner-approved packet")
    return child, packet


def reference_activation_inert_projection_map(repo: Path, head: str) -> dict[str, set[str]]:
    """Return only exact independently delivered inert rows; never a caller declaration."""
    reference_activation_repair_preceding_sources(repo, head)
    frozen = reference_activation_repair_state(repo, REFERENCE_ACTIVATION_REPAIR_PAUSE)
    parent, sibling = amendment_record(frozen, "W2.A03"), amendment_record(frozen, "W2.A04")
    parent_ranges = correction_submission_ranges(repo, head, {"tasks": [parent["tasks"][1]]})
    correction_submission_ranges(repo, head, sibling)
    sibling_packet, _, _ = approved_amendment_packet(repo, head, sibling)
    adoption = adopted_continuation_adoption(repo, REFERENCE_ACTIVATION_REPAIR_PAUSE, frozen, sibling, sibling_packet)
    if adoption != "8f1a47f8a334fe32330e75f637f9b71b83669a03":
        raise ValueError("activation repair inert projection has substituted A04 delivery")
    reference_activation_correction_slice_history(
        repo,
        head,
        sibling["tasks"][0],
        str(sibling["campaign"]["owner"]),
        sibling["completion"]["exit_review_control"]["attempts"][-1]["submission"]["candidate_commit"],
    )
    reference_activation_correction_checkpoint_reviews(repo, head, sibling, adoption)
    for attempt in sibling["completion"]["exit_review_control"]["attempts"]:
        for ref in (attempt["ledger"], attempt["submission"]["evidence_reference"]):
            immutable_record(repo, head, ref["path"], ref["sha256"], evidence=True)
    for checkpoint in frozen["waves"]:
        if checkpoint["id"] == "W2":
            for item in checkpoint["checkpoints"]:
                for ref in item["evidence"]:
                    if isinstance(ref, dict) and ref.get("amendment_id") == "W2.A04":
                        immutable_record(repo, head, ref["path"], ref["sha256"], evidence=True)
    record, _ = immutable_record(
        repo,
        head,
        "planning/enabler-change-requests/ECR-0013.preflight-01.json",
        "140350618878d3f73f921f092054c75c7cb7352fb3ed9a0ebc9bea646918a991",
    )
    rows = record.get("historicalProjectionRows")
    if not isinstance(rows, list) or len(rows) != 6:
        raise ValueError("activation repair inert projection inventory differs")
    admitted: dict[str, set[str]] = {}
    for row in rows:
        commit, path = row["commit"], row["path"]
        previous = resolve_commit(repo, f"{commit}^")
        if (
            commit in admitted
            or path != "planning/review-site/waves/W2.html"
            or row["mode"] != "100644"
            or len(git(repo, "rev-list", "--parents", "-n", "1", commit).decode().split()) != 2
            or any(tree_entry(repo, at, path) != ("100644", "blob") for at in (previous, commit))
            or hashlib.sha256(blob(repo, previous, path)).hexdigest() != row["beforeBlobSha256"]
            or hashlib.sha256(blob(repo, commit, path)).hexdigest() != row["afterBlobSha256"]
            or not any(
                r["base"] != commit
                and is_ancestor(repo, r["base"], previous)
                and is_ancestor(repo, commit, r["candidate"])
                for r in parent_ranges
            )
            or not is_ancestor(repo, commit, REFERENCE_ACTIVATION_REPAIR_PAUSE)
        ):
            raise ValueError("activation repair inert projection lacks exact regular blobs and reviewed delivery")
        admitted[commit] = {path}
    return admitted


def reference_activation_repair_preceding_sources(repo: Path, head: str) -> dict[str, set[str]]:
    """Verify GOV27 directly and the exact separately approved B00 source patch."""
    child, _ = reference_activation_repair_packet(repo, head)
    binding, _ = immutable_record(
        repo,
        head,
        "planning/enabler-change-requests/ECR-0013.maintenance-binding.json",
        "d550768944a0b142035270af47e2dcace88c7021edd0251d0a30e5ffc3e09be5",
    )
    proposal, _ = immutable_record(
        repo,
        head,
        "artifacts/evidence/W2.A05.B00.addendum-01.proposal.json",
        "2222d84429772151da87fd8fbadaa71d1aa01205db91083bb509f48bbec2620f",
    )
    addendum_path = "planning/wave-amendment-approvals/W2.A05.B00.addendum-01.json"
    addendum, patch_commit = immutable_record(
        repo, head, addendum_path, "c64eee49399600bb5630322ba7556be9309c331b48a0cb5e626667d5be39be1e"
    )
    readiness, readiness_intro = immutable_record(
        repo,
        head,
        "artifacts/evidence/W2.A05.B00.addendum-01.review-R01.json",
        "75c1de33033ebcbfa5a8ecc112fb344ecd60a2c51d1f26ef3aa9b90baa3e8239",
        evidence=True,
    )
    patch_path = proposal["sourcePatch"]["path"]
    if (
        hashlib.sha256(blob(repo, head, patch_path)).hexdigest() != proposal["sourcePatch"]["sha256"]
        or patch_commit != "57f5c3f264611f59cd2778ff13b5082b2726e24b"
        or proposal.get("baseApprovalCommit") != "b54f24c222f631700056574a08056f660696d305"
        or addendum.get("status") != "APPROVED"
        or readiness.get("result") != "approved"
        or readiness_intro != "d6c61300987f378c26b361e923e439b267923604"
        or not is_ancestor(repo, readiness_intro, patch_commit)
        or not is_ancestor(repo, patch_commit, child["bootstrap"]["implementation_commit"])
    ):
        raise ValueError("activation repair B00 source exception lacks exact proposal/patch/owner/review")
    admitted: dict[str, set[str]] = {}
    previous = binding["predecessorCommit"]
    for row in binding["history"]:
        commit = row["commit"]
        paths = {item["path"] for item in row["changedFiles"]}
        if (
            row["parent"] != previous
            or resolve_commit(repo, f"{commit}^") != previous
            or len(git(repo, "rev-list", "--parents", "-n", "1", commit).decode().split()) != 2
            or commit_paths(repo, commit) != paths
        ):
            raise ValueError("activation repair GOV27 has omitted, extra or substituted source history")
        for item in row["changedFiles"]:
            for at, expected in ((previous, item["before"]), (commit, item["after"])):
                entry = tree_entry(repo, at, item["path"])
                if (expected is None and entry is not None) or (
                    expected is not None
                    and (
                        entry != (expected["mode"], "blob")
                        or expected["mode"] != "100644"
                        or hashlib.sha256(blob(repo, at, item["path"])).hexdigest() != expected["sha256"]
                    )
                ):
                    raise ValueError("activation repair GOV27 source mode or bytes differ")
        admitted[commit] = paths
        previous = commit
    if previous != binding["finalDispositionCommit"]:
        raise ValueError("activation repair GOV27 final disposition differs")
    patch_sources = {item["path"]: item for item in proposal["sourceBindings"]}
    if (
        set(patch_sources) != {"tools/taskctl.py", "tests/foundation/test_taskctl_workflow.py"}
        or commit_paths(repo, patch_commit) != {*patch_sources, addendum_path}
        or len(git(repo, "rev-list", "--parents", "-n", "1", patch_commit).decode().split()) != 2
    ):
        raise ValueError("activation repair B00 source patch has extra or mixed history")
    for path, item in patch_sources.items():
        parent = resolve_commit(repo, f"{patch_commit}^")
        if (
            item["mode"] != "100644"
            or any(tree_entry(repo, at, path) != ("100644", "blob") for at in (parent, patch_commit, head))
            or hashlib.sha256(blob(repo, parent, path)).hexdigest() != item["beforeSha256"]
            or git(repo, "rev-parse", f"{parent}:{path}").decode().strip() != item["beforeGitBlob"]
            or hashlib.sha256(blob(repo, patch_commit, path)).hexdigest() != item["afterSha256"]
            or blob(repo, head, path) != blob(repo, patch_commit, path)
        ):
            raise ValueError("activation repair B00 source bytes/modes differ")
    for item in [*binding["finalSourceFiles"], *binding["finalEvidenceFiles"]]:
        path = item["path"]
        if tree_entry(repo, head, path) != ("100644", "blob"):
            raise ValueError("activation repair preceding source/evidence mode differs")
        if path not in patch_sources and hashlib.sha256(blob(repo, head, path)).hexdigest() != item["sha256"]:
            raise ValueError("activation repair preceding source or adverse evidence was rewritten")
        touches = git(repo, "log", "--format=%H", f"{previous}..{head}", "--", path).decode().splitlines()
        if touches != ([patch_commit] if path in patch_sources else []):
            raise ValueError("activation repair preceding source/evidence has unapproved later history")
    admitted[patch_commit] = commit_paths(repo, patch_commit)
    return admitted


def reference_activation_repair_active(repo: Path, commit: str, task: dict[str, Any]) -> bool:
    """Require both real claim endpoints and contemporaneous campaign/task leases."""
    state = reference_activation_repair_state(repo, commit)
    child = amendment_record(state, REFERENCE_ACTIVATION_REPAIR_ID)
    current = backlog_task(state, str(task["id"])) or {}
    campaign = child.get("campaign") or {}
    observed = int(git(repo, "show", "-s", "--format=%ct", commit).decode())
    leases = [current.get("lease") or {}, campaign.get("lease") or {}]
    try:
        live = all(
            lease.get("claimed_by") == task.get("owner")
            and datetime.fromisoformat(lease["claimed_at"].replace("Z", "+00:00")).timestamp()
            <= observed
            < datetime.fromisoformat(lease["expires_at"].replace("Z", "+00:00")).timestamp()
            for lease in leases
        )
    except KeyError, TypeError, ValueError:
        live = False
    return (
        live
        and child.get("lifecycle", {}).get("status") == "ACTIVE"
        and state.get("control_plane", {}).get("active_amendment") == REFERENCE_ACTIVATION_REPAIR_ID
        and next(x for x in state["waves"] if x["id"] == "W2")["campaign"]["status"] == "PAUSED"
        and current.get("status") == "IN_PROGRESS"
        and all(current.get(field) == task.get(field) for field in ("owner", "branch", "base_sha", "worktree"))
        and current.get("worktree") == "."
        and campaign.get("status") == "ACTIVE"
        and campaign.get("scope") == "wave-amendment"
        and campaign.get("base_sha") == "11b1dbceffd1434a02a9e967e2d54ed63b330535"
        and all(campaign.get(field) == current.get(field) for field in ("owner", "branch", "worktree"))
        and campaign.get("profile") == "LOC"
        and campaign.get("platform") == "windows-x64"
    )


def reference_activation_repair_authority(repo: Path, head: str) -> dict[str, Any]:
    """Authenticate only the two reviewed repair tasks and their actual paused-parent return."""
    import taskctl
    from governance_kernel import validate_returned_predecessor_history

    child, packet = reference_activation_repair_packet(repo, head)
    frozen = reference_activation_repair_state(repo, REFERENCE_ACTIVATION_REPAIR_PAUSE)
    parent = amendment_record(frozen, "W2.A03")
    materialization = "11b1dbceffd1434a02a9e967e2d54ed63b330535"
    activation = "911e4a0b2e4adcadbb0f5095d78bc9c184ba352b"
    materialized = amendment_record(reference_activation_repair_state(repo, materialization), child["id"])
    activated = amendment_record(reference_activation_repair_state(repo, activation), child["id"])
    if (
        resolve_commit(repo, f"{materialization}^") != "cc2e61b55ebf0802845a217a78ccf49966e9bfd8"
        or resolve_commit(repo, f"{activation}^") != materialization
        or materialized.get("lifecycle", {}).get("status") != "MATERIALIZED"
        or materialized.get("campaign") is not None
        or materialized.get("tasks")
        != [taskctl.materialized_amendment_task(child["id"], t) for t in packet["taskInventory"]]
        or activated.get("lifecycle", {}).get("status") != "ACTIVE"
        or [t.get("status") for t in activated["tasks"]] != ["READY", "NOT_STARTED"]
        or any(t.get("owner") is not None or t.get("base_sha") is not None for t in activated["tasks"])
        or activated.get("campaign", {}).get("base_sha") != materialization
        or not is_ancestor(repo, activation, head)
    ):
        raise ValueError("activation repair materialization/activation is not its exact separate supported history")
    admitted: dict[str, set[str]] = {}
    outputs = {
        "planning/backlog.yaml",
        "docs/planning-implementation-plan.md",
        "planning/status-summary.md",
        "planning/review-site/enablers/ECR-0013.html",
        "planning/review-site/enablers/index.html",
        "planning/review-site/manifest.json",
        "planning/review-site/waves/W2.html",
    }
    candidates: list[str] = []
    for task, source in zip(child["tasks"], REFERENCE_ACTIVATION_REPAIR_SOURCE, strict=True):
        ranges, commits = adopted_continuation_reviewed_task_commits(repo, head, task)
        if not ranges or set(commits) & set(admitted):
            raise ValueError("activation repair task ranges are missing or overlapping")
        base = task.get("base_sha")
        if not isinstance(base, str) or not is_ancestor(repo, activation, base):
            raise ValueError("activation repair has a stale or foreign task base")
        claim = None
        seen: set[str] = set()
        ordered_rows = (
            git(
                repo,
                "rev-list",
                "--reverse",
                "--topo-order",
                "--parents",
                f"{base}..{ranges[-1]['candidate']}",
            )
            .decode()
            .splitlines()
        )
        predecessor = base
        for row in ordered_rows:
            values = row.split()
            if len(values) != 2 or values[1] != predecessor:
                raise ValueError("activation repair task range must remain linear")
            commit = values[0]
            predecessor = commit
            paths = commit_paths(repo, commit)
            previous = resolve_commit(repo, f"{commit}^")
            if "planning/backlog.yaml" in paths:
                before = backlog_task(reference_activation_repair_state(repo, previous), task["id"]) or {}
                after = backlog_task(reference_activation_repair_state(repo, commit), task["id"]) or {}
                if before.get("status") == "READY" and after.get("status") == "IN_PROGRESS":
                    if (
                        claim is not None
                        or previous != base
                        or after.get("base_sha") != base
                        or paths & set().union(*REFERENCE_ACTIVATION_REPAIR_SOURCE)
                        or not reference_activation_repair_active(repo, commit, task)
                    ):
                        raise ValueError("activation repair has a mixed, foreign or repeated task claim")
                    claim = commit
            if paths & source:
                if (
                    claim is None
                    or not is_ancestor(repo, claim, previous)
                    or any(not reference_activation_repair_active(repo, at, task) for at in (previous, commit))
                ):
                    raise ValueError("activation repair source lacks both active claim endpoints")
                if any(tree_entry(repo, commit, path) != ("100644", "blob") for path in paths & source):
                    raise ValueError("activation repair source has a missing or nonregular mode")
                seen.update(paths & source)
            if not paths.issubset(
                source
                | outputs
                | {
                    p
                    for p in paths
                    if p.startswith(f"artifacts/evidence/{task['id']}.")
                    or p.startswith(f"artifacts/evidence/{task['id']}-")
                }
            ):
                raise ValueError("activation repair task changed source outside its closed packet envelope")
        if claim is None or seen != source:
            raise ValueError("activation repair lacks a separate claim or all exact task sources")
        admitted.update(commits)
        candidates.append(ranges[-1]["candidate"])
    t01, t02 = child["tasks"]
    ledger = t01["review_control"]["attempts"][-1]["ledger"]
    _, review_intro = immutable_record(repo, head, ledger["path"], ledger["sha256"], evidence=True)
    at_t02_base = reference_activation_repair_state(repo, t02["base_sha"])
    if (
        not is_ancestor(repo, review_intro, t02["base_sha"])
        or backlog_task(at_t02_base, t01["id"]) != t01
        or (backlog_task(at_t02_base, t02["id"]) or {}).get("status") != "READY"
    ):
        raise ValueError("activation repair T02 began before independent T01 approval")
    before_index = json_object(blob(repo, activation, "docs/adr/index.json"), "pre-repair registry")
    expected_index = copy.deepcopy(before_index)
    expected_index["records"].append(
        {
            "id": "ADR-0041",
            "path": REFERENCE_ACTIVATION_REPAIR_ADR,
            "title": "Authenticate reviewed activation control repairs",
            "status": "Proposed",
            "linkedTasks": ["W2.A05.T01", "W2.A05.T02"],
        }
    )
    index_touches = [c for c, paths in admitted.items() if "docs/adr/index.json" in paths]
    adr_touches = [c for c, paths in admitted.items() if REFERENCE_ACTIVATION_REPAIR_ADR in paths]
    if (
        len(index_touches) != 1
        or not adr_touches
        or index_touches[0] != adr_touches[0]
        or tree_entry(repo, f"{adr_touches[0]}^", REFERENCE_ACTIVATION_REPAIR_ADR) is not None
        or json_object(blob(repo, head, "docs/adr/index.json"), "repair registry") != expected_index
    ):
        raise ValueError("activation repair ADR/index is not one authorized appended Proposed entry")
    parts = blob(repo, candidates[0], REFERENCE_ACTIVATION_REPAIR_ADR).decode().split("---", 2)
    metadata = yaml.safe_load(parts[1]) if len(parts) == 3 and not parts[0].strip() else {}
    if (
        not isinstance(metadata, dict)
        or metadata.get("id") != "ADR-0041"
        or metadata.get("status") != "Proposed"
        or metadata.get("deciders") != []
        or metadata.get("supersedes") != []
        or metadata.get("superseded_by") is not None
        or metadata.get("linked_tasks") != [t01["id"], t02["id"]]
        or metadata.get("affected_paths") != ["tools/ui_change_gate.py", "tools/ui_conformance.py"]
        or any(
            s not in parts[2]
            for s in (
                "## Context",
                "## Candidates",
                "## Decision",
                "## Consequences",
                "## Verification",
                "## Task links",
            )
        )
    ):
        raise ValueError("activation repair companion changed accepted architecture authority")
    t02_parts = blob(repo, candidates[1], REFERENCE_ACTIVATION_REPAIR_ADR).decode().split("---", 2)
    if (
        len(t02_parts) != 3
        or yaml.safe_load(t02_parts[1]) != metadata
        or not t02_parts[2].startswith(parts[2])
        or t02_parts[2] == parts[2]
        or not t02_parts[2][len(parts[2]) :].lstrip().startswith("## T02 implementation and verification")
        or len(t02_parts[2]) - len(parts[2]) > 10000
    ):
        raise ValueError("activation repair T02 ADR is not its bounded metadata-preserving body append")
    for commit in adr_touches:
        version = blob(repo, commit, REFERENCE_ACTIVATION_REPAIR_ADR).decode().split("---", 2)
        if (
            len(version) != 3
            or yaml.safe_load(version[1]) != metadata
            or json_object(blob(repo, commit, "docs/adr/index.json"), "historical repair registry") != expected_index
        ):
            raise ValueError("activation repair historical ADR/index authority differs")
    completion_owner = "planning/wave-amendment-approvals/W2.A05.S01.addendum-01.json"
    if tree_entry(repo, head, completion_owner) is not None:
        completion_segment = reference_activation_completion_segment(repo, head, require_review=True)
        if set(completion_segment["commits"]) & set(admitted):
            raise ValueError("A05 completion source overlaps its completed task ranges")
        admitted.update(completion_segment["commits"])
    for commit in git(repo, "rev-list", f"b54f24c222f631700056574a08056f660696d305..{head}").decode().splitlines():
        if commit_paths(repo, commit) & set().union(*REFERENCE_ACTIVATION_REPAIR_SOURCE) and commit not in admitted:
            raise ValueError("activation repair source was touched outside its reviewed tasks")
    adoption = adopted_continuation_adoption(repo, head, reference_activation_repair_state(repo, head), child, packet)
    exit_candidate = child["completion"]["exit_review_control"]["attempts"][-1]["submission"]["candidate_commit"]
    reference_activation_correction_slice_history(
        repo, head, t01, str(child["campaign"]["owner"]), exit_candidate, amendment_id=child["id"], tasks=child["tasks"]
    )
    reference_activation_correction_checkpoint_reviews(repo, head, child, adoption)
    returned = reference_activation_repair_state(repo, adoption)
    if amendment_record(returned, "W2.A03") != parent or amendment_record(returned, child["id"]) != child:
        raise ValueError("activation repair did not return its exact still-paused A03 predecessor")
    baseline = copy.deepcopy(frozen)
    baseline.pop("wave_amendments")
    baseline["control_plane"].pop("active_amendment", None)
    for wave in baseline["waves"]:
        if wave["id"] == "W2":
            wave.pop("checkpoints", None)
    original_wave = next(w for w in frozen["waves"] if w["id"] == "W2")
    expected_checkpoints = [
        *original_wave["checkpoints"],
        *taskctl.amendment_adoption_checkpoints(next(w for w in returned["waves"] if w["id"] == "W2"), child["id"]),
    ]
    for commit in (
        git(repo, "rev-list", f"{REFERENCE_ACTIVATION_REPAIR_PAUSE}..{adoption}", "--", "planning/backlog.yaml")
        .decode()
        .splitlines()
    ):
        state = reference_activation_repair_state(repo, commit)
        if [a for a in state["wave_amendments"] if a["id"] != child["id"]] != frozen["wave_amendments"]:
            raise ValueError("activation repair changed a frozen predecessor or completed sibling")
        ordinary = copy.deepcopy(state)
        ordinary.pop("wave_amendments")
        ordinary["control_plane"].pop("active_amendment", None)
        for wave in ordinary["waves"]:
            if wave["id"] == "W2":
                checkpoints = wave.pop("checkpoints", None)
        if ordinary != baseline or checkpoints != (
            expected_checkpoints if commit == adoption else original_wave["checkpoints"]
        ):
            raise ValueError("activation repair changed ordinary scope, hold or unrelated checkpoint history")
    activations: list[str] = []
    activation_campaign: dict[str, Any] | None = None
    for commit in (
        git(repo, "rev-list", "--reverse", f"{adoption}..{head}", "--", "planning/backlog.yaml").decode().splitlines()
    ):
        previous = resolve_commit(repo, f"{commit}^")
        before, after = (
            reference_activation_repair_state(repo, previous),
            reference_activation_repair_state(repo, commit),
        )
        prior_parent, next_parent = amendment_record(before, "W2.A03"), amendment_record(after, "W2.A03")
        for historical, historical_parent in ((before, prior_parent), (after, next_parent)):
            validate_returned_predecessor_history(parent, historical_parent)
            if any(
                historical_parent.get(field) != parent.get(field)
                for field in (
                    "id",
                    "kind",
                    "target_wave",
                    "change_request_id",
                    "approval_reference",
                    "contributions",
                    "correction",
                )
            ) or [a for a in historical["wave_amendments"] if a["id"] != "W2.A03"] != [
                a for a in returned["wave_amendments"] if a["id"] != "W2.A03"
            ]:
                raise ValueError("activation repair return changed frozen parent authority or completed siblings")
        validate_returned_predecessor_history(prior_parent, next_parent)
        if amendment_record(after, child["id"]) != child or next_parent["tasks"] != parent["tasks"]:
            raise ValueError("activation repair return rewrote adopted history or reopened a DONE A03 task")
        if not activations and prior_parent != parent:
            raise ValueError("activation repair parent was mutated before its separate activation")
        if prior_parent["lifecycle"]["status"] == "PAUSED" and next_parent["lifecycle"]["status"] == "ACTIVE":
            campaign = next_parent["campaign"]
            if (
                activations
                or commit_paths(repo, commit) != {"planning/backlog.yaml"}
                or next_parent["tasks"] != prior_parent["tasks"]
                or campaign.get("status") != "ACTIVE"
                or campaign.get("base_sha") != previous
                or campaign.get("scope") != "wave-amendment"
                or campaign.get("owner") != child["campaign"]["owner"]
                or campaign.get("branch") != child["campaign"]["branch"]
                or campaign.get("worktree") != "."
                or campaign.get("profile") != "LOC"
                or campaign.get("platform") != "windows-x64"
                or (campaign.get("lease") or {}).get("claimed_by") != campaign.get("owner")
                or after["control_plane"].get("active_amendment") != "W2.A03"
                or next(w for w in after["waves"] if w["id"] == "W2")["campaign"]["status"] != "PAUSED"
            ):
                raise ValueError("activation repair has a premature, foreign or mixed parent activation")
            activations.append(commit)
            activation_campaign = campaign
        if activation_campaign is not None:
            for historical_parent in (prior_parent, next_parent):
                if historical_parent == parent:
                    continue
                campaign = historical_parent.get("campaign") or {}
                if any(
                    campaign.get(field) != activation_campaign.get(field)
                    for field in ("owner", "branch", "worktree", "scope", "profile", "platform", "base_sha")
                ):
                    raise ValueError("activation repair returned campaign identity was rewritten")
                lease = campaign.get("lease")
                if (campaign.get("status") == "ACTIVE" and not lease) or (
                    lease is not None
                    and (not isinstance(lease, dict) or lease.get("claimed_by") != campaign.get("owner"))
                ):
                    raise ValueError("activation repair returned campaign lease owner differs")
    if len(activations) != 1:
        raise ValueError("activation repair lacks exactly one separate post-adoption A03 activation")
    preceding = reference_activation_repair_preceding_sources(repo, head)
    if set(preceding) & set(admitted):
        raise ValueError("activation repair preceding and task source ranges overlap")
    return {
        "commits": admitted,
        "precedingCommits": preceding,
        "adoptionCommit": adoption,
        "activationCommit": activations[0],
        "index": expected_index,
    }


def adopted_continuation_reviewed_task_commits(
    repo: Path, head: str, task: dict[str, Any], *, inert_outputs: dict[str, set[str]] | None = None
) -> tuple[list[dict[str, Any]], dict[str, set[str]]]:
    """Attribute every source commit to an immutable independent task submission."""

    inert_outputs = inert_outputs or {}
    if inert_outputs and inert_outputs != reference_activation_inert_projection_map(repo, head):
        raise ValueError("adopted continuation inert projection map is not independently authenticated")
    ranges = correction_submission_ranges(repo, head, {"tasks": [task]})
    a02_control = task.get("id") == "W2.A02.T01"
    allowed_a02_paths = set(ADOPTED_CONTINUATION_A02_CONTROL_SOURCE | ADOPTED_CONTINUATION_A02_TRACKING_OUTPUTS)
    if a02_control:
        allowed_a02_paths.add("artifacts/evidence/W2.A02.T01.task-start.md")
        for index, attempt in enumerate((task.get("review_control") or {}).get("attempts") or [], start=1):
            reference = attempt["submission"]["evidence_reference"]
            evidence_path = reference.get("path")
            ledger_path = attempt["ledger"].get("path")
            if (
                not isinstance(evidence_path, str)
                or not canonical_correction_evidence_path("W2.A02.T01", evidence_path)
                or ledger_path != f"artifacts/evidence/W2.A02.T01.review-R{index:02d}.json"
            ):
                raise ValueError("W2.A02.T01 source paths differ from approved six-file scope")
            allowed_a02_paths.update((evidence_path, ledger_path))
    admitted: dict[str, set[str]] = {}
    a02_source_seen: set[str] = set()
    for reviewed in ranges:
        net = sorted(changed_paths(repo, reviewed["base"], reviewed["candidate"]))
        if reviewed["paths"] != net:
            raise ValueError("adopted continuation reviewed task path inventory differs from Git")
        if a02_control:
            reviewed_paths = set(reviewed["paths"])
            if not reviewed_paths.issubset(allowed_a02_paths):
                raise ValueError("W2.A02.T01 source paths differ from approved six-file scope")
            a02_source_seen.update(reviewed_paths & ADOPTED_CONTINUATION_A02_CONTROL_SOURCE)
        rows = git(repo, "rev-list", "--reverse", f"{reviewed['base']}..{reviewed['candidate']}").decode().splitlines()
        for commit in rows:
            paths = commit_paths(repo, commit)
            if not paths.issubset(set(reviewed["paths"]) | inert_outputs.get(commit, set())) or commit in admitted:
                raise ValueError("adopted continuation task review has hidden or overlapping source paths")
            admitted[commit] = paths
    if a02_control and a02_source_seen != ADOPTED_CONTINUATION_A02_CONTROL_SOURCE:
        raise ValueError("W2.A02.T01 source paths differ from approved six-file scope")
    return ranges, admitted


def adopted_continuation_adoption(
    repo: Path, head: str, backlog: dict[str, Any], amendment: dict[str, Any], packet: dict[str, Any]
) -> str:
    """Authenticate task, exit, checkpoint and first ADOPTED transition."""

    from planctl import _adoption_transition_errors
    from taskctl import amendment_adoption_checkpoints, amendment_adoption_reference_errors

    identity = str(amendment["id"])
    if amendment.get("lifecycle", {}).get("status") != "ADOPTED":
        raise ValueError(f"{identity} is not adopted")
    inert_outputs = (
        reference_activation_inert_projection_map(repo, head)
        if identity == "W2.A03"
        and any(a.get("id") == REFERENCE_ACTIVATION_REPAIR_ID for a in backlog.get("wave_amendments", []))
        else None
    )
    for task in amendment.get("tasks", []):
        adopted_continuation_reviewed_task_commits(repo, head, task, inert_outputs=inert_outputs)
    errors = correction_exit_errors(repo, head, amendment, packet)
    wave = next(item for item in backlog["waves"] if item["id"] == "W2")
    checkpoints = amendment_adoption_checkpoints(wave, identity)
    if len(checkpoints) != 1:
        raise ValueError(f"{identity} lacks exactly one security adoption checkpoint")
    references = [item for item in checkpoints[0]["evidence"] if item.get("amendment_id") == identity]
    if len(references) != 1 or references[0].get("path") != f"artifacts/evidence/{identity}.adoption.json":
        raise ValueError(f"{identity} checkpoint lacks exact adoption evidence")
    errors.extend(amendment_adoption_reference_errors(repo, references[0], amendment))
    evidence, introduction = immutable_record(
        repo, head, references[0]["path"], references[0].get("sha256"), evidence=True
    )
    reference_commit = references[0].get("commit")
    if (
        evidence.get("amendmentId") != identity
        or not isinstance(reference_commit, str)
        or not is_ancestor(repo, introduction, reference_commit)
        or tree_entry(repo, reference_commit, references[0]["path"]) != ("100644", "blob")
        or blob(repo, reference_commit, references[0]["path"]) != blob(repo, head, references[0]["path"])
    ):
        errors.append(f"{identity} adoption evidence differs from checkpoint")
    candidate_commits = [
        commit
        for commit in git(repo, "rev-list", "--reverse", f"{introduction}..{head}").decode().splitlines()
        if "planning/backlog.yaml" in commit_paths(repo, commit)
        and amendment_record(yaml_object(blob(repo, commit, "planning/backlog.yaml"), "adoption state"), identity)
        .get("lifecycle", {})
        .get("status")
        == "ADOPTED"
    ]
    if not candidate_commits:
        errors.append(f"{identity} has no ADOPTED transition")
        adoption = ""
    else:
        adoption = candidate_commits[0]
        errors.extend(_adoption_transition_errors(repo, identity, adoption))
        if not is_ancestor(repo, introduction, adoption) or introduction == adoption:
            errors.append(f"{identity} adoption evidence did not precede transition")
    if errors:
        raise ValueError("; ".join(errors))
    return adoption


def adopted_continuation_original_task(repo: Path, head: str, backlog: dict[str, Any], current: dict[str, Any]) -> str:
    """Bind ordinary T01 to the immutable human-approved W2 task/slice packet."""

    import taskctl

    bases = [item for item in backlog.get("wave_approval_bases", []) if item.get("wave_id") == "W2"]
    wave = next(item for item in backlog["waves"] if item["id"] == "W2")
    if len(bases) != 1 or wave.get("approval") != bases[0].get("approval"):
        raise ValueError("adopted continuation lacks the exact W2 approval base")
    record = bases[0]
    packet_commit, approval_commit = record.get("packet_commit"), record.get("record_commit")
    if (
        not isinstance(packet_commit, str)
        or not isinstance(approval_commit, str)
        or resolve_commit(repo, packet_commit) != packet_commit
        or resolve_commit(repo, approval_commit) != approval_commit
        or resolve_commit(repo, f"{approval_commit}^") != packet_commit
        or not is_ancestor(repo, approval_commit, ADOPTED_CONTINUATION_BASE)
        or wave["approval"].get("status") != "APPROVED"
        or wave["approval"].get("approved_commit") != packet_commit
        or HUMAN_ID.fullmatch(str(wave["approval"].get("approved_by"))) is None
    ):
        raise ValueError("adopted continuation W2 packet/human approval ancestry differs")
    original = yaml_object(blob(repo, packet_commit, "planning/backlog.yaml"), "frozen W2 packet")
    approved = yaml_object(blob(repo, approval_commit, "planning/backlog.yaml"), "W2 approval introduction")
    original_task = backlog_task(original, ADOPTED_CONTINUATION_TASK_ID)
    original_wave = next(item for item in original["waves"] if item["id"] == "W2")
    approved_wave = next(item for item in approved["waves"] if item["id"] == "W2")
    if (
        original_task is None
        or original_task.get("status") != "NOT_STARTED"
        or original_task.get("review_gate") != "agent-review"
        or original_task.get("experience_change") is not None
        or original_wave.get("approval", {}).get("status") == "APPROVED"
        or approved_wave.get("approval") != wave["approval"]
        or taskctl.corrective_contract(original, original_task) != taskctl.corrective_contract(backlog, current)
        or current.get("review_gate") != "agent-review"
        or current.get("experience_change") is not None
    ):
        raise ValueError("adopted continuation ordinary task/slice differs from approved W2")
    return taskctl.canonical_json_sha256(taskctl.corrective_contract(original, original_task))


def adopted_continuation_live_claim(
    repo: Path, base: str, head: str, contract: dict[str, Any], policy: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any], str]:
    """Require the sole active original T01 owner, base, branch and lease."""

    from taskctl import require_active_lease, wave_resume_record_errors

    authority = contract.get("adoptedContinuationAuthority")
    selectors = {
        "amendmentId": "W2.A02",
        "changeRequestId": "ECR-0010",
        "controlTaskId": "W2.A02.T01",
        "inheritedAmendmentId": "W2.A01",
        "inheritedTaskId": "W2.A01.T02",
        "inheritedContractPath": ADOPTED_CONTINUATION_INHERITED_CONTRACT_PATH,
    }
    if (
        head != resolve_commit(repo, "HEAD")
        or base != ADOPTED_CONTINUATION_BASE
        or contract.get("schemaVersion") not in {"1.3", "1.4"}
        or contract.get("taskId") != ADOPTED_CONTINUATION_TASK_ID
        or contract.get("changeKind") != "defect-restoration"
        or not isinstance(authority, dict)
        or any(authority.get(key) != value for key, value in selectors.items())
        or contract.get("contractPath") != ADOPTED_CONTINUATION_CONTRACT_PATH
    ):
        raise ValueError("adopted continuation selector/head/base is not the approved T01 lane")
    backlog = yaml_object(blob(repo, head, "planning/backlog.yaml"), "adopted continuation backlog")
    task = backlog_task(backlog, ADOPTED_CONTINUATION_TASK_ID)
    wave = next(item for item in backlog["waves"] if item["id"] == "W2")
    active = [
        item
        for item in backlog_tasks(backlog)
        if item.get("wave") == "W2" and item.get("status") in {"IN_PROGRESS", "REVIEW"}
    ]
    owner = task.get("owner") if task else None
    branch = git(repo, "branch", "--show-current").decode().strip()
    root = Path(git(repo, "rev-parse", "--show-toplevel").decode().strip()).resolve()
    if (
        task is None
        or active != [task]
        or task.get("status") not in {"IN_PROGRESS", "REVIEW"}
        or task.get("base_sha") != base
        or not isinstance(owner, str)
        or not owner
        or contract.get("implementationAgent") != f"agent:{owner}"
        or task.get("branch") != branch
        or task.get("worktree") != "."
        or root != repo
        or wave.get("campaign", {}).get("status") != "ACTIVE"
        or wave.get("campaign", {}).get("scope") != "wave"
        or wave.get("campaign", {}).get("owner") != owner
        or wave.get("campaign", {}).get("branch") != branch
        or wave.get("campaign", {}).get("worktree") != "."
        or wave.get("campaign", {}).get("profile") != "LOC"
        or wave.get("campaign", {}).get("platform") != "windows-x64"
        or backlog.get("control_plane", {}).get("active_amendment") is not None
        or any(
            (item.get("campaign") or {}).get("status") in {"ACTIVE", "REVIEW"}
            for item in backlog.get("wave_amendments", [])
        )
    ):
        raise ValueError("adopted continuation requires the exact sole active W2/T01 claim")
    try:
        require_active_lease(wave["campaign"], owner, "W2 campaign")
        require_active_lease(task, owner, "CAP-05.S01.T01")
        if wave_resume_record_errors(backlog, "W2", wave["campaign"], repo):
            raise ValueError("adopted continuation current W2 resume history is invalid")
    except SystemExit as exc:
        raise ValueError(f"adopted continuation lease is stale or foreign: {exc}") from exc
    ordered = git(repo, "rev-list", "--reverse", f"{base}..{head}").decode().splitlines()
    if not ordered or resolve_commit(repo, f"{ordered[0]}^") != base:
        raise ValueError("adopted continuation original claim is not a direct child of its frozen base")
    first = yaml_object(blob(repo, ordered[0], "planning/backlog.yaml"), "original T01 claim")
    claimed = backlog_task(first, ADOPTED_CONTINUATION_TASK_ID) or {}
    if (
        claimed.get("status") != "IN_PROGRESS"
        or claimed.get("base_sha") != base
        or claimed.get("owner") != owner
        or claimed.get("branch") != branch
        or claimed.get("worktree") != "."
        or (claimed.get("lease") or {}).get("claimed_by") != owner
        or any(
            is_implementation_path(path, policy) or path.startswith(f"{policy['referenceRoot']}/")
            for path in commit_paths(repo, ordered[0])
        )
    ):
        raise ValueError("adopted continuation original T01 claim/base is not authentic")
    task_digest = adopted_continuation_original_task(repo, head, backlog, task)
    return backlog, task, task_digest


def adopted_continuation_projection_at(repo: Path, commit: str) -> dict[str, Any]:
    """Select the committed backlog object; reused blobs share one projection."""

    blob_id = git(repo, "rev-parse", f"{commit}:planning/backlog.yaml").decode().strip()
    if not re.fullmatch(r"[0-9a-f]{40}", blob_id):
        raise ValueError("historical W2/T01 backlog has an invalid Git blob ID")
    return adopted_continuation_projection_for_blob(repo, blob_id)


@lru_cache(maxsize=64)
def adopted_continuation_projection_for_blob(repo: Path, blob_id: str) -> dict[str, Any]:
    """Parse one immutable YAML blob and retain only bounded authority fields."""

    payload = git(repo, "cat-file", "blob", blob_id).decode("utf-8")
    state = yaml.load(payload, Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader))
    if not isinstance(state, dict):
        raise ValueError("historical W2/T01 backlog is not a YAML object")
    wave = next(item for item in state.get("waves", []) if item.get("id") == "W2")
    campaign = wave.get("campaign") or {}
    task = backlog_task(state, ADOPTED_CONTINUATION_TASK_ID) or {}
    campaign_fields = (
        "status",
        "scope",
        "owner",
        "branch",
        "worktree",
        "base_sha",
        "profile",
        "platform",
        "updated_at",
        "lease",
        "resume_records",
    )
    task_fields = ("status", "base_sha", "owner", "branch", "worktree", "lease")
    return {
        "waves": [{"id": "W2", "campaign": {field: campaign.get(field) for field in campaign_fields}}],
        "task": {field: task.get(field) for field in task_fields},
        "control_plane": {
            "revision": (state.get("control_plane") or {}).get("revision"),
            "active_amendment": (state.get("control_plane") or {}).get("active_amendment"),
        },
    }


@lru_cache(maxsize=512)
def adopted_continuation_active_at(
    repo: Path, commit: str, base: str, owner: str, branch: str, profile: str, platform: str
) -> bool:
    """Attribute a source edit to the original active Wave/task on both sides."""

    state = adopted_continuation_projection_at(repo, commit)
    task = state["task"]
    wave: dict[str, Any] = next((item for item in state.get("waves", []) if item.get("id") == "W2"), {})
    campaign = wave.get("campaign") or {}
    return (
        task.get("status") in {"IN_PROGRESS", "REVIEW"}
        and task.get("base_sha") == base
        and task.get("owner") == owner
        and task.get("branch") == branch
        and task.get("worktree") == "."
        and (task.get("lease") or {}).get("claimed_by") == owner
        and campaign.get("status") == "ACTIVE"
        and campaign.get("scope") == "wave"
        and campaign.get("owner") == owner
        and campaign.get("branch") == branch
        and campaign.get("worktree") == "."
        and campaign.get("profile") == profile
        and campaign.get("platform") == platform
        and (campaign.get("lease") or {}).get("claimed_by") == owner
        and (state.get("control_plane") or {}).get("active_amendment") is None
    )


def adopted_continuation_authority(
    repo: Path, base: str, head: str, contract: dict[str, Any], policy: dict[str, Any]
) -> dict[str, Any]:
    """Authenticate the original-base approved publication and reviewed continuations."""

    from planctl import _reference_publication_content_errors

    backlog, task, task_digest = adopted_continuation_live_claim(repo, base, head, contract, policy)
    authority = contract["adoptedContinuationAuthority"]
    activated = contract["schemaVersion"] == "1.4"
    activation_authority = contract.get("referenceActivationAuthority") if activated else None
    amendments = backlog.get("wave_amendments", [])
    expected_amendments = ["W2.A01", "W2.A02", "W2.A03"] if activated else ["W2.A01", "W2.A02"]
    if activated and any(item.get("id") == REFERENCE_ACTIVATION_CORRECTION_ID for item in amendments):
        expected_amendments.append(REFERENCE_ACTIVATION_CORRECTION_ID)
    repaired = activated and any(item.get("id") == REFERENCE_ACTIVATION_REPAIR_ID for item in amendments)
    if repaired:
        if REFERENCE_ACTIVATION_CORRECTION_ID not in expected_amendments:
            raise ValueError("activation repair lacks its exact adopted A04 predecessor")
        expected_amendments.append(REFERENCE_ACTIVATION_REPAIR_ID)
    if [item.get("id") for item in amendments if item.get("target_wave") == "W2"][
        -len(expected_amendments) :
    ] != expected_amendments:
        raise ValueError("adopted continuation requires the exact ordered W2 amendments")
    inherited = amendment_record(backlog, "W2.A01")
    continuation = amendment_record(backlog, "W2.A02")
    inherited_packet, inherited_packet_commit, inherited_approval = approved_amendment_packet(repo, head, inherited)
    continuation_packet, continuation_packet_commit, continuation_approval = approved_amendment_packet(
        repo, head, continuation
    )
    activation = amendment_record(backlog, REFERENCE_ACTIVATION_AMENDMENT_ID) if activated else None
    if activation is not None:
        activation_packet, activation_packet_commit, activation_approval = approved_amendment_packet(
            repo, head, activation
        )
        if (
            activation_packet_commit != REFERENCE_ACTIVATION_PACKET_COMMIT
            or activation.get("change_request_id") != "ECR-0011"
            or activation_packet.get("authorizedTaskIds")
            != [REFERENCE_ACTIVATION_CONTROL_TASK_ID, REFERENCE_ACTIVATION_CONSUMER_TASK_ID]
            or activation_packet.get("governedExperience", {}).get("referenceId")
            != ADOPTED_CONTINUATION_APPROVED_REFERENCE
            or not is_ancestor(repo, continuation_approval, activation_approval)
        ):
            raise ValueError("reference activation lacks exact approved ECR-0011 task/package authority")
        reference_activation_bootstrap_authority(repo, head, activation, activation_packet)
    if (
        inherited.get("change_request_id") != "ECR-0009"
        or continuation.get("change_request_id") != "ECR-0010"
        or inherited_packet.get("authorizedTaskIds") != ["W2.A01.T01", "W2.A01.T02"]
        or continuation_packet.get("authorizedTaskIds") != ["W2.A02.T01"]
        or inherited_packet.get("governedExperience", {}).get("referenceId") != ADOPTED_CONTINUATION_APPROVED_REFERENCE
        or continuation_packet.get("governedExperience", {}).get("referenceId")
        != ADOPTED_CONTINUATION_APPROVED_REFERENCE
    ):
        raise ValueError("adopted continuation packets do not bind exact A01/A02 task and reference authority")
    inherited_adoption = adopted_continuation_adoption(repo, head, backlog, inherited, inherited_packet)
    adoption = adopted_continuation_adoption(repo, head, backlog, continuation, continuation_packet)
    activation_adoption = (
        adopted_continuation_adoption(repo, head, backlog, activation, activation_packet)
        if activation is not None
        else None
    )
    if (
        authority.get("adoptionCommit") != adoption
        or not is_ancestor(repo, inherited_approval, inherited_adoption)
        or not is_ancestor(repo, inherited_adoption, continuation_packet_commit)
        or not is_ancestor(repo, continuation_approval, adoption)
        or not is_ancestor(repo, adoption, head)
    ):
        raise ValueError("adopted continuation approved amendment/adoption ancestry differs")
    if activation is not None and (
        not isinstance(activation_authority, dict)
        or activation_adoption is None
        or activation_authority.get("adoptionCommit") != activation_adoption
        or not is_ancestor(repo, adoption, activation_packet_commit)
        or not is_ancestor(repo, activation_approval, activation_adoption)
        or not is_ancestor(repo, activation_adoption, head)
    ):
        raise ValueError("reference activation amendment/adoption ancestry differs")
    for item in continuation_packet.get("governedExperience", {}).get("files", []):
        path = item.get("path") if isinstance(item, dict) else None
        if (
            not isinstance(path, str)
            or not path.startswith(f"{policy['referenceRoot']}/")
            or tree_entry(repo, continuation_packet_commit, path) != ("100644", "blob")
            or hashlib.sha256(blob(repo, continuation_packet_commit, path)).hexdigest() != item.get("sha256")
            or blob(repo, continuation_packet_commit, path) != blob(repo, head, path)
        ):
            raise ValueError("adopted continuation changed the packet-bound approved 1.8 package")
    if activation is not None and activation_packet.get("governedExperience", {}).get(
        "files"
    ) != continuation_packet.get("governedExperience", {}).get("files"):
        raise ValueError("reference activation packet differs from unchanged approved 1.8 package")

    inherited_task = backlog_task(backlog, "W2.A01.T02")
    control_task = backlog_task(backlog, "W2.A02.T01")
    if inherited_task is None or control_task is None:
        raise ValueError("adopted continuation lacks materialized reviewed predecessor/control tasks")
    inherited_ranges, inherited_source = adopted_continuation_reviewed_task_commits(repo, head, inherited_task)
    if not inherited_ranges:
        raise ValueError("adopted continuation inherited task has no independent review")
    inherited_candidate = inherited_ranges[-1]["candidate"]
    inherited_base = inherited_task.get("base_sha")
    if not isinstance(inherited_base, str) or not re.fullmatch(r"[0-9a-f]{40}", inherited_base):
        raise ValueError("adopted continuation inherited task lacks its canonical base")
    predecessor = intentional_amendment_control_predecessor(repo, inherited_candidate, inherited_base, inherited)
    inherited_contract, inherited_contract_intro = immutable_record(
        repo, head, ADOPTED_CONTINUATION_INHERITED_CONTRACT_PATH
    )
    historical_schema = json_object(
        blob(repo, inherited_candidate, str(policy["contractSchemaPath"])), "historical v1.2 UI schema"
    )
    if (
        list(Draft202012Validator(historical_schema).iter_errors(inherited_contract))
        or inherited_contract.get("schemaVersion") != "1.2"
        or inherited_contract.get("taskId") != "W2.A01.T02"
        or inherited_contract.get("changeKind") != "intentional-design-change"
        or inherited_contract.get("contractPath") != ADOPTED_CONTINUATION_INHERITED_CONTRACT_PATH
        or inherited_contract.get("implementationAgent") != f"agent:{inherited_task.get('owner')}"
        or inherited_contract.get("intentionalAmendmentAuthority")
        != {
            "amendmentId": "W2.A01",
            "changeRequestId": "ECR-0009",
            "controlTaskId": "W2.A01.T01",
            "referenceApprovalPath": INTENTIONAL_AMENDMENT_REFERENCE_APPROVAL_PATH,
        }
        or inherited_contract_intro == inherited_candidate
        or not is_ancestor(repo, inherited_contract_intro, inherited_candidate)
        or blob(repo, inherited_candidate, ADOPTED_CONTINUATION_INHERITED_CONTRACT_PATH)
        != blob(repo, head, ADOPTED_CONTINUATION_INHERITED_CONTRACT_PATH)
    ):
        raise ValueError("adopted continuation inherited T02 v1.2 contract differs from reviewed history")
    publication = inherited_contract["reference"]["approvalCommit"]
    before_state, before_errors = reference_state(repo, inherited_base, policy)
    published_state, published_errors = reference_state(repo, publication, policy)
    current_state, current_errors = reference_state(repo, head, policy)
    publication_errors = _reference_publication_content_errors(
        repo, inherited_packet, inherited_packet_commit, publication
    )
    if (
        before_errors
        or published_errors
        or current_errors
        or publication_errors
        or before_state.get("referenceId") != "RO-UI-ACADEMIC-MINIMAL-1.7"
        or published_state != current_state
        or published_state.get("referenceId") != ADOPTED_CONTINUATION_APPROVED_REFERENCE
        or published_state.get("version") != "1.8"
        or inherited_contract["reference"].get("packageSha256") != published_state.get("packageSha256")
        or inherited_contract["reference"].get("approvedBy") != published_state.get("approval", {}).get("approved_by")
        or not is_ancestor(repo, predecessor["reviewIntroduction"], inherited_base)
        or not is_ancestor(repo, inherited_approval, publication)
    ):
        raise ValueError("adopted continuation inherited 1.7-to-1.8 publication is not authentic")
    reference_paths = {
        path
        for path in changed_paths(repo, inherited_base, publication)
        if path.startswith(f"{policy['referenceRoot']}/")
    }
    historical = intentional_amendment_segments(
        repo,
        inherited_base,
        inherited_candidate,
        publication,
        ADOPTED_CONTINUATION_INHERITED_CONTRACT_PATH,
        reference_paths,
        policy,
    )
    if (
        historical["uiFiles"] != inherited_contract.get("changedFiles")
        or historical["referenceFiles"] != sorted(reference_paths)
        or not is_ancestor(repo, inherited_candidate, inherited_adoption)
    ):
        raise ValueError("adopted continuation inherited T02 renderer/reference segment differs")

    inherited_control_ranges, inherited_controls = adopted_continuation_reviewed_task_commits(
        repo, head, backlog_task(backlog, "W2.A01.T01") or {}
    )
    if (
        not inherited_control_ranges
        or inherited_control_ranges[-1]["candidate"] != ADOPTED_CONTINUATION_A01_CONTROL_CANDIDATE
    ):
        raise ValueError("adopted continuation inherited A01 control candidate differs from approved history")
    _, continuation_controls = adopted_continuation_reviewed_task_commits(repo, head, control_task)
    reviewed_controls = {**inherited_controls, **continuation_controls}
    if set(inherited_controls) & set(continuation_controls):
        raise ValueError("adopted continuation control review ranges overlap")
    reviewed_controls.update(adopted_continuation_reviewed_maintenance(repo, head))
    reviewed_activation: dict[str, set[str]] = {}
    reviewed_activation_consumer: set[str] = set()
    reviewed_repair_predecessors: dict[str, set[str]] = {}
    witness_introduction = ""
    if activation is not None:
        reviewed_controls.update(reference_activation_historical_authority(repo, head, backlog))
        if repaired:
            reviewed_repair_predecessors = reference_activation_repair_preceding_sources(repo, head)
            if set(reviewed_controls) & set(reviewed_repair_predecessors):
                raise ValueError("activation repair predecessor control ranges overlap")
            reviewed_controls.update(reviewed_repair_predecessors)
        reviewed_activation, reviewed_activation_consumer, witness_introduction = reference_activation_reviewed_tasks(
            repo, head, activation
        )
        if set(reviewed_controls) & set(reviewed_activation):
            raise ValueError("reference activation reviewed control ranges overlap")
        reviewed_controls.update(reviewed_activation)
        if repaired:
            latest_exit = activation["completion"]["exit_review_control"]["attempts"][-1]["submission"][
                "candidate_commit"
            ]
            reference_activation_correction_slice_history(
                repo,
                head,
                activation["tasks"][0],
                str(activation["campaign"]["owner"]),
                latest_exit,
                amendment_id="W2.A03",
                tasks=activation["tasks"],
            )
            immutable_record(
                repo,
                head,
                "artifacts/evidence/W2.A03.S01.review-01.json",
                "75d03f4f1d72ee966e70bcbdf66a7afc9bcbdb9fa222533e02d7c52e3d9f76f3",
                evidence=True,
            )
            slice_rounds = [
                p
                for p in git(repo, "ls-tree", "-r", "--name-only", head, "--", "artifacts/evidence")
                .decode()
                .splitlines()
                if re.fullmatch(r"artifacts/evidence/W2\.A03\.S01\.review-[0-9]{2,}\.json", p)
            ]
            if len(slice_rounds) < 2:
                raise ValueError("activation repair parent lacks fresh review-02 finding replay")
            replay, _ = immutable_record(repo, head, sorted(slice_rounds)[-1], evidence=True)
            if not any(c.get("finding_id") == "W2.A03.S01-R01-F01" for c in replay.get("closures", [])):
                raise ValueError("activation repair parent did not explicitly close its retained S01 finding")
            reference_activation_correction_checkpoint_reviews(repo, head, activation, str(activation_adoption))
        from ui_conformance import presentation_compatibility_errors

        witness_errors = presentation_compatibility_errors(
            repo, ADOPTED_CONTINUATION_APPROVED_REFERENCE, published_state["packageSha256"]
        )
        if witness_errors:
            raise ValueError("reference activation witness is invalid: " + "; ".join(witness_errors))
    historical_planning_inputs = adopted_continuation_historical_planning_inputs(
        repo, head, inherited_approval, continuation_packet_commit
    )

    ordered_rows = (
        git(repo, "rev-list", "--reverse", "--topo-order", "--parents", f"{base}..{head}").decode().splitlines()
    )
    ordered: list[str] = []
    previous = base
    for row in ordered_rows:
        values = row.split()
        if len(values) != 2 or values[1] != previous:
            raise ValueError("adopted continuation full task-base history must remain linear")
        previous = values[0]
        ordered.append(previous)
    if not ordered or previous != head:
        raise ValueError("adopted continuation full task-base history is incomplete")
    positions = {commit: index for index, commit in enumerate([base, *ordered])}
    anchors = (
        (publication, inherited_adoption, adoption, activation_adoption, witness_introduction)
        if activated
        else (publication, inherited_adoption, adoption)
    )
    if any(anchor not in positions for anchor in anchors):
        raise ValueError("adopted continuation historical anchors are outside the original T01 range")
    import taskctl

    owner = str(task["owner"])
    branch = str(task["branch"])
    profile = str(next(item for item in backlog["waves"] if item["id"] == "W2")["campaign"]["profile"])
    platform = str(next(item for item in backlog["waves"] if item["id"] == "W2")["campaign"]["platform"])
    reactivations: list[str] = []
    resumes: list[str] = []
    epochs = (
        ((inherited_adoption, adoption), (adoption, activation_adoption), (activation_adoption, head))
        if activation_adoption is not None
        else ((inherited_adoption, adoption), (adoption, head))
    )
    for adopted, limit in epochs:
        resumed = None
        reopened = None
        for commit in ordered[positions[adopted] : positions[limit]]:
            if "planning/backlog.yaml" not in commit_paths(repo, commit):
                continue
            parent = resolve_commit(repo, f"{commit}^")
            previous_state = adopted_continuation_projection_at(repo, parent)
            state = adopted_continuation_projection_at(repo, commit)
            prior_wave = next(item for item in previous_state["waves"] if item["id"] == "W2")
            active_wave = next(item for item in state["waves"] if item["id"] == "W2")
            prior_campaign = prior_wave.get("campaign") or {}
            campaign = active_wave.get("campaign") or {}
            if prior_campaign.get("status") == "PAUSED" and campaign.get("status") == "ACTIVE":
                prior_records = prior_campaign.get("resume_records") or []
                records = campaign.get("resume_records") or []
                record = records[-1] if records else {}
                if (
                    resumed is not None
                    or len(records) != len(prior_records) + 1
                    or records[:-1] != prior_records
                    or record.get("pre_resume_commit") != parent
                    or taskctl.wave_resume_record_errors(state, "W2", campaign, repo)
                    or campaign.get("base_sha") != parent
                    or campaign.get("owner") != owner
                    or campaign.get("branch") != branch
                    or campaign.get("worktree") != "."
                    or campaign.get("profile") != profile
                    or campaign.get("platform") != platform
                    or campaign.get("scope") != "wave"
                ):
                    raise ValueError("adopted continuation W2 PAUSED-to-ACTIVE resume record is invalid")
                resumed = commit
            prior_task = previous_state["task"]
            active_task = state["task"]
            if prior_task.get("status") not in {"IN_PROGRESS", "REVIEW"} and active_task.get("status") in {
                "IN_PROGRESS",
                "REVIEW",
            }:
                if (
                    resumed is None
                    or resumed == commit
                    or not adopted_continuation_active_at(repo, commit, base, owner, branch, profile, platform)
                    or active_task.get("base_sha") != base
                ):
                    raise ValueError("adopted continuation reopened T01 without authenticated W2 resume")
                reopened = commit
                break
        if resumed is None or reopened is None:
            raise ValueError("adopted continuation lacks an authenticated W2 resume and T01 reactivation")
        resumes.append(resumed)
        reactivations.append(reopened)
    if authority.get("reactivationCommit") != reactivations[1] or not (
        positions[inherited_adoption] < positions[reactivations[0]] < positions[adoption] < positions[reactivations[1]]
    ):
        raise ValueError("adopted continuation T01 reactivation anchors are stale or out of order")
    if activated:
        if not isinstance(activation_adoption, str) or not isinstance(activation_authority, dict):
            raise ValueError("reference activation is missing its adopted authority")
        if (
            activation_authority.get("reactivationCommit") != reactivations[2]
            or not positions[reactivations[1]] < positions[activation_adoption] < positions[reactivations[2]]
        ):
            raise ValueError("reference activation requires its separate post-A03 W2/T01 reactivation")
        reference_activation_source_history(
            repo,
            ordered,
            positions,
            activation_adoption,
            reactivations[2],
            reviewed_activation,
            (base, owner, branch, profile, platform),
        )

    reference_root = f"{policy['referenceRoot']}/"
    contract_root = f"{policy['contractRoot']}/"
    control_paths = (
        MAINTENANCE_CONTROL_PATHS
        | ADOPTED_CONTINUATION_AUTHORITY_INPUTS
        | ADOPTED_CONTINUATION_PLANNING_TOOLS
        | frozenset(
            {
                "docs/adr/index.json",
                "docs/adr/ADR-0035-admit-exact-intentional-amendment-ui-lineage.md",
                "docs/adr/ADR-0036-verify-exact-amendment-reference-approval-metadata.md",
                "docs/adr/ADR-0037-authenticate-adopted-attachment-ui-continuation.md",
                "docs/adr/ADR-0039-bind-approved-desktop-reference-activation.md",
                REFERENCE_ACTIVATION_CORRECTION_ADR,
                REFERENCE_ACTIVATION_REPAIR_ADR,
            }
        )
    )
    inherited_commits = set(historical["uiCommits"])
    touched_ui: set[str] = set()
    resumed_ui: set[str] = set()
    resumed_commits: list[str] = []
    product_paths: set[str] = set()
    t01_contract_touches: list[str] = []
    classification_ref = authority.get("classification") or {}
    _, classification_intro = immutable_record(repo, head, classification_ref["path"], classification_ref["sha256"])
    for commit in ordered:
        parent = resolve_commit(repo, f"{commit}^")
        paths = commit_paths(repo, commit)
        if "planning/backlog.yaml" in paths:
            prior_state = adopted_continuation_projection_at(repo, parent)
            current_state = adopted_continuation_projection_at(repo, commit)
            prior_wave = next(item for item in prior_state["waves"] if item["id"] == "W2")
            current_wave = next(item for item in current_state["waves"] if item["id"] == "W2")
            prior_task = prior_state["task"]
            current_task = current_state["task"]
            if (
                (prior_wave.get("campaign") or {}).get("status") == "PAUSED"
                and (current_wave.get("campaign") or {}).get("status") == "ACTIVE"
                and commit not in resumes
            ):
                raise ValueError("adopted continuation has an unbound W2 campaign resume")
            if (
                prior_task.get("status") not in {"IN_PROGRESS", "REVIEW"}
                and current_task.get("status") in {"IN_PROGRESS", "REVIEW"}
                and commit not in {ordered[0], *reactivations}
            ):
                raise ValueError("adopted continuation has an unbound original T01 reactivation")
        ui_paths = {path for path in paths if is_implementation_path(path, policy)}
        reference_delta = {path for path in paths if path.startswith(reference_root)}
        control_delta = paths & control_paths
        contract_delta = {path for path in paths if path.startswith(contract_root)}
        product_delta = {
            path
            for path in paths
            if path.startswith(ADOPTED_CONTINUATION_PRODUCT_ROOTS)
            or path in ADOPTED_CONTINUATION_PRODUCT_TOOLS
            or path == "Cargo.lock"
        }
        if contract_delta - {
            ADOPTED_CONTINUATION_INHERITED_CONTRACT_PATH,
            ADOPTED_CONTINUATION_CONTRACT_PATH,
        }:
            raise ValueError("adopted continuation has an extra or reverted UI contract")
        if reference_delta and (commit != publication or ui_paths or "planning/backlog.yaml" in paths):
            raise ValueError("adopted continuation reference changed outside separate approved publication")
        if "planning/backlog.yaml" in paths and ui_paths:
            raise ValueError("adopted continuation backlog transition mixed with governed renderer")
        imported_delta = paths & ADOPTED_CONTINUATION_AUTHORITY_INPUTS
        if imported_delta:
            if (
                commit in reviewed_repair_predecessors
                and paths == reviewed_repair_predecessors[commit]
                and not ui_paths
                and not reference_delta
            ):
                pass  # Exact owner-approved GOV27/B00 imported-source segment, authenticated above.
            elif commit == ADOPTED_CONTINUATION_TASKCTL_PREDECESSOR:
                if (
                    paths != {"tools/taskctl.py", "tests/foundation/test_taskctl_workflow.py"}
                    or len(git(repo, "rev-list", "--parents", "-n", "1", commit).decode().split()) != 2
                    or git(repo, "rev-parse", f"{commit}^{{tree}}").decode().strip()
                    != ADOPTED_CONTINUATION_TASKCTL_TREE
                    or not is_ancestor(repo, commit, "468cb390")
                    or not is_ancestor(repo, commit, continuation_packet_commit)
                ):
                    raise ValueError("adopted continuation inherited taskctl predecessor is not packet-bound")
            elif imported_delta == {"tools/adr_check.py"} and commit in inherited_controls:
                if commit not in {
                    "3658da21dfdb2d10765a0578d6629beedc1cae17",
                    "0948d63449cd7e1efdffe4eec7751d5dfd775146",
                }:
                    raise ValueError("adopted continuation ADR checker changed outside reviewed A01 source")
            else:
                raise ValueError("adopted continuation imported authority code changed without exact approval")
        if control_delta:
            if commit in historical_planning_inputs:
                pass  # Exact reviewed/packet-bound historical planning-site source only.
            elif commit == ADOPTED_CONTINUATION_TASKCTL_PREDECESSOR:
                pass  # Exact packet-bound inherited source, independently covered in A02.T01 review.
            elif commit == ADOPTED_CONTINUATION_MIXED_COMMIT:
                errors = adopted_continuation_quality_scope_errors(repo, commit, policy)
                if errors:
                    raise ValueError("; ".join(errors))
            elif commit == ADOPTED_CONTINUATION_QUALITY_CANDIDATE:
                errors = reviewed_preimplementation_maintenance_errors(repo, commit, head, paths, [])
                if errors:
                    raise ValueError("; ".join(errors))
            elif (
                activated
                and control_delta == {"tests/desktop/test_ui_conformance.py"}
                and positions[commit] > positions[reactivations[2]]
                and all(
                    adopted_continuation_active_at(repo, at, base, owner, branch, profile, platform)
                    for at in (parent, commit)
                )
            ):
                pass  # Shared T02 test also belongs to original T01 dependent-input classification.
            elif commit not in reviewed_controls or paths != reviewed_controls[commit] or ui_paths or reference_delta:
                raise ValueError("adopted continuation has unreviewed or mixed gate-control history")
        for path in contract_delta:
            if tree_entry(repo, commit, path) != ("100644", "blob"):
                raise ValueError("adopted continuation UI contract has non-regular history: " + path)
            if path == ADOPTED_CONTINUATION_INHERITED_CONTRACT_PATH:
                if commit not in inherited_source:
                    raise ValueError("adopted continuation inherited contract changed outside reviewed T02 source")
            elif path == ADOPTED_CONTINUATION_CONTRACT_PATH:
                if (
                    not all(
                        adopted_continuation_active_at(repo, at, base, owner, branch, profile, platform)
                        for at in (parent, commit)
                    )
                    or tree_entry(repo, parent, path) is not None
                ):
                    raise ValueError("adopted continuation T01 contract lacks a single active-claim introduction")
                t01_contract_touches.append(commit)
        if ui_paths:
            if implementation_object_errors(repo, parent, commit, sorted(ui_paths)):
                raise ValueError("adopted continuation has redirected governed renderer history")
            if commit in inherited_commits:
                if positions[commit] >= positions[inherited_adoption]:
                    raise ValueError("adopted continuation inherited renderer crossed adoption boundary")
            else:
                if (
                    positions[commit] <= positions[reactivations[0]]
                    or commit in reviewed_controls
                    or not all(
                        adopted_continuation_active_at(repo, at, base, owner, branch, profile, platform)
                        for at in (parent, commit)
                    )
                ):
                    raise ValueError("adopted continuation T01 renderer lacks an active original claim")
                for path in ui_paths:
                    if tree_entry(repo, commit, path) not in {("100644", "blob"), ("100755", "blob")}:
                        raise ValueError("adopted continuation T01 renderer was deleted or redirected: " + path)
                resumed_ui.update(ui_paths)
                resumed_commits.append(commit)
            touched_ui.update(ui_paths)
        if (
            commit in reviewed_controls
            or commit in inherited_source
            or commit in historical_planning_inputs
            or commit
            in {
                ADOPTED_CONTINUATION_TASKCTL_PREDECESSOR,
                ADOPTED_CONTINUATION_QUALITY_CANDIDATE,
            }
        ):
            product_delta.clear()
        if product_delta:
            if not all(
                adopted_continuation_active_at(repo, at, base, owner, branch, profile, platform)
                for at in (parent, commit)
            ):
                raise ValueError("adopted continuation dependent product changed outside active original T01")
            for path in product_delta:
                if tree_entry(repo, commit, path) not in {("100644", "blob"), ("100755", "blob")}:
                    raise ValueError("adopted continuation dependent product has non-regular history: " + path)
                predecessor_entry = tree_entry(repo, parent, path)
                if predecessor_entry is not None and predecessor_entry not in {
                    ("100644", "blob"),
                    ("100755", "blob"),
                }:
                    raise ValueError("adopted continuation dependent product redirected in history: " + path)
            product_paths.update(product_delta)
    if len(t01_contract_touches) != 1 or positions[t01_contract_touches[0]] <= positions[classification_intro]:
        raise ValueError("adopted continuation T01 contract changed without fresh independent classification")
    if (
        authority.get("inheritedUiFiles") != historical["uiFiles"]
        or authority.get("inheritedUiCommits") != historical["uiCommits"]
        or authority.get("resumedUiFiles") != sorted(resumed_ui)
        or authority.get("resumedUiCommits") != resumed_commits
        or touched_ui != {path for path in changed_paths(repo, base, head) if is_implementation_path(path, policy)}
        or not resumed_commits
        or set(historical["uiCommits"]) & set(resumed_commits)
    ):
        raise ValueError("adopted continuation UI path/commit attribution is incomplete or stale")
    if activated:
        if (
            not isinstance(activation, dict)
            or not isinstance(activation_authority, dict)
            or not isinstance(activation_adoption, str)
        ):
            raise ValueError("reference activation is missing its reviewed task/commit authority")
        consumer_base = next(
            item for item in activation["tasks"] if item["id"] == REFERENCE_ACTIVATION_CONSUMER_TASK_ID
        )["base_sha"]
        consumer_file_touches = [
            commit
            for commit in ordered
            if commit in reviewed_activation_consumer
            and commit_paths(repo, commit) & REFERENCE_ACTIVATION_CONSUMER_FILES
        ]
        consumer_files = {
            path for commit in consumer_file_touches for path in commit_paths(repo, commit)
        } & REFERENCE_ACTIVATION_CONSUMER_FILES
        baseline_touches = [
            commit
            for commit in consumer_file_touches
            if "verification/baselines/desktop-ui.json" in commit_paths(repo, commit)
        ]
        activation_input_touches = [
            commit
            for commit in consumer_file_touches
            if commit_paths(repo, commit)
            & (REFERENCE_ACTIVATION_CONSUMER_FILES - {"verification/baselines/desktop-ui.json"})
        ]
        later_unreviewed_consumer_touches = [
            commit
            for commit in ordered
            if positions[commit] > positions[consumer_base]
            and commit not in reviewed_activation_consumer
            and commit_paths(repo, commit) & REFERENCE_ACTIVATION_CONSUMER_FILES
        ]
        if (
            activation_authority.get("publicationCommit") != publication
            or activation_authority.get("witnessCommit") != witness_introduction
            or activation_authority.get("activationUiFiles") != sorted(REFERENCE_ACTIVATION_CONSUMER_FILES)
            or activation_authority.get("activationUiCommits") != consumer_file_touches
            or consumer_files != REFERENCE_ACTIVATION_CONSUMER_FILES
            or changed_paths(repo, consumer_base, head) & REFERENCE_ACTIVATION_CONSUMER_FILES
            != REFERENCE_ACTIVATION_CONSUMER_FILES
            or not consumer_file_touches
            or not baseline_touches
            or not activation_input_touches
            or max(positions[commit] for commit in activation_input_touches)
            >= min(positions[commit] for commit in baseline_touches)
            or positions[witness_introduction] >= positions[consumer_file_touches[0]]
            or positions[consumer_file_touches[-1]] >= positions[activation_adoption]
            or later_unreviewed_consumer_touches
        ):
            raise ValueError("reference activation reviewed consumer file/commit history is incomplete or stale")
        consumer_errors = reference_activation_consumer_errors(repo, head, consumer_base)
        if consumer_errors:
            raise ValueError("reference activation consumer contract is invalid: " + "; ".join(consumer_errors))
    return {
        "taskDefinitionSha256": task_digest,
        "adoptionCommit": adoption,
        "reactivationCommit": reactivations[1],
        "inheritedUiFiles": historical["uiFiles"],
        "inheritedUiCommits": historical["uiCommits"],
        "resumedUiFiles": sorted(resumed_ui),
        "resumedUiCommits": resumed_commits,
        "t01ProductPaths": sorted(product_paths),
        "publicationCommit": publication,
        "packetCommit": continuation_packet_commit,
        **(
            {
                "referenceActivationAdoptionCommit": activation_adoption,
                "referenceActivationWitnessCommit": witness_introduction,
                "referenceActivationUiFiles": sorted(REFERENCE_ACTIVATION_CONSUMER_FILES),
                "referenceActivationUiCommits": consumer_file_touches,
            }
            if activated
            else {}
        ),
    }


def adopted_continuation_classification_errors(
    repo: Path, base: str, head: str, contract: dict[str, Any], scope: dict[str, Any], policy: dict[str, Any]
) -> list[str]:
    """Reuse the locked capture reader, then bind omitted T01 product inputs."""

    reference = contract["adoptedContinuationAuthority"]["classification"]
    existing_contract = {**contract, "restorationClassification": reference}
    existing_scope = {**scope, "correctionProductPaths": scope["t01ProductPaths"]}
    errors = restoration_classification_errors(repo, base, head, existing_contract, existing_scope, policy)
    if errors:
        return errors
    record, _ = immutable_record(repo, head, reference["path"], reference["sha256"])
    candidate = str(record["candidateCommit"])
    manifest_ref = record["captures"]
    manifest, _ = immutable_record(repo, head, manifest_ref["path"], manifest_ref["sha256"])
    producer_blobs = (manifest.get("producer") or {}).get("inputGitBlobs") or {}
    if not isinstance(producer_blobs, dict):
        return ["adopted continuation capture producer lacks Git input inventory"]
    dependent = sorted(set(scope["t01ProductPaths"]) - set(producer_blobs))
    claimed = record.get("dependentInputFiles")
    bindings = record.get("dependentInputGitBlobs")
    if claimed != dependent or not isinstance(bindings, dict) or sorted(bindings) != dependent:
        return ["adopted continuation classification omits or adds dependent T01 product inputs"]
    for path in dependent:
        if (
            canonical_path(path) != path
            or tree_entry(repo, candidate, path) != ("100644", "blob")
            or tree_entry(repo, head, path) != ("100644", "blob")
        ):
            return ["adopted continuation dependent product input is absent or redirected: " + path]
        entry = git(repo, "rev-parse", f"{candidate}:{path}").decode().strip()
        if bindings.get(path) != entry or blob(repo, candidate, path) != blob(repo, head, path):
            return ["adopted continuation dependent product input changed after classification: " + path]
    inputs = set(dependent) | set(producer_blobs)
    for commit in git(repo, "rev-list", f"{candidate}..{head}").decode().splitlines():
        if commit_paths(repo, commit) & inputs:
            return ["adopted continuation classification is stale after a dependent input touch"]
    return []


def validate_adopted_continuation(
    repo: Path,
    base: str,
    head: str,
    changed: set[str],
    ui_files: list[str],
    contract_paths: list[str],
    schema: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    """Check the sole approved two-contract exception over T01's whole base."""

    errors: list[str] = []
    report: dict[str, Any] = {
        "ok": False,
        "base": base,
        "head": head,
        "uiFiles": ui_files,
        "contract": ADOPTED_CONTINUATION_CONTRACT_PATH,
        "changeKind": "defect-restoration",
        "referenceId": None,
        "referencePackageSha256": None,
        "errors": errors,
    }
    if contract_paths != sorted([ADOPTED_CONTINUATION_CONTRACT_PATH, ADOPTED_CONTINUATION_INHERITED_CONTRACT_PATH]):
        errors.append("adopted continuation requires exactly inherited T02 and current T01 UI contracts")
        return report
    try:
        if tree_entry(repo, head, ADOPTED_CONTINUATION_CONTRACT_PATH) != ("100644", "blob"):
            errors.append("adopted continuation current T01 contract is not a regular 100644 Git blob")
            return report
        contract = json_object(blob(repo, head, ADOPTED_CONTINUATION_CONTRACT_PATH), "adopted continuation contract")
        for issue in sorted(
            Draft202012Validator(schema).iter_errors(contract), key=lambda item: list(item.absolute_path)
        ):
            location = ".".join(str(part) for part in issue.absolute_path) or "<root>"
            errors.append(f"{ADOPTED_CONTINUATION_CONTRACT_PATH}:{location}: {issue.message}")
        if errors:
            return report
        if contract.get("changedFiles") != ui_files:
            errors.append("adopted continuation changedFiles omit the original-base governed UI inventory")
        errors.extend(implementation_object_errors(repo, base, head, ui_files))
        state, state_errors = reference_state(repo, head, policy)
        errors.extend(state_errors)
        reference = contract["reference"]
        expected = {
            "referenceId": state.get("referenceId"),
            "version": state.get("version"),
            "packageSha256": state.get("packageSha256"),
            "approvalCommit": "acdc67b616f5ecdec448f57a7efe46e4f359aa9f",
            "approvedBy": state.get("approval", {}).get("approved_by"),
            "previousReferenceId": "RO-UI-ACADEMIC-MINIMAL-1.7",
        }
        if any(reference.get(key) != value for key, value in expected.items()):
            errors.append("adopted continuation contract reference differs from the exact approved 1.8 package")
        report["referenceId"] = state.get("referenceId")
        report["referencePackageSha256"] = state.get("packageSha256")
        if errors:
            return report
        scope = adopted_continuation_authority(repo, base, head, contract, policy)
        report["rangeAuthority"] = scope
        if scope["publicationCommit"] != reference["approvalCommit"]:
            errors.append("adopted continuation cited a different historical 1.8 publication")
        if not errors:
            errors.extend(adopted_continuation_classification_errors(repo, base, head, contract, scope, policy))
    except (
        KeyError,
        IndexError,
        StopIteration,
        TypeError,
        ValueError,
        UnicodeError,
        OSError,
        subprocess.TimeoutExpired,
        yaml.YAMLError,
    ) as exc:
        errors.append(f"invalid adopted continuation UI authority: {exc}")
    report["ok"] = not errors
    return report


def validate(repo: Path, base_ref: str, head_ref: str = "HEAD") -> dict[str, Any]:
    errors: list[str] = []
    try:
        repo = repo.resolve(strict=True)
        base = resolve_commit(repo, base_ref)
        head = resolve_commit(repo, head_ref)
        if base == head or not is_ancestor(repo, base, head):
            raise ValueError("UI change base must be a strict ancestor of head")
        policy = json_object(blob(repo, head, "ui-change-policy.json"), "ui-change-policy.json")
        require_canonical_policy(policy)
        schema_path = str(policy.get("contractSchemaPath", ""))
        schema = json_object(blob(repo, head, schema_path), schema_path)
        changed = changed_paths(repo, base, head)
        try:
            base_policy = json_object(blob(repo, base, "ui-change-policy.json"), "base ui-change-policy.json")
            require_canonical_policy(base_policy)
        except UnicodeDecodeError, ValueError, json.JSONDecodeError:
            if "ui-change-policy.json" not in changed:
                raise
            base_policy = policy
        ui_files = sorted(
            path
            for path in changed
            if is_implementation_path(path, policy) or is_implementation_path(path, base_policy)
        )
        contract_root = str(policy.get("contractRoot", ""))
        contract_paths = sorted(
            path for path in changed if path.startswith(f"{contract_root}/") and path.endswith(".json")
        )
    except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        return {"ok": False, "base": base_ref, "head": head_ref, "errors": [str(exc)]}

    report: dict[str, Any] = {
        "ok": False,
        "base": base,
        "head": head,
        "uiFiles": ui_files,
        "contract": contract_paths[0] if len(contract_paths) == 1 else None,
        "changeKind": None,
        "referenceId": None,
        "referencePackageSha256": None,
        "errors": errors,
    }
    if not ui_files:
        # Authenticate a live linked range even on an evidence-only head. An
        # explicit short base or a reverted net diff cannot erase its authority.
        try:
            no_ui_backlog = (
                yaml_object(blob(repo, head, "planning/backlog.yaml"), "planning/backlog.yaml")
                if tree_entry(repo, head, "planning/backlog.yaml") is not None
                else {}
            )
            linked_active = [
                task
                for task in authenticated_active_corrections(repo, head, no_ui_backlog)
                if corrective_ui_paths(task)
            ]
            if len(linked_active) > 1:
                raise ValueError("ambiguous active linked UI corrections")
            if linked_active:
                linked_correction_authority(repo, base, head, no_ui_backlog, linked_active[0])
                errors.extend(corrective_scope_errors(repo, linked_active[0], head))
                errors.extend(linked_correction_range_errors(repo, base, head, linked_active[0], policy))
                if implementation_commits(repo, base, head, policy):
                    errors.append("linked correction has reverted UI history but no net governed implementation change")
            intentional = backlog_task(no_ui_backlog, INTENTIONAL_AMENDMENT_TASK_ID)
            if intentional is not None and intentional.get("status") in {"IN_PROGRESS", "REVIEW"}:
                if intentional.get("amendment_id") != INTENTIONAL_AMENDMENT_ID or intentional.get("base_sha") != base:
                    raise ValueError("intentional amendment task has a stale or foreign base")
                if implementation_commits(repo, base, head, policy):
                    errors.append("intentional amendment has reverted renderer history but no net governed change")
            continuation = backlog_task(no_ui_backlog, ADOPTED_CONTINUATION_TASK_ID)
            if continuation is not None and continuation.get("status") in {"IN_PROGRESS", "REVIEW"}:
                if automatic_base(repo, head) != base:
                    raise ValueError("active adopted continuation cannot shorten its original 6506 task base")
                if implementation_commits(repo, base, head, policy):
                    errors.append("adopted continuation has reverted UI history without its exact two contracts")
                else:
                    errors.append("active adopted continuation T01 requires its full-range UI authority contract")
        except (KeyError, StopIteration, TypeError, UnicodeError, ValueError, yaml.YAMLError) as exc:
            errors.append(str(exc))
        if contract_paths:
            errors.append("UI change evidence is present but no governed UI implementation file changed")
        report["ok"] = not errors
        return report
    if ADOPTED_CONTINUATION_CONTRACT_PATH in contract_paths:
        return validate_adopted_continuation(repo, base, head, changed, ui_files, contract_paths, schema, policy)
    if len(contract_paths) != 1:
        errors.append(f"exactly one changed UI evidence contract is required; found {contract_paths}")
        return report
    try:
        errors.extend(implementation_object_errors(repo, base, head, ui_files))
        # A later revert cannot erase an intermediate control-authority change.
        # Control-maintenance authority remains required for actual UI work;
        # the linked no-UI range is authenticated separately above.
        protected_touches: set[str] = set()
        for commit in git(repo, "rev-list", f"{base}..{head}").decode("ascii").splitlines():
            protected_touches.update(commit_paths(repo, commit) & GATE_CONTROL_PATHS)
        protected_changes = sorted(protected_touches)
    except ValueError as exc:
        errors.append(str(exc))
        return report

    contract_path = contract_paths[0]
    try:
        contract = json_object(blob(repo, head, contract_path), contract_path)
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(str(exc))
        return report
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    for issue in sorted(validator.iter_errors(contract), key=lambda item: list(item.absolute_path)):
        location = ".".join(str(part) for part in issue.absolute_path) or "<root>"
        errors.append(f"{contract_path}:{location}: {issue.message}")
    if errors:
        return report

    resumed_scope: dict[str, Any] | None = None
    intentional_scope: dict[str, Any] | None = None
    linked_origin: dict[str, Any] | None = None
    if "intentionalAmendmentAuthority" in contract:
        try:
            intentional_scope = intentional_amendment_authority(repo, base, head, contract, policy)
            report["rangeAuthority"] = intentional_scope
        except (KeyError, TypeError, ValueError, UnicodeError, yaml.YAMLError) as exc:
            errors.append(f"invalid intentional amendment UI authority: {exc}")
            return report
    if "amendmentAuthority" in contract:
        try:
            resumed_scope = resumed_amendment_authority(repo, base, head, contract, policy)
            report["rangeAuthority"] = resumed_scope
        except (KeyError, TypeError, ValueError, UnicodeError, yaml.YAMLError) as exc:
            errors.append(f"invalid resumed amendment UI authority: {exc}")
            return report
    if LINKED_CORRECTION_ID.fullmatch(str(contract.get("taskId"))):
        try:
            backlog = yaml_object(blob(repo, head, "planning/backlog.yaml"), "planning/backlog.yaml")
            linked_task = find_task(backlog, str(contract["taskId"]))
            if (
                linked_task is None
                or contract["schemaVersion"] != "1.0"
                or contract["changeKind"] != "defect-restoration"
            ):
                raise ValueError("control maintenance requires an admitted v1.0 linked restoration")
            linked_origin = linked_correction_authority(repo, base, head, backlog, linked_task)
            errors.extend(corrective_scope_errors(repo, linked_task, head))
        except (KeyError, TypeError, ValueError, UnicodeError, yaml.YAMLError) as exc:
            errors.append(f"invalid linked correction control maintenance: {exc}")
        if errors:
            return report
    elif protected_changes:
        errors.extend(
            application_activation_errors(
                repo, base, head, protected_changes, contract, policy, resumed_scope=resumed_scope
            )
        )
        if errors:
            return report

    task_id = str(contract["taskId"])
    expected_contract_path = f"{contract_root}/{task_id}.json"
    if contract_path != expected_contract_path or contract.get("contractPath") != contract_path:
        errors.append(f"UI evidence path must be {expected_contract_path}")
    if contract.get("changedFiles") != ui_files:
        errors.append("UI evidence changedFiles must exactly equal the sorted governed implementation change set")

    state, state_errors = reference_state(repo, head, policy)
    base_state, base_state_errors = reference_state(repo, base, policy)
    errors.extend(state_errors)
    errors.extend(f"base: {error}" for error in base_state_errors)
    reference = contract["reference"]
    report["changeKind"] = contract["changeKind"]
    report["referenceId"] = state.get("referenceId")
    report["referencePackageSha256"] = state.get("packageSha256")
    expected_reference = {
        "referenceId": state.get("referenceId"),
        "version": state.get("version"),
        "packageSha256": state.get("packageSha256"),
        "approvedBy": state.get("approval", {}).get("approved_by"),
        "previousReferenceId": state.get("approval", {}).get("supersedes"),
    }
    for key, expected in expected_reference.items():
        if reference.get(key) != expected:
            errors.append(f"UI evidence reference.{key} does not match the exact approved reference")

    try:
        approval_commit = resolve_commit(repo, str(reference["approvalCommit"]))
        if approval_commit != reference["approvalCommit"]:
            errors.append("reference.approvalCommit must be a full canonical commit SHA")
        if not is_ancestor(repo, approval_commit, head):
            errors.append("reference approval commit is not an ancestor of head")
        if str(policy["approvalPath"]) not in commit_paths(repo, approval_commit):
            errors.append("reference approval commit did not change the approval record")
        approval_payload = blob(repo, approval_commit, str(policy["approvalPath"]))
        if approval_payload != state.get("approvalPayload"):
            errors.append("reference approval record changed after the cited approval commit")
    except (KeyError, ValueError) as exc:
        errors.append(f"invalid reference approval commit: {exc}")
        approval_commit = ""

    try:
        backlog = yaml_object(blob(repo, head, "planning/backlog.yaml"), "planning/backlog.yaml")
        task = find_task(backlog, task_id)
    except (UnicodeDecodeError, ValueError, yaml.YAMLError) as exc:
        errors.append(str(exc))
        task = None
    if task is None:
        errors.append(f"UI evidence task does not exist in the authoritative backlog: {task_id}")
    else:
        if task.get("correction") is not None or LINKED_CORRECTION_ID.fullmatch(task_id):
            try:
                if contract["schemaVersion"] != "1.0" or contract["changeKind"] != "defect-restoration":
                    raise ValueError("linked UI correction requires the existing v1.0 defect-restoration contract")
                if linked_origin is None:
                    linked_origin = linked_correction_authority(repo, base, head, backlog, task)
                errors.extend(linked_correction_range_errors(repo, base, head, task, policy))
            except (KeyError, TypeError, ValueError, UnicodeError, yaml.YAMLError) as exc:
                errors.append(f"invalid linked correction UI authority: {exc}")
                return report
        experience = task.get("experience_change")
        expected_experience = {
            "kind": contract["changeKind"],
            "contract_path": contract_path,
            "reference_id": reference["referenceId"],
            "reference_version": reference["version"],
            "reference_package_sha256": reference["packageSha256"],
            "reference_approval_commit": reference["approvalCommit"],
            "previous_reference_id": reference["previousReferenceId"],
            "implementation_agent": contract["implementationAgent"],
        }
        if (
            linked_origin is None
            and ("amendmentAuthority" not in contract or experience is not None)
            and intentional_scope is None
            and experience != expected_experience
        ):
            errors.append("task experience_change must exactly match the UI evidence lineage")
        if task.get("status") not in {"IN_PROGRESS", "REVIEW"}:
            errors.append("UI evidence task must be active in IN_PROGRESS or REVIEW state")
        if task.get("base_sha") != base:
            errors.append("UI evidence task base_sha must exactly equal the validated change base")
        implementation_identity = str(contract["implementationAgent"]).split(":", 1)[1]
        if task.get("owner") != implementation_identity:
            errors.append("UI evidence implementationAgent must identify the claimed task owner")

    reference_changed = sorted(path for path in changed if path.startswith(f"{policy['referenceRoot']}/"))
    kind = contract["changeKind"]
    if "amendmentAuthority" in contract:
        if task is not None and (
            task.get("branch") != git(repo, "branch", "--show-current").decode().strip()
            or (task.get("lease") or {}).get("claimed_by") != task.get("owner")
        ):
            errors.append("resumed UI task branch or lease owner differs from the current claim")
        if not errors:
            try:
                if resumed_scope is None:
                    raise ValueError("resumed control authority was not authenticated")
                errors.extend(restoration_classification_errors(repo, base, head, contract, resumed_scope, policy))
            except (KeyError, TypeError, ValueError, UnicodeError, yaml.YAMLError) as exc:
                errors.append(f"invalid resumed amendment UI authority: {exc}")
    elif kind == "intentional-design-change":
        approval = state.get("approval", {})
        if base_state.get("referenceId") == state.get("referenceId"):
            errors.append("intentional UI change requires a newer approved reference than the base commit")
        if reference.get("previousReferenceId") != base_state.get("referenceId"):
            errors.append("intentional UI change previousReferenceId must equal the base reference ID")
        approved_by = approval.get("approved_by")
        if (
            approval.get("approval_kind") != "human"
            or not isinstance(approved_by, str)
            or not HUMAN_ID.fullmatch(approved_by)
        ):
            errors.append("intentional UI reference approval must be an explicit human:<identity> approval")
        implementation_identity = str(contract.get("implementationAgent", "")).split(":", 1)[-1].casefold()
        approval_identity = str(approved_by).split(":", 1)[-1].casefold()
        if approved_by == contract.get("implementationAgent") or approval_identity == implementation_identity:
            errors.append("the implementation agent cannot approve its own UI reference revision")
        if task is not None and intentional_scope is None and task.get("review_gate") != "human-and-agent-review":
            errors.append("intentional UI implementation tasks require human-and-agent-review")
        if not reference_changed:
            errors.append("intentional UI change requires a governed reference revision in the change range")
        if approval_commit:
            if approval_commit == base or not is_ancestor(repo, base, approval_commit):
                errors.append("reference approval commit must occur after the pull-request base")
            approval_state, approval_errors = reference_state(repo, approval_commit, policy)
            errors.extend(f"approval commit: {error}" for error in approval_errors)
            if approval_state.get("packageSha256") != state.get("packageSha256"):
                errors.append("approved reference package changed after the approval commit")
            try:
                commits = implementation_commits(repo, base, head, policy)
            except ValueError as exc:
                errors.append(str(exc))
                commits = []
            for commit in commits:
                if commit == approval_commit or not is_ancestor(repo, approval_commit, commit):
                    errors.append(f"reference approval must strictly precede UI implementation commit {commit}")
    else:
        if base_state.get("referenceId") != state.get("referenceId") or base_state.get("packageSha256") != state.get(
            "packageSha256"
        ):
            errors.append(f"{kind} must use the unchanged approved reference from the base commit")
        if reference_changed:
            errors.append(f"{kind} cannot modify the governed UI reference")
        if (
            linked_origin is not None
            and task is not None
            and (
                "restorationClassification" in contract
                or (
                    linked_origin.get("review_gate") == "agent-review"
                    and task["correction"].get("origin_amendment_id") is None
                )
            )
        ):
            try:
                errors.extend(linked_conformance_classification_errors(repo, base, head, contract, task, policy))
            except (KeyError, TypeError, ValueError, UnicodeError, yaml.YAMLError) as exc:
                errors.append(f"invalid linked conformance classification: {exc}")
        review_task = linked_origin if linked_origin is not None else task
        if (
            kind == "defect-restoration"
            and linked_origin is None
            and review_task is not None
            and review_task.get("review_gate") != "human-and-agent-review"
        ):
            errors.append(
                "defect restoration requires human-and-agent-review to classify the change until governed "
                "implementation-conformance evidence is installed"
            )

    report["ok"] = not errors
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--base", default=os.environ.get("UI_CHANGE_BASE_SHA"))
    parser.add_argument("--head", default="HEAD")
    args = parser.parse_args()
    repo = args.repo.resolve()
    try:
        base = args.base or automatic_base(repo, args.head)
        result = validate(repo, base, args.head)
    except ValueError as exc:
        result = {"ok": False, "base": args.base, "head": args.head, "errors": [str(exc)]}
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
