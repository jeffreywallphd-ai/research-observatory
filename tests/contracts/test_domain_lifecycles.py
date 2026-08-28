from __future__ import annotations

import hashlib
import json
import sys
import unittest
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any, cast

from jsonschema import Draft202012Validator

REPO = Path(__file__).resolve().parents[2]
SERVICE_SRC = REPO / "services" / "core-api" / "src"
if str(SERVICE_SRC) not in sys.path:
    sys.path.insert(0, str(SERVICE_SRC))

from research_observatory_core.domain_lifecycles import (  # noqa: E402
    DOMAIN_LIFECYCLE_PROFILE_SHA256,
    DOMAIN_LIFECYCLE_SCHEMA_SHA256,
    DomainLifecycleProblem,
    apply_lifecycle_transition,
    domain_lifecycle_profile,
    lifecycle_transition_errors,
    lifecycle_transition_json,
    prepare_lifecycle_transition,
)

AGGREGATE_ID = "018f47a2-4d6b-7f78-9f2e-7fb76c86d9a1"
OTHER_AGGREGATE_ID = "018f47a2-4d6b-7f78-9f2e-7fb76c86d9a2"
EXPECTED_KINDS = (
    "project",
    "corpus-item",
    "document",
    "evidence-record",
    "decision",
    "task",
    "dossier",
    "export",
)


def snapshot(kind: str, state: str, revision: int = 0) -> dict[str, object]:
    return {
        "schemaVersion": "1.0",
        "documentType": "research-observatory-domain-lifecycle-snapshot",
        "profileVersion": "1.0.0",
        "subjectKind": kind,
        "aggregateId": AGGREGATE_ID,
        "state": state,
        "revision": revision,
    }


def command(kind: str, name: str, revision: int = 0) -> dict[str, object]:
    return {
        "schemaVersion": "1.0",
        "documentType": "research-observatory-domain-lifecycle-command",
        "profileVersion": "1.0.0",
        "subjectKind": kind,
        "aggregateId": AGGREGATE_ID,
        "expectedRevision": revision,
        "command": name,
        "actor": {"kind": "human", "id": "researcher:local-owner"},
        "reason": {"code": "researcher-judgment", "detail": "Researcher recorded the bounded lifecycle decision."},
        "occurredAt": "2026-08-28T13:45:00.000Z",
        "idempotencyKey": f"{kind}.{name}.{revision}",
    }


class RecordingRepository:
    def __init__(self) -> None:
        self.writes: list[MappingProxyType[str, object] | Any] = []

    def apply(self, current: object, requested: object) -> object:
        return apply_lifecycle_transition(current, requested, self.writes.append)


