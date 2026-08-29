from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
SERVICE_SRC = REPO / "services" / "core-api" / "src"
sys.path.insert(0, str(SERVICE_SRC))

from research_observatory_core import object_store as object_store_module  # noqa: E402
from research_observatory_core.object_store import create_local_object_store  # noqa: E402
from research_observatory_core.ports.object_store import (  # noqa: E402
    ObjectConflict,
    ObjectNotFound,
    ObjectPutCommand,
    ObjectStoragePressure,
    ObjectStoreProblem,
    StorageCleanupRequest,
    StoragePolicy,
)
from research_observatory_core.ports.repositories import (  # noqa: E402
    AggregateRevisionDraft,
    AtomicRepositoryEvent,
)
from research_observatory_core.repositories import create_sqlite_unit_of_work_factory  # noqa: E402
from research_observatory_core.storage import development_plaintext_database_fixture, initialize_database  # noqa: E402

PROJECT_ID = "123e4567-e89b-42d3-a456-426614174020"
CREATED_AT = "2026-08-18T16:00:00.000Z"
TRACE_ID = "0123456789abcdef0123456789abcdef"


def put_command(*, retention_class: str = "project-lifetime") -> ObjectPutCommand:
    return ObjectPutCommand(
        media_type="application/pdf",
        rights_status="allowed",
        protection_profile="plaintext-fixture-v1",
        retention_class=retention_class,  # type: ignore[arg-type]
        creation_source="test-fixture",
        created_at=CREATED_AT,
    )


def document_draft(object_sha256: str) -> AggregateRevisionDraft:
    return AggregateRevisionDraft(
        revision_id="01890f6e-6a40-7cc5-98b7-000000000901",
        aggregate_id="01890f6e-6a40-7cc5-98b7-000000000900",
        aggregate_kind="document",
        created_at=CREATED_AT,
        modified_at=CREATED_AT,
        display_label_observed="Retained canonical document",
        display_label_normalized=None,
        knowledge_status="observed",
        rights_status="allowed",
        object_sha256=object_sha256,
    )


def event() -> AtomicRepositoryEvent:
    return AtomicRepositoryEvent(
        event_id="01890f6e-6a40-7cc5-98b7-000000000902",
        outbox_id="01890f6e-6a40-7cc5-98b7-000000000903",
        event_type="document.created",
        occurred_at=CREATED_AT,
        available_at=CREATED_AT,
        trace_id=TRACE_ID,
        actor_type="human",
        actor_id="01890f6e-6a40-7cc5-98b7-000000000301",
        idempotency_key="storage-maintenance-document",
    )


def cleanup_request(*categories: str) -> StorageCleanupRequest:
    return StorageCleanupRequest(
        categories=categories,  # type: ignore[arg-type]
        requested_at=CREATED_AT,
        trace_id=TRACE_ID,
        actor_id="human.storage-maintenance-test",
    )


class StorageMaintenanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database_profile = development_plaintext_database_fixture()
        self.database_profile.__enter__()
        self.temporary = tempfile.TemporaryDirectory(prefix="ro-storage-maintenance-")
        self.parent = Path(self.temporary.name).resolve()
        self.project = self.parent / "project"
        for relative in (
            "state",
            "objects",
            "indexes",
            "cache",
            "models",
            "config",
            "exports",
            "logs",
            ".locks",
            ".tmp",
        ):
            (self.project / relative).mkdir(parents=True, mode=0o700)
        self.database = self.project / "state" / "project.sqlite3"
        initialize_database(self.database, project_id=PROJECT_ID, project_created_at=CREATED_AT)
        self.shared_cache = self.parent / "shared-cache"
        self.shared_cache.mkdir(mode=0o700)

    def tearDown(self) -> None:
        try:
            self.temporary.cleanup()
        finally:
            self.database_profile.__exit__(None, None, None)

    def create_store(self, policy: StoragePolicy | None = None):
        return create_local_object_store(
            self.project,
            PROJECT_ID,
            allow_plaintext_fixture=True,
            storage_policy=policy,
            shared_cache_root=self.shared_cache,
        )

    def link_document(self, object_sha256: str) -> None:
        factory = create_sqlite_unit_of_work_factory(self.database, PROJECT_ID)
        with factory() as unit:
            unit.aggregates.append(document_draft(object_sha256), event(), expected_revision=None)
            unit.commit()

    def test_usage_preview_and_cleanup_are_category_explicit_reference_safe_and_audited(self) -> None:
        store = self.create_store(StoragePolicy(project_soft_limit_bytes=1, minimum_free_bytes=0))
        retained = store.put(io.BytesIO(b"retained canonical content"), put_command())
        self.link_document(retained.object_sha256)
        derivative = store.put(
            io.BytesIO(b"rebuildable derivative"),
            put_command(retention_class="derived-rebuildable"),
        )
        (self.project / "cache" / "parse.cache").write_bytes(b"project-cache")
        (self.project / "indexes" / "search.idx").write_bytes(b"index")
        (self.project / "models" / "local.model").write_bytes(b"model")
        (self.shared_cache / "shared.model").write_bytes(b"shared-model")
        orphan = self.project / "objects" / "fe" / "ed" / f"{'f' * 64}.blob"
        orphan.parent.mkdir(parents=True)
        orphan.write_bytes(b"unpublished-orphan")

        usage = store.usage()
        categories = {entry.category: entry for entry in usage.categories}
        self.assertEqual("soft-limit", usage.project_pressure)
        self.assertGreater(usage.project_byte_count, 0)
        self.assertEqual(len(b"shared-model"), usage.shared_cache_byte_count)
        self.assertEqual(1, categories["durable-objects"].item_count)
        self.assertEqual(0, categories["durable-objects"].reclaimable_item_count)
        self.assertEqual(1, categories["derived-objects"].reclaimable_item_count)
        self.assertEqual(1, categories["orphaned-objects"].reclaimable_item_count)

        preview = store.preview_cleanup(
            cleanup_request(
                "derived-objects",
                "orphaned-objects",
                "indexes",
                "project-cache",
                "models",
                "shared-cache",
            )
        )
        self.assertGreater(preview.reclaimable_byte_count, 0)
        self.assertEqual(
            {
                "derived-objects",
                "orphaned-objects",
                "indexes",
                "project-cache",
                "models",
                "shared-cache",
            },
            {entry.category for entry in preview.categories},
        )
        self.assertTrue(orphan.exists(), "preview must not delete bytes")
        with store.open(retained.object_sha256, purpose="document-analysis") as stream:
            self.assertEqual(b"retained canonical content", stream.read())

        result = store.cleanup(preview.preview_token)
        self.assertEqual(preview.reclaimable_item_count, result.reclaimed_item_count)
        self.assertEqual(0, result.skipped_item_count)
        with store.open(retained.object_sha256, purpose="document-analysis") as stream:
            self.assertEqual(b"retained canonical content", stream.read())
        with self.assertRaises(ObjectNotFound):
            store.open(derivative.object_sha256, purpose="document-analysis")
        self.assertFalse(orphan.exists())
        self.assertFalse((self.project / "cache" / "parse.cache").exists())
        self.assertFalse((self.project / "indexes" / "search.idx").exists())
        self.assertFalse((self.project / "models" / "local.model").exists())
        self.assertFalse((self.shared_cache / "shared.model").exists())

        audit = [
            json.loads(line)
            for line in (self.project / "logs" / "storage-maintenance.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(["storage.cleanup.started", "storage.cleanup.completed"], [row["event"] for row in audit])
        self.assertNotIn(retained.object_sha256, json.dumps(audit))
        self.assertNotIn(str(self.project), json.dumps(audit))

    def test_cleanup_rechecks_references_readers_and_changed_cache_identity(self) -> None:
        store = self.create_store(StoragePolicy(minimum_free_bytes=0))
        became_referenced = store.put(
            io.BytesIO(b"linked after preview"),
            put_command(retention_class="derived-rebuildable"),
        )
        held = store.put(
            io.BytesIO(b"reader lease after preview"),
            put_command(retention_class="derived-rebuildable"),
        )
        cache = self.project / "cache" / "mutable.cache"
        cache.write_bytes(b"previewed-cache")
        preview = store.preview_cleanup(cleanup_request("derived-objects", "project-cache"))

        self.link_document(became_referenced.object_sha256)
        reader = store.open(held.object_sha256, purpose="document-analysis")
        cache.write_bytes(b"changed-content")
        try:
            result = store.cleanup(preview.preview_token)
        finally:
            reader.close()

        self.assertEqual(0, result.reclaimed_item_count)
        self.assertEqual(3, result.skipped_item_count)
        with store.open(became_referenced.object_sha256, purpose="document-analysis") as stream:
            self.assertEqual(b"linked after preview", stream.read())
        with store.open(held.object_sha256, purpose="document-analysis") as stream:
            self.assertEqual(b"reader lease after preview", stream.read())
        self.assertEqual(b"changed-content", cache.read_bytes())
        with self.assertRaises(ObjectConflict):
            store.cleanup(preview.preview_token)

    def test_stale_cleanup_preview_never_deletes_a_republished_derived_generation(self) -> None:
        store = self.create_store(StoragePolicy(minimum_free_bytes=0))
        payload = b"republished derived generation"
        original = store.put(
            io.BytesIO(payload),
            put_command(retention_class="derived-rebuildable"),
        )
        preview = store.preview_cleanup(cleanup_request("derived-objects"))
        plan = store._state().cleanup_plan
        self.assertIsNotNone(plan)
        assert plan is not None
        candidate = next(item for item in plan.candidates if item.object_sha256 == original.object_sha256)

        store.delete(original.object_sha256)
        republished = store.put(
            io.BytesIO(payload),
            put_command(retention_class="derived-rebuildable"),
        )
        current = candidate.path.stat(follow_symlinks=False)
        self.assertNotEqual(candidate.identity, (current.st_dev, current.st_ino))

        result = store.cleanup(preview.preview_token)

        self.assertEqual(0, result.reclaimed_item_count)
        self.assertEqual(1, result.skipped_item_count)
        self.assertEqual(republished, store.metadata(republished.object_sha256))
        with store.open(republished.object_sha256, purpose="test-verification") as stream:
            self.assertEqual(payload, stream.read())

    def test_cleanup_move_is_bound_to_the_previewed_file_identity(self) -> None:
        store = self.create_store(StoragePolicy(minimum_free_bytes=0))
        cache = self.project / "cache" / "race.cache"
        saved = self.project / "cache" / "previewed-generation.saved"
        cache.write_bytes(b"previewed-generation")
        preview = store.preview_cleanup(cleanup_request("project-cache"))
        original_held_candidate = object_store_module._held_cleanup_candidate

        @contextmanager
        def replace_before_handle_open(candidate: Any):
            if getattr(candidate, "path", None) == cache:
                cache.rename(saved)
                cache.write_bytes(b"post-preview-generation")
            with original_held_candidate(candidate) as operations:
                yield operations

        with patch.object(object_store_module, "_held_cleanup_candidate", replace_before_handle_open):
            result = store.cleanup(preview.preview_token)

        self.assertEqual(0, result.reclaimed_item_count)
        self.assertEqual(1, result.skipped_item_count)
        self.assertEqual(b"post-preview-generation", cache.read_bytes())
        self.assertEqual(b"previewed-generation", saved.read_bytes())
        self.assertEqual([], list((self.project / ".tmp" / "storage-cleanup").iterdir()))
        self.create_store(StoragePolicy(minimum_free_bytes=0))
        self.assertEqual(b"post-preview-generation", cache.read_bytes())

    def test_restart_deletes_only_identity_committed_cleanup_partials(self) -> None:
        store = self.create_store(StoragePolicy(minimum_free_bytes=0))
        cache = self.project / "cache" / "interrupted.cache"
        cache.write_bytes(b"interrupted-generation")
        preview = store.preview_cleanup(cleanup_request("project-cache"))

        def interrupt_after_move(step: str) -> None:
            if step == "after-rebuildable-move":
                raise RuntimeError("injected post-move interruption")

        with (
            patch.object(object_store_module, "_cleanup_step_completed", side_effect=interrupt_after_move),
            self.assertRaises(ObjectStoreProblem),
        ):
            store.cleanup(preview.preview_token)

        staging = self.project / ".tmp" / "storage-cleanup"
        partials = list(staging.iterdir())
        self.assertEqual(1, len(partials))
        self.assertEqual(b"interrupted-generation", partials[0].read_bytes())
        self.assertFalse(cache.exists())

        self.create_store(StoragePolicy(minimum_free_bytes=0))

        self.assertEqual([], list(staging.iterdir()))

    def test_restart_preserves_cleanup_partial_when_filename_identity_does_not_match(self) -> None:
        self.create_store(StoragePolicy(minimum_free_bytes=0))
        authority = self.project / "cache" / "preview-authority.cache"
        payload = b"preview-authority"
        authority.write_bytes(payload)
        status = authority.stat(follow_symlinks=False)
        staging = self.project / ".tmp" / "storage-cleanup"
        staging.mkdir(exist_ok=True)
        authority_candidate = object_store_module._FileCandidate(
            category="project-cache",
            path=authority,
            authority_root=self.project / "cache",
            identity=(status.st_dev, status.st_ino),
            byte_count=status.st_size,
            modified_ns=status.st_mtime_ns,
        )
        commitment = object_store_module._cleanup_candidate_commitment(authority_candidate)
        partial = staging / f"cleanup-{'a' * 24}-{commitment}.partial"
        post_preview = b"replacement-bytes"
        self.assertEqual(len(payload), len(post_preview))
        partial.write_bytes(post_preview)

        with self.assertRaises(ObjectStoreProblem):
            self.create_store(StoragePolicy(minimum_free_bytes=0))

        self.assertEqual(post_preview, partial.read_bytes())
        self.assertEqual(payload, authority.read_bytes())

    def test_cleanup_partial_name_is_bounded_and_commits_the_full_identity(self) -> None:
        candidate = object_store_module._FileCandidate(
            category="project-cache",
            path=self.project / "cache" / "bounded.cache",
            authority_root=self.project / "cache",
            identity=(2**64 - 1, 2**64 - 1),
            byte_count=2**53 - 1,
            modified_ns=2**63 - 1,
        )

        partial = object_store_module._cleanup_partial_path(self.project / ".tmp", candidate)

        self.assertEqual(84, len(partial.name))
        self.assertIn(object_store_module._cleanup_candidate_commitment(candidate), partial.name)
        self.assertIsNotNone(object_store_module._CLEANUP_PARTIAL.fullmatch(partial.name))

    def test_hard_quota_and_low_disk_degrade_writes_without_blocking_reads(self) -> None:
        initial = self.create_store(StoragePolicy(minimum_free_bytes=0))
        retained = initial.put(io.BytesIO(b"readable under storage pressure"), put_command())
        current = initial.usage().project_byte_count

        hard_limited = self.create_store(
            StoragePolicy(project_soft_limit_bytes=current, project_hard_limit_bytes=current, minimum_free_bytes=0)
        )
        with self.assertRaises(ObjectStoragePressure) as hard:
            hard_limited.put(io.BytesIO(b"must not be admitted"), put_command())
        self.assertEqual("RO-CORE-OBJECT-STORAGE-PRESSURE", hard.exception.code)
        with hard_limited.open(retained.object_sha256, purpose="document-analysis") as stream:
            self.assertEqual(b"readable under storage pressure", stream.read())

        low_disk = self.create_store(StoragePolicy(minimum_free_bytes=1024))
        with patch.object(
            object_store_module.shutil,
            "disk_usage",
            return_value=SimpleNamespace(total=10_000, used=9_900, free=100),
        ):
            self.assertEqual("low-disk", low_disk.usage().project_pressure)
            with self.assertRaises(ObjectStoragePressure):
                low_disk.put(io.BytesIO(b"also not admitted"), put_command())
            with low_disk.open(retained.object_sha256, purpose="document-analysis") as stream:
                self.assertEqual(b"readable under storage pressure", stream.read())

    def test_interrupted_cleanup_is_restart_safe_and_resumable(self) -> None:
        store = self.create_store(StoragePolicy(minimum_free_bytes=0))
        first = store.put(io.BytesIO(b"first derivative"), put_command(retention_class="derived-rebuildable"))
        second = store.put(io.BytesIO(b"second derivative"), put_command(retention_class="derived-rebuildable"))
        preview = store.preview_cleanup(cleanup_request("derived-objects"))
        completed = 0

        def interrupt(step: str) -> None:
            nonlocal completed
            if step == "after-candidate":
                completed += 1
                if completed == 1:
                    raise OSError("injected cleanup interruption")

        with (
            patch.object(object_store_module, "_cleanup_step_completed", side_effect=interrupt),
            self.assertRaises(ObjectStoreProblem),
        ):
            store.cleanup(preview.preview_token)

        restarted = self.create_store(StoragePolicy(minimum_free_bytes=0))
        states = {
            restarted.metadata(first.object_sha256).storage_state,
            restarted.metadata(second.object_sha256).storage_state,
        }
        self.assertEqual({"available", "deleted"}, states)
        resumed = restarted.preview_cleanup(cleanup_request("derived-objects"))
        result = restarted.cleanup(resumed.preview_token)
        self.assertEqual(1, result.reclaimed_item_count)
        self.assertEqual("deleted", restarted.metadata(first.object_sha256).storage_state)
        self.assertEqual("deleted", restarted.metadata(second.object_sha256).storage_state)

    def test_shared_cache_authority_cannot_overlap_project_authority(self) -> None:
        with self.assertRaises(ObjectStoreProblem):
            create_local_object_store(
                self.project,
                PROJECT_ID,
                allow_plaintext_fixture=True,
                storage_policy=StoragePolicy(minimum_free_bytes=0),
                shared_cache_root=self.project / "cache",
            )

    @unittest.skipUnless(hasattr(os, "link"), "hardlink support is unavailable")
    def test_hardlinked_cache_is_reported_but_never_reclaimed(self) -> None:
        store = self.create_store(StoragePolicy(minimum_free_bytes=0))
        outside = self.parent / "outside.bin"
        outside.write_bytes(b"outside shared identity")
        hostile = self.project / "cache" / "hostile.cache"
        os.link(outside, hostile)
        preview = store.preview_cleanup(cleanup_request("project-cache"))
        category = preview.categories[0]
        self.assertEqual(1, category.item_count)
        self.assertEqual(0, category.reclaimable_item_count)
        result = store.cleanup(preview.preview_token)
        self.assertEqual(0, result.reclaimed_item_count)
        self.assertEqual(b"outside shared identity", outside.read_bytes())
        self.assertTrue(hostile.exists())

    @unittest.skipUnless(hasattr(os, "link"), "hardlink support is unavailable")
    def test_cleanup_audit_failure_denies_deletion(self) -> None:
        store = self.create_store(StoragePolicy(minimum_free_bytes=0))
        cache = self.project / "cache" / "preserved.cache"
        cache.write_bytes(b"preserve without audit")
        preview = store.preview_cleanup(cleanup_request("project-cache"))
        outside = self.parent / "outside-audit.jsonl"
        outside.write_bytes(b"")
        os.link(outside, self.project / "logs" / "storage-maintenance.jsonl")

        with self.assertRaises(ObjectStoreProblem):
            store.cleanup(preview.preview_token)

        self.assertEqual(b"preserve without audit", cache.read_bytes())
        self.assertEqual(b"", outside.read_bytes())


if __name__ == "__main__":
    unittest.main()
