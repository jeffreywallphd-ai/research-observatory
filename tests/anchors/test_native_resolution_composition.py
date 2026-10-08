"""Actual native-only Core/SQLCipher/context resolution over declared synthetic IR.

This proves Core composition; no parser, Tauri process or hardware-tier test.
"""

import json
import os
import sqlite3
import time
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from research_observatory_core import storage
from research_observatory_core.document_revisions import DocumentRevisionProblem
from research_observatory_core.domain_contracts import new_uuid_v7
from research_observatory_core.object_store import _object_relative_path
from research_observatory_core.ports.repositories import AggregateRevisionDraft
from research_observatory_core.repositories import create_sqlite_unit_of_work_factory
from research_observatory_core.source_anchor_repository import LocalSourceAnchorRepository

from tests.anchors import test_native_anchor_composition as predecessor

ROOT = Path(__file__).resolve().parents[2]


class NativeResolutionCompositionTests(unittest.TestCase):
    def setUp(self):
        self.f = predecessor.NativeAnchorCompositionTests(methodName="runTest")
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        response = self.f.post(
            "anchor-create",
            commandId=new_uuid_v7(),
            selection={
                "schemaVersion": "1.0",
                "revisionId": self.f.accepted.revision_id,
                "nodeId": self.f.accepted.structure.nodes[0].node_id,
                "normalizedRange": {"start": 25, "end": 49},
            },
        )
        self.assertEqual(200, response.status_code)
        self.anchor = response.json()
        self.fields = {"anchorId": self.anchor["anchorId"], "expectedRevisionId": self.f.accepted.revision_id}

    def test_common_resolution_authenticates_exact_context_without_whole_ir_or_pdf(self):
        samples = []
        with patch(
            "research_observatory_core.document_revision_repository.LocalDocumentRevisionRepository._accepted",
            side_effect=AssertionError("common resolution must not read whole IR"),
        ):
            warm = self.f.post("anchor-resolve", **self.fields)
            self.assertEqual(200, warm.status_code)
            expected = warm.json()
            self.assertEqual("fallback", expected["status"])
            self.assertEqual(self.anchor["target"], expected["target"])
            for _ in range(20):
                began = time.perf_counter()
                response = self.f.post("anchor-resolve", **self.fields)
                samples.append((time.perf_counter() - began) * 1000)
                self.assertEqual(200, response.status_code)
                self.assertEqual(expected, response.json())
        output = os.environ.get("RO_RESOLUTION_TIMING_OUTPUT")
        if output:
            path = Path(output).resolve()
            path.relative_to((ROOT / "artifacts/tmp").resolve())
            self.assertFalse(path.exists())
            path.write_text(
                json.dumps(
                    {
                        "kind": "synthetic-exact-context-actual-Core-native-composition",
                        "samplesMs": samples,
                        "warmP95Ms": sorted(samples)[18],
                        "budgetMs": 100,
                        "method": (
                            "20 consecutive warm in-process HTTP/current native session/Intent/privacy/"
                            "rights/SQLCipher/envelope resolutions; nearest-rank p95"
                        ),
                        "parsing": "declared-synthetic-predecessor-IR",
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        self.assertLessEqual(sorted(samples)[18], 100, "retain actual over-budget measurements")

    def test_substitutions_and_late_native_detach_deny_research_content(self):
        for fields in (dict(self.fields, expectedRevisionId=new_uuid_v7()), dict(self.fields, anchorId=new_uuid_v7())):
            response = self.f.post("anchor-resolve", **fields)
            self.assertEqual(409, response.status_code)
            self.assertNotIn("Second synthetic", response.text)
        original = LocalSourceAnchorRepository.resolve

        def late(repository, *args, **kwargs):
            result = original(repository, *args, **kwargs)
            self.f.f.f.preview.service.detach(self.f.f.f.preview.root)
            return result

        with patch.object(LocalSourceAnchorRepository, "resolve", late):
            response = self.f.post("anchor-resolve", **self.fields)
        self.assertEqual(409, response.status_code)
        self.assertNotIn("Second synthetic", response.text)
        self.assertEqual(409, self.f.post("anchor-resolve", **self.fields).status_code)

    def _reopen_native_session(self):
        preview = self.f.f.f.preview
        old_session = dict(self.f.session)
        preview.service.detach(preview.root)
        preview.projects.close(root=preview.root, trace_id="f" * 32)
        preview.projects.open(root=preview.root, trace_id="f" * 32)
        preview.service.attach(preview.root)
        self.f.session["sessionId"] = preview.service.native_context(preview.root, self.anchor["target"]["projectId"])
        self.assertNotEqual(old_session["sessionId"], self.f.session["sessionId"])
        return old_session

    def test_native_stop_during_invalidation_rolls_back_and_fresh_session_retries_once(self):
        fixture = self.f.f.fixture
        project = self.anchor["target"]["projectId"]
        anchor_revision = self.anchor["anchorRevisionId"]
        with create_sqlite_unit_of_work_factory(fixture.database, project)() as unit:
            source = unit.aggregates.get_revision(anchor_revision)
            unit.aggregates.append(
                AggregateRevisionDraft(
                    revision_id=new_uuid_v7(),
                    aggregate_id=new_uuid_v7(),
                    aggregate_kind="evidence",
                    created_at=fixture.now,
                    modified_at=fixture.now,
                    display_label_observed="Synthetic stopped anchor-dependent evidence",
                    display_label_normalized=None,
                    knowledge_status="observed",
                    rights_status="unknown",
                    provenance_inputs=(source,),
                    dependency_coverage="complete",
                    material_dependencies=fixture.repository._dependencies((source,)),
                ),
                fixture.repository._event(fixture.actor, fixture.now, "evidence.created", "fixture." + new_uuid_v7()),
                expected_revision=None,
            )
            unit.commit()
        with closing(storage.open_canonical_database(fixture.database, expected_project_id=project)) as connection:
            digest = connection.execute(
                "SELECT object_sha256 FROM documents WHERE revision_id=?", (anchor_revision,)
            ).fetchone()[0]
        path = fixture.f.fixture.project_root / "objects" / _object_relative_path(project, digest)
        damaged = bytearray(path.read_bytes())
        damaged[-1] ^= 1
        path.write_bytes(damaged)
        tables = ("dependency_impact_runs", "dependency_stale_causes", "provenance_events", "outbox_events")

        def counts():
            with closing(storage.open_canonical_database(fixture.database, expected_project_id=project)) as connection:
                return {
                    table: connection.execute('SELECT count(*) FROM "' + table + '"').fetchone()[0] for table in tables
                }

        before = counts()
        stops = []

        def stop(step):
            self.f.f.f.preview.service.signal_stop(self.f.f.f.preview.root)
            stops.append(step)

        with patch("research_observatory_core.source_anchor_repository._publication_step", stop):
            response = self.f.post("anchor-resolve", **self.fields)
        self.assertEqual(["anchor-dependents-stale"], stops)
        self.assertEqual(409, response.status_code)
        self.assertNotIn("Second synthetic", response.text)
        self.assertEqual(before, counts())

        old_session = self._reopen_native_session()
        old = self.f.client.post("/native/document-revisions/anchor-resolve", json=old_session | self.fields)
        self.assertEqual(409, old.status_code)
        self.assertEqual(before, counts())
        retried = self.f.post("anchor-resolve", **self.fields)
        self.assertEqual(200, retried.status_code)
        self.assertEqual("broken", retried.json()["status"])
        published = counts()
        self.assertEqual({table: value + 1 for table, value in before.items()}, published)
        replayed = self.f.post("anchor-resolve", **self.fields)
        self.assertEqual(200, replayed.status_code)
        self.assertEqual(retried.json(), replayed.json())
        self.assertEqual(published, counts())

    def test_native_stop_during_anchor_creation_rolls_back(self):
        fixture = self.f.f.fixture
        project = self.anchor["target"]["projectId"]
        tables = ("aggregate_revisions", "documents", "provenance_events", "outbox_events")

        def counts():
            with closing(storage.open_canonical_database(fixture.database, expected_project_id=project)) as connection:
                return {
                    table: connection.execute('SELECT count(*) FROM "' + table + '"').fetchone()[0] for table in tables
                }

        before = counts()
        stops = []

        def stop(step):
            self.f.f.f.preview.service.signal_stop(self.f.f.f.preview.root)
            stops.append(step)

        with patch("research_observatory_core.source_anchor_repository._publication_step", stop):
            response = self.f.post(
                "anchor-create",
                commandId=new_uuid_v7(),
                selection={
                    "schemaVersion": "1.0",
                    "revisionId": self.f.accepted.revision_id,
                    "nodeId": self.f.accepted.structure.nodes[0].node_id,
                    "normalizedRange": {"start": 0, "end": 5},
                },
            )
        self.assertEqual(["anchor-recorded"], stops)
        self.assertEqual(409, response.status_code)
        self.assertNotIn("First synthetic", response.text)
        self.assertEqual(before, counts())

    def test_lookup_and_context_share_owned_writer_without_verifying_original_bytes(self):
        database = self.f.f.fixture.database
        project = self.anchor["target"]["projectId"]
        digest = self.anchor["target"]["source"]["objectSha256"]

        def original_state():
            connection = storage.open_canonical_database(database, expected_project_id=project)
            try:
                return connection.execute(
                    "SELECT verified_at,storage_state FROM object_records WHERE object_sha256=?", (digest,)
                ).fetchone()
            finally:
                connection.close()

        before = original_state()
        sources, records = [], []
        source_read = LocalSourceAnchorRepository._source
        record_read = LocalSourceAnchorRepository._record

        def source(repository, connection, *args):
            sources.append(connection)
            return source_read(repository, connection, *args)

        def record(repository, connection, *args):
            records.append(connection)
            return record_read(repository, connection, *args)

        with (
            patch.object(LocalSourceAnchorRepository, "_source", source),
            patch.object(LocalSourceAnchorRepository, "_record", record),
            patch(
                "research_observatory_core.document_revision_repository.LocalDocumentRevisionRepository._accepted",
                side_effect=AssertionError("whole IR forbidden"),
            ),
        ):
            response = self.f.post("anchor-resolve", **self.fields)
        self.assertEqual(200, response.status_code)
        self.assertTrue(sources and records)
        self.assertTrue(all(connection is records[0] for connection in sources + records))
        with self.assertRaises(sqlite3.ProgrammingError):
            records[0].execute("SELECT 1")
        self.assertEqual(before, original_state())

    def test_late_intent_content_substitution_with_retained_declared_hash_denies(self):
        original = LocalSourceAnchorRepository.resolve
        substituted = []
        failures = []

        def replace_content(repository, *args, **kwargs):
            # Test-only external corruption; ordinary canonical connections deny DDL.
            connection = storage._connect_held(repository.revisions.database, project_id=repository.revisions.project)
            try:
                row = connection.execute(
                    "SELECT revision,text_value FROM settings WHERE setting_key='research-intent.revision' "
                    "ORDER BY revision DESC LIMIT 1"
                ).fetchone()
                value = json.loads(row[1])
                value["phenomenon"]["value"] = "Synthetic substituted Intent content"
                trigger = connection.execute(
                    "SELECT sql FROM sqlite_master WHERE name='settings_no_update'"
                ).fetchone()[0]
                connection.execute("DROP TRIGGER settings_no_update")
                connection.execute(
                    "UPDATE settings SET text_value=? WHERE setting_key='research-intent.revision' AND revision=?",
                    (json.dumps(value, sort_keys=True, separators=(",", ":")), row[0]),
                )
                connection.execute(trigger)
                connection.commit()
                substituted.append(True)
            except Exception as error:
                failures.append(type(error).__name__)
                raise
            finally:
                connection.close()
            return original(repository, *args, **kwargs)

        with patch.object(LocalSourceAnchorRepository, "resolve", replace_content):
            response = self.f.post("anchor-resolve", **self.fields)
        self.assertEqual([True], substituted, failures)
        self.assertEqual(409, response.status_code)
        self.assertNotIn("Second synthetic", response.text)

    def test_failed_or_foreign_source_resolution_closes_writer_before_protected_context(self):
        original = LocalSourceAnchorRepository._source
        for mode in ("failed", "foreign-project"):
            connections = []

            def source(repository, connection, revision_id, mode=mode, connections=connections):
                connections.append(connection)
                if mode == "failed":
                    raise DocumentRevisionProblem("source-anchor-revision-unavailable")
                return original(repository, connection, revision_id).model_copy(update={"project_id": new_uuid_v7()})

            with (
                patch.object(LocalSourceAnchorRepository, "_source", source),
                patch.object(LocalSourceAnchorRepository, "_record", side_effect=AssertionError("context forbidden")),
            ):
                response = self.f.post("anchor-resolve", **self.fields)
            self.assertEqual(409, response.status_code)
            self.assertNotIn("Second synthetic", response.text)
            self.assertEqual(1, len(connections))
            with self.assertRaises(sqlite3.ProgrammingError):
                connections[0].execute("SELECT 1")


if __name__ == "__main__":
    unittest.main(verbosity=2)