class DomainLifecycleContractTests(unittest.TestCase):
    profile_root = REPO / "packages" / "contracts" / "domain"

    def test_exact_profile_is_schema_valid_hash_bound_and_semantically_deterministic(self) -> None:
        schema_bytes = (self.profile_root / "domain-lifecycle.schema.json").read_bytes()
        profile_bytes = (self.profile_root / "domain-lifecycle.v1.json").read_bytes()
        schema = json.loads(schema_bytes)
        profile = json.loads(profile_bytes)
        Draft202012Validator.check_schema(schema)
        self.assertEqual([], list(Draft202012Validator(schema).iter_errors(profile)))
        self.assertEqual(hashlib.sha256(schema_bytes).hexdigest(), DOMAIN_LIFECYCLE_SCHEMA_SHA256)
        self.assertEqual(hashlib.sha256(profile_bytes).hexdigest(), DOMAIN_LIFECYCLE_PROFILE_SHA256)
        self.assertEqual(EXPECTED_KINDS, tuple(subject["subjectKind"] for subject in profile["subjects"]))
        wire_validator = lambda definition: Draft202012Validator(  # noqa: E731
            {
                "$schema": schema["$schema"],
                "$defs": schema["$defs"],
                "$ref": f"#/$defs/{definition}",
            }
        )
        self.assertEqual([], list(wire_validator("LifecycleSnapshot").iter_errors(snapshot("task", "ready", 3))))
        requested = command("task", "start", 3)
        self.assertEqual([], list(wire_validator("LifecycleCommand").iter_errors(requested)))
        emitted = json.loads(
            lifecycle_transition_json(prepare_lifecycle_transition(snapshot("task", "ready", 3), requested))
        )
        self.assertEqual([], list(wire_validator("LifecycleTransition").iter_errors(emitted)))

        for subject in profile["subjects"]:
            states = {state["id"]: state for state in subject["states"]}
            self.assertEqual(len(states), len(subject["states"]))
            self.assertIn(subject["initialState"], states)
            self.assertFalse(states[subject["initialState"]]["terminal"])
            self.assertTrue(any(state["terminal"] for state in states.values()))
            selectors: set[tuple[str, str]] = set()
            for rule in subject["transitions"]:
                self.assertIn(rule["from"], states)
                self.assertIn(rule["to"], states)
                self.assertNotEqual(rule["from"], rule["to"])
                selector = (rule["from"], rule["command"])
                self.assertNotIn(selector, selectors)
                selectors.add(selector)
                if states[rule["from"]]["terminal"]:
                    self.assertEqual("reopen", rule["kind"])

    def test_every_declared_transition_is_deterministic_and_retains_actor_and_reason(self) -> None:
        subjects = cast(tuple[Mapping[str, object], ...], domain_lifecycle_profile()["subjects"])
        for subject in subjects:
            transitions = cast(tuple[Mapping[str, object], ...], subject["transitions"])
            for rule in transitions:
                current = snapshot(str(subject["subjectKind"]), str(rule["from"]), 7)
                requested = command(str(subject["subjectKind"]), str(rule["command"]), 7)
                first = prepare_lifecycle_transition(current, requested)
                second = prepare_lifecycle_transition(current, requested)
                self.assertEqual(lifecycle_transition_json(first), lifecycle_transition_json(second))
                self.assertEqual(rule["to"], first["toState"])
                self.assertEqual(rule["kind"], first["transitionKind"])
                self.assertEqual(7, first["priorRevision"])
                self.assertEqual(8, first["revision"])
                self.assertEqual(requested["actor"], first["actor"])
                self.assertEqual(requested["reason"], first["reason"])

    def test_illegal_transition_and_revision_conflict_fail_before_persistence(self) -> None:
        repository = RecordingRepository()
        with self.assertRaises(DomainLifecycleProblem) as denied:
            repository.apply(snapshot("project", "active"), command("project", "publish"))
        self.assertEqual("lifecycle-command-not-allowed", denied.exception.code)
        self.assertEqual([], repository.writes)

        stale = command("task", "start", 4)
        self.assertEqual(
            ("lifecycle-revision-conflict",),
            lifecycle_transition_errors(snapshot("task", "ready", 5), stale),
        )
        with self.assertRaises(DomainLifecycleProblem):
            repository.apply(snapshot("task", "ready", 5), stale)
        self.assertEqual([], repository.writes)

    def test_terminal_and_reopen_rules_are_explicit(self) -> None:
        completed = snapshot("task", "completed", 2)
        self.assertEqual(
            ("lifecycle-command-not-allowed",),
            lifecycle_transition_errors(completed, command("task", "start", 2)),
        )
        reopened = prepare_lifecycle_transition(completed, command("task", "reopen", 2))
        self.assertEqual("ready", reopened["toState"])
        self.assertEqual("reopen", reopened["transitionKind"])

        deleted = snapshot("project", "deleted", 9)
        self.assertEqual(
            ("lifecycle-command-not-allowed",),
            lifecycle_transition_errors(deleted, command("project", "reopen", 9)),
        )

    def test_strict_untrusted_inputs_and_subject_mismatch_are_bounded(self) -> None:
        valid_current = snapshot("document", "registered")
        valid_command = command("document", "make-available")
        hostile_cases: list[tuple[object, object, tuple[str, ...]]] = []

        extra = dict(valid_command)
        extra["credential"] = "secret"
        hostile_cases.append((valid_current, extra, ("lifecycle-command-invalid",)))

        path_actor = json.loads(json.dumps(valid_command))
        cast(dict[str, object], path_actor["actor"])["id"] = "C:\\private\\researcher"
        hostile_cases.append((valid_current, path_actor, ("lifecycle-command-invalid",)))

        control_reason = json.loads(json.dumps(valid_command))
        cast(dict[str, object], control_reason["reason"])["detail"] = "unsafe\nreason"
        hostile_cases.append((valid_current, control_reason, ("lifecycle-command-invalid",)))

        wrong_subject = json.loads(json.dumps(valid_command))
        wrong_subject["aggregateId"] = OTHER_AGGREGATE_ID
        hostile_cases.append((valid_current, wrong_subject, ("lifecycle-subject-mismatch",)))

        unknown_state = snapshot("document", "invented")
        hostile_cases.append(
            (
                unknown_state,
                command("document", "make-available"),
                ("lifecycle-state-unknown", "lifecycle-command-not-allowed"),
            )
        )

        for current, requested, expected in hostile_cases:
            self.assertEqual(expected, lifecycle_transition_errors(current, requested))

    def test_transition_is_owned_frozen_and_restart_composes_from_its_exact_revision(self) -> None:
        requested = command("task", "make-ready")
        first = prepare_lifecycle_transition(snapshot("task", "pending"), requested)
        cast(dict[str, object], requested["actor"])["id"] = "agent:mutated"
        cast(dict[str, object], requested["reason"])["detail"] = "mutated"
        first_actor = cast(Mapping[str, object], first["actor"])
        first_reason = cast(Mapping[str, object], first["reason"])
        self.assertEqual("researcher:local-owner", first_actor["id"])
        self.assertEqual("Researcher recorded the bounded lifecycle decision.", first_reason["detail"])
        with self.assertRaises(TypeError):
            first["state"] = "mutated"  # type: ignore[index]

        first_revision = cast(int, first["revision"])
        restarted = snapshot("task", str(first["toState"]), first_revision)
        second = prepare_lifecycle_transition(restarted, command("task", "start", first_revision))
        self.assertEqual("in-progress", second["toState"])
        self.assertEqual(2, second["revision"])


if __name__ == "__main__":
    unittest.main()
