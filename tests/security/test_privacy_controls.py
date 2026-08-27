from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

REPO = Path(__file__).resolve().parents[2]
SERVICE_SRC = REPO / "services" / "core-api" / "src"
sys.path.insert(0, str(SERVICE_SRC))

from research_observatory_core.app import create_app  # noqa: E402
from research_observatory_core.authentication import capability_token_digest  # noqa: E402
from research_observatory_core.config import CoreSettings  # noqa: E402
from research_observatory_core.models import (  # noqa: E402
    CacheClearRequest,
    DocumentRetentionPolicy,
    PrivacyNetworkPolicy,
    PrivacyPolicyUpdateRequest,
    RemoteModelApproval,
    TelemetryMode,
)
from research_observatory_core.ports.object_store import (  # noqa: E402
    ObjectAccessRequest,
    StoredObject,
)
from research_observatory_core.privacy import PrivacyPolicyProblem, ProjectPrivacyService  # noqa: E402
from research_observatory_core.projects import ProjectLifecycleProblem, ProjectLifecycleService  # noqa: E402
from research_observatory_core.repositories import sqlite_privacy_policy_repository  # noqa: E402
from research_observatory_core.storage import (  # noqa: E402
    development_plaintext_database_fixture,
    open_canonical_database,
)

TOKEN = "0123456789abcdef" * 4
AUTHORITY = "127.0.0.1:49152"
TRACE = "a" * 32
CONSENT = "acknowledge-egress-preview-v1"


def update_command(
    root: str,
    *,
    revision: int = 0,
    network: PrivacyNetworkPolicy = PrivacyNetworkPolicy.OFFLINE,
    consent: str | None = None,
) -> PrivacyPolicyUpdateRequest:
    return PrivacyPolicyUpdateRequest(
        root=root,
        expected_revision=revision,
        network_policy=network,
        remote_model_approval=RemoteModelApproval.PREVIEW_EVERY_TASK,
        telemetry_mode=TelemetryMode.OFF,
        log_retention_days=14,
        document_retention=DocumentRetentionPolicy.PROJECT_LIFETIME,
        cache_retention_days=30,
        egress_consent_token=consent,
    )


def stored_object(project_id: str) -> ObjectAccessRequest:
    return ObjectAccessRequest(
        project_id=project_id,
        object_metadata=StoredObject(
            object_sha256="1" * 64,
            byte_length=3,
            media_type="text/plain",
            rights_status="allowed",
            protection_profile="encrypted-content-addressed-v1",
            retention_class="project-lifetime",
            creation_source="test-fixture",
            storage_state="available",
            created_at="2026-08-22T00:00:00.000Z",
            verified_at="2026-08-22T00:00:00.000Z",
            reference_count=1,
            envelope_version="encrypted-content-addressed-v1",
            key_version="test-key-v1",
            ciphertext_byte_length=19,
        ),
        purpose="provider-egress",
        access_class="controlled-egress",
        destination_id="provider-approved-one",
    )


class PrivacyControlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database_profile = development_plaintext_database_fixture()
        self.database_profile.__enter__()
        self.temporary = tempfile.TemporaryDirectory(prefix="ro-privacy-controls-")
        self.parent = Path(self.temporary.name).resolve(strict=True)
        self.lifecycle = ProjectLifecycleService()
        created = self.lifecycle.create(
            parent_directory=str(self.parent),
            directory_name="study-one",
            display_name="Study One",
            template_id="theory-synthesis",
            trace_id=TRACE,
        )
        self.root = Path(created.root)
        self.project_id = created.project_id
        self.privacy = ProjectPrivacyService(self.lifecycle, sqlite_privacy_policy_repository)

    def tearDown(self) -> None:
        try:
            self.lifecycle.shutdown()
            self.temporary.cleanup()
        finally:
            self.database_profile.__exit__(None, None, None)

    def open(self) -> None:
        self.lifecycle.open(root=str(self.root), trace_id=TRACE)

    def privacy_cache_clear_audit_count(self) -> int:
        connection = sqlite3.connect(self.root / "state" / "project.sqlite3")
        try:
            return int(
                connection.execute(
                    "SELECT COUNT(*) FROM provenance_events WHERE event_type='privacy.cache.cleared'"
                ).fetchone()[0]
            )
        finally:
            connection.close()

    def assert_staged_canonical_substitution_is_denied(self, boundary_name: str) -> None:
        self.open()
        cache = self.root / "cache"
        cached = cache / "derived.bin"
        cached.write_bytes(b"rebuildable")
        canonical_directory = self.root / "config"
        canonical = canonical_directory / "project-profile.json"
        canonical_before = canonical.read_bytes()
        preview = self.privacy.preview_cache(str(self.root))
        tombstone = self.root / ".tmp" / f"cache-clear-{preview.preview_token}"
        boundaries: list[str] = []

        def attempt_substitution(boundary: str) -> None:
            boundaries.append(boundary)
            if boundary == boundary_name:
                canonical_directory.rename(tombstone / "config")

        with (
            patch("research_observatory_core.privacy._cache_clear_boundary", side_effect=attempt_substitution),
            self.assertRaisesRegex(ProjectLifecycleProblem, "RO-CORE-PROJECT-PATH-INVALID"),
        ):
            self.privacy.clear_cache(
                CacheClearRequest(
                    root=str(self.root),
                    preview_token=preview.preview_token,
                    confirmation=preview.confirmation,
                ),
                trace_id=TRACE,
            )

        self.assertIn(boundary_name, boundaries)
        self.assertEqual(canonical.read_bytes(), canonical_before)
        self.assertEqual(cached.read_bytes(), b"rebuildable")
        self.assertFalse(tombstone.exists())
        self.assertEqual(self.privacy_cache_clear_audit_count(), 0)
        (cache / "acl-restored.bin").write_bytes(b"writable")

    def test_defaults_are_local_only_and_project_session_authority_is_retained(self) -> None:
        with self.assertRaisesRegex(ProjectLifecycleProblem, "RO-CORE-PROJECT-NOT-OPEN"):
            self.privacy.get(str(self.root))
        self.open()

        policy = self.privacy.get(str(self.root))
        self.assertEqual(policy.project_id, self.project_id)
        self.assertEqual(policy.revision, 0)
        self.assertTrue(policy.defaults_applied)
        self.assertEqual(policy.network_policy, PrivacyNetworkPolicy.OFFLINE)
        self.assertEqual(policy.telemetry_mode, TelemetryMode.OFF)
        self.assertFalse(policy.egress_consent_recorded)
        self.assertEqual(policy.egress_enforcement, "deny")
        self.assertFalse(policy.deletion_disclosure.physical_erasure_guaranteed)
        self.assertTrue(policy.deletion_disclosure.canonical_project_data_excluded)

    def test_non_offline_policy_requires_exact_consent_and_remains_confirmation_bound(self) -> None:
        self.open()
        with self.assertRaises(ValidationError):
            update_command(str(self.root), network=PrivacyNetworkPolicy.APPROVED_PROVIDERS)
        with self.assertRaises(ValidationError):
            update_command(str(self.root), network=PrivacyNetworkPolicy.OFFLINE, consent=CONSENT)

        updated = self.privacy.update(
            update_command(
                str(self.root),
                network=PrivacyNetworkPolicy.APPROVED_PROVIDERS,
                consent=CONSENT,
            ),
            trace_id=TRACE,
        )
        self.assertEqual(updated.revision, 1)
        self.assertTrue(updated.egress_consent_recorded)
        self.assertEqual(updated.egress_enforcement, "require-task-preview")
        decision = self.privacy.object_access_policy(str(self.root)).authorize(stored_object(self.project_id))
        self.assertEqual(decision.outcome, "require-confirmation")

        local_request = stored_object(self.project_id)
        local_request = ObjectAccessRequest(
            project_id=local_request.project_id,
            object_metadata=local_request.object_metadata,
            purpose="document-analysis",
            access_class="local-read",
            destination_id=None,
        )
        self.assertEqual(
            self.privacy.object_access_policy(str(self.root)).authorize(local_request).outcome,
            "allow",
        )
        mismatched_local = ObjectAccessRequest(
            project_id="22222222-2222-4222-8222-222222222222",
            object_metadata=local_request.object_metadata,
            purpose="document-analysis",
            access_class="local-read",
            destination_id=None,
        )
        self.assertEqual(
            self.privacy.object_access_policy(str(self.root)).authorize(mismatched_local).outcome,
            "deny",
        )

    def test_policy_revisions_are_append_only_restart_safe_and_audited_without_paths(self) -> None:
        self.open()
        self.privacy.update(update_command(str(self.root)), trace_id=TRACE)
        with self.assertRaisesRegex(PrivacyPolicyProblem, "RO-CORE-PRIVACY-REVISION-CONFLICT"):
            self.privacy.update(update_command(str(self.root)), trace_id=TRACE)

        connection = open_canonical_database(
            self.root / "state" / "project.sqlite3", expected_project_id=self.project_id
        )
        try:
            settings = connection.execute(
                "SELECT setting_key, revision FROM settings WHERE project_id=? ORDER BY setting_key",
                (self.project_id,),
            ).fetchall()
            events = connection.execute(
                "SELECT event_type, record_sha256 FROM provenance_events WHERE project_id=? AND event_type=?",
                (self.project_id, "privacy.policy.changed"),
            ).fetchall()
        finally:
            connection.close()
        self.assertEqual(len(settings), 7)
        self.assertEqual({int(row[1]) for row in settings}, {1})
        self.assertEqual(len(events), 1)
        self.assertNotIn(str(self.root), json.dumps([tuple(row) for row in events]))

        self.lifecycle.close(root=str(self.root), trace_id=TRACE)
        restarted = ProjectLifecycleService()
        try:
            restarted.open(root=str(self.root), trace_id=TRACE)
            persisted = ProjectPrivacyService(restarted, sqlite_privacy_policy_repository).get(str(self.root))
            self.assertEqual(persisted.revision, 1)
            self.assertFalse(persisted.defaults_applied)
        finally:
            restarted.shutdown()

    def test_cache_clear_requires_current_preview_and_excludes_canonical_data(self) -> None:
        self.open()
        cache_file = self.root / "cache" / "derived.bin"
        cache_file.write_bytes(b"rebuildable")
        canonical = self.root / "config" / "project-profile.json"
        canonical_before = canonical.read_bytes()

        preview = self.privacy.preview_cache(str(self.root))
        self.assertEqual(preview.item_count, 1)
        self.assertEqual(preview.byte_count, len(b"rebuildable"))
        with self.assertRaisesRegex(ValidationError, "confirmation"):
            CacheClearRequest(
                root=str(self.root),
                preview_token=preview.preview_token,
                confirmation="clear-cache:" + "0" * 32,
            )
        cache_file.write_bytes(b"changed")
        with self.assertRaisesRegex(PrivacyPolicyProblem, "RO-CORE-CACHE-PREVIEW-STALE"):
            self.privacy.clear_cache(
                CacheClearRequest(
                    root=str(self.root),
                    preview_token=preview.preview_token,
                    confirmation=preview.confirmation,
                ),
                trace_id=TRACE,
            )
        self.assertEqual(cache_file.read_bytes(), b"changed")

        current = self.privacy.preview_cache(str(self.root))
        result = self.privacy.clear_cache(
            CacheClearRequest(
                root=str(self.root),
                preview_token=current.preview_token,
                confirmation=current.confirmation,
            ),
            trace_id=TRACE,
        )
        self.assertIn(result.state, {"cleared", "cleared-cleanup-pending"})
        self.assertTrue((self.root / "cache").is_dir())
        self.assertEqual(list((self.root / "cache").iterdir()), [])
        self.assertEqual(canonical.read_bytes(), canonical_before)
        self.assertTrue((self.root / "state" / "project.sqlite3").is_file())
        self.assertFalse(result.deletion_disclosure.physical_erasure_guaranteed)

        connection = sqlite3.connect(self.root / "state" / "project.sqlite3")
        try:
            count = connection.execute(
                "SELECT COUNT(*) FROM provenance_events WHERE event_type='privacy.cache.cleared'"
            ).fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(count, 1)

    @unittest.skipUnless(sys.platform == "win32", "Windows release-authority path boundary")
    def test_cache_clear_holds_exact_root_identity_across_the_rename_boundary(self) -> None:
        self.open()
        cache = self.root / "cache"
        cached = cache / "derived.bin"
        cached.write_bytes(b"rebuildable")
        canonical = self.root / "config" / "project-profile.json"
        canonical_before = canonical.read_bytes()
        preview = self.privacy.preview_cache(str(self.root))
        displaced = self.parent / "adversarial-cache-swap"
        boundaries: list[str] = []

        def attempt_swap(boundary: str) -> None:
            boundaries.append(boundary)
            if boundary != "before-held-cache-rename":
                return
            try:
                cache.rename(displaced)
            except OSError:
                raise
            else:
                displaced.rename(cache)
                raise AssertionError("the held cache directory allowed a path substitution")

        with (
            patch("research_observatory_core.privacy._cache_clear_boundary", side_effect=attempt_swap),
            self.assertRaisesRegex(ProjectLifecycleProblem, "RO-CORE-PROJECT-PATH-INVALID"),
        ):
            self.privacy.clear_cache(
                CacheClearRequest(
                    root=str(self.root),
                    preview_token=preview.preview_token,
                    confirmation=preview.confirmation,
                ),
                trace_id=TRACE,
            )

        self.assertEqual(boundaries, ["before-held-cache-rename"])
        self.assertEqual(cached.read_bytes(), b"rebuildable")
        self.assertEqual(canonical.read_bytes(), canonical_before)
        self.assertFalse(displaced.exists())
        self.assertEqual(list((self.root / ".tmp").glob("cache-clear-*")), [])
        connection = sqlite3.connect(self.root / "state" / "project.sqlite3")
        try:
            count = connection.execute(
                "SELECT COUNT(*) FROM provenance_events WHERE event_type='privacy.cache.cleared'"
            ).fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(count, 0)

    @unittest.skipUnless(sys.platform == "win32", "Windows release-authority path boundary")
    def test_cache_clear_denies_canonical_insertion_after_the_held_rename(self) -> None:
        self.assert_staged_canonical_substitution_is_denied("after-held-cache-rename")

    @unittest.skipUnless(sys.platform == "win32", "Windows release-authority path boundary")
    def test_cache_clear_denies_canonical_insertion_after_staged_validation(self) -> None:
        self.assert_staged_canonical_substitution_is_denied("after-staged-cache-validation")

    @unittest.skipUnless(sys.platform == "win32", "Windows release-authority path boundary")
    def test_cache_clear_keeps_the_staged_tree_protected_after_audit(self) -> None:
        self.open()
        cache = self.root / "cache"
        (cache / "derived.bin").write_bytes(b"rebuildable")
        canonical_directory = self.root / "config"
        canonical = canonical_directory / "project-profile.json"
        canonical_before = canonical.read_bytes()
        preview = self.privacy.preview_cache(str(self.root))
        tombstone = self.root / ".tmp" / f"cache-clear-{preview.preview_token}"
        denied: list[str] = []

        def attempt_substitution(boundary: str) -> None:
            if boundary != "after-cache-audit-before-cleanup":
                return
            try:
                canonical_directory.rename(tombstone / "config")
            except OSError:
                denied.append(boundary)
            else:
                (tombstone / "config").rename(canonical_directory)
                raise AssertionError("the protected staged tree accepted canonical project data")

        with patch("research_observatory_core.privacy._cache_clear_boundary", side_effect=attempt_substitution):
            result = self.privacy.clear_cache(
                CacheClearRequest(
                    root=str(self.root),
                    preview_token=preview.preview_token,
                    confirmation=preview.confirmation,
                ),
                trace_id=TRACE,
            )

        self.assertEqual(denied, ["after-cache-audit-before-cleanup"])
        self.assertEqual(canonical.read_bytes(), canonical_before)
        self.assertFalse(tombstone.exists())
        self.assertEqual(result.state.value, "cleared")
        self.assertEqual(self.privacy_cache_clear_audit_count(), 1)

    @unittest.skipUnless(sys.platform == "win32", "Windows release-authority path boundary")
    def test_cleanup_pending_tombstone_remains_protected_from_canonical_insertion(self) -> None:
        self.open()
        cache = self.root / "cache"
        (cache / "derived.bin").write_bytes(b"rebuildable")
        canonical_directory = self.root / "config"
        canonical = canonical_directory / "project-profile.json"
        canonical_before = canonical.read_bytes()
        preview = self.privacy.preview_cache(str(self.root))
        tombstone = self.root / ".tmp" / f"cache-clear-{preview.preview_token}"

        with patch(
            "research_observatory_core.privacy._remove_tree_no_follow",
            side_effect=OSError("forced cleanup interruption"),
        ):
            result = self.privacy.clear_cache(
                CacheClearRequest(
                    root=str(self.root),
                    preview_token=preview.preview_token,
                    confirmation=preview.confirmation,
                ),
                trace_id=TRACE,
            )

        self.assertEqual(result.state.value, "cleared-cleanup-pending")
        self.assertTrue(tombstone.is_dir())
        with self.assertRaises(OSError):
            canonical_directory.rename(tombstone / "config")
        self.assertEqual(canonical.read_bytes(), canonical_before)
        self.assertEqual(self.privacy_cache_clear_audit_count(), 1)

    @unittest.skipUnless(sys.platform == "win32", "Windows release-authority path boundary")
    def test_cache_clear_rejects_a_post_preview_redirect_without_touching_its_target(self) -> None:
        self.open()
        cache = self.root / "cache"
        target = self.parent / "post-preview-cache-target"
        (cache / "derived.bin").write_bytes(b"rebuildable")
        preview = self.privacy.preview_cache(str(self.root))
        cache.rename(target)
        protected = target / "must-remain.txt"
        protected.write_text("outside", encoding="utf-8")
        created = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(cache), str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
        if created.returncode != 0:
            target.rename(cache)
            self.skipTest(f"directory junctions are unavailable: {created.stderr.strip()}")
        try:
            with self.assertRaisesRegex(ProjectLifecycleProblem, "RO-CORE-PROJECT-PATH-INVALID"):
                self.privacy.clear_cache(
                    CacheClearRequest(
                        root=str(self.root),
                        preview_token=preview.preview_token,
                        confirmation=preview.confirmation,
                    ),
                    trace_id=TRACE,
                )
            self.assertEqual(protected.read_text(encoding="utf-8"), "outside")
            connection = sqlite3.connect(self.root / "state" / "project.sqlite3")
            try:
                count = connection.execute(
                    "SELECT COUNT(*) FROM provenance_events WHERE event_type='privacy.cache.cleared'"
                ).fetchone()[0]
            finally:
                connection.close()
            self.assertEqual(count, 0)
        finally:
            os.rmdir(cache)
            target.rename(cache)

    @unittest.skipUnless(sys.platform == "win32", "Windows release-authority path boundary")
    def test_cache_preview_rejects_a_redirect_without_touching_its_target(self) -> None:
        self.open()
        cache = self.root / "cache"
        target = self.parent / "outside-cache-target"
        cache.rename(target)
        protected = target / "must-remain.txt"
        protected.write_text("outside", encoding="utf-8")
        created = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(cache), str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
        if created.returncode != 0:
            target.rename(cache)
            self.skipTest(f"directory junctions are unavailable: {created.stderr.strip()}")
        try:
            with self.assertRaisesRegex(ProjectLifecycleProblem, "RO-CORE-PROJECT-PATH-INVALID"):
                self.privacy.preview_cache(str(self.root))
            self.assertEqual(protected.read_text(encoding="utf-8"), "outside")
        finally:
            os.rmdir(cache)
            target.rename(cache)

    def test_authenticated_api_enforces_consent_and_cache_confirmation(self) -> None:
        app = create_app(
            settings=CoreSettings(),
            capability_digest=capability_token_digest(TOKEN),
            expected_authority=AUTHORITY,
            projects=self.lifecycle,
            privacy=self.privacy,
        )
        headers = {"Authorization": f"Bearer {TOKEN}"}
        with TestClient(
            app,
            base_url=f"http://{AUTHORITY}",
            headers=headers,
            client=("127.0.0.1", 50000),
        ) as client:
            created = client.post(
                "/projects",
                json={
                    "parentDirectory": str(self.parent),
                    "directoryName": "api-study",
                    "displayName": "API Study",
                    "templateId": "theory-synthesis",
                },
            )
            self.assertEqual(created.status_code, 200, created.text)
            root = created.json()["root"]
            self.assertEqual(client.post("/projects/open", json={"root": root}).status_code, 200)
            policy = client.post("/projects/privacy", json={"root": root})
            self.assertEqual(policy.status_code, 200, policy.text)
            self.assertEqual(policy.json()["networkPolicy"], "offline")
            denied = client.post(
                "/projects/privacy/update",
                json={
                    "root": root,
                    "expectedRevision": 0,
                    "networkPolicy": "approved-providers",
                    "remoteModelApproval": "preview-every-task",
                    "telemetryMode": "off",
                    "logRetentionDays": 14,
                    "documentRetention": "project-lifetime",
                    "cacheRetentionDays": 30,
                    "egressConsentToken": None,
                },
            )
            self.assertEqual(denied.status_code, 422)
            self.assertEqual(denied.json()["code"], "RO-CORE-VALIDATION-FAILED")
            preview = client.post("/projects/privacy/cache/preview", json={"root": root})
            self.assertEqual(preview.status_code, 200, preview.text)
            cleared = client.post(
                "/projects/privacy/cache/clear",
                json={
                    "root": root,
                    "previewToken": preview.json()["previewToken"],
                    "confirmation": preview.json()["confirmation"],
                },
            )
            self.assertEqual(cleared.status_code, 200, cleared.text)
            self.assertFalse(cleared.json()["deletionDisclosure"]["physicalErasureGuaranteed"])


if __name__ == "__main__":
    unittest.main()
