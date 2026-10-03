"""Verify one committed synthetic Windows document drop after the app exits.

All paths are confined to the ignored directory-dialog fixture. The verifier
opens the existing SQLCipher project through Core's canonical database reader;
it never creates a project, grants rights, or publishes an attachment. Stdout
contains opaque IDs and digests only, so it can be retained as test evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import re
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services/core-api/src"))

from research_observatory_core.domain_contracts import is_uuid_v7  # noqa: E402
from research_observatory_core.rights_policy import RightsPolicyRevision  # noqa: E402
from research_observatory_core.storage import (  # noqa: E402
    configure_protected_database_provider,
    open_canonical_database,
)
from research_observatory_core.windows_credentials import create_windows_database_key_provider  # noqa: E402

_SOURCE_NAME = "document-drop-source.txt"
_SOURCE_SHA256 = "b83fc32249fefc9f92520155a0f78353d02a23365d582bb39bc060c096890d91"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_SQLITE_HEADER = b"SQLite format 3\x00"


class FixtureFailure(Exception):
    """Content-free reason for a nonqualifying synthetic fixture."""


@dataclass(frozen=True, slots=True)
class Expected:
    project_id: str
    work_id: str
    work_revision_id: str
    version_id: str
    version_revision_id: str
    source_assertion_revision_id: str
    source_sha256: str
    operation_id: str
    command_id: str
    attachment_id: str
    document_revision_id: str
    candidate_id: str | None


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise FixtureFailure(code)


def _project_id(value: str) -> bool:
    try:
        parsed = UUID(value)
    except TypeError, ValueError, AttributeError:
        return False
    return str(parsed) == value and parsed.version in {4, 7}


def _regular(path: Path, code: str) -> Path:
    _require(path.is_file() and path.resolve(strict=True) == path, code)
    _require(not path.is_symlink() and not getattr(path, "is_junction", lambda: False)(), code)
    _require(stat.S_ISREG(path.stat(follow_symlinks=False).st_mode), code)
    return path


def _directory(path: Path, code: str) -> Path:
    _require(path.is_dir() and path.resolve(strict=True) == path, code)
    _require(not path.is_symlink() and not getattr(path, "is_junction", lambda: False)(), code)
    return path


def _one(connection, sql: str, values: tuple[object, ...], code: str):
    row = connection.execute(sql, values).fetchone()
    _require(row is not None, code)
    return row


def _count(connection, table: str, project_id: str) -> int:
    # Every table name is a fixed call-site literal, never CLI input.
    return int(connection.execute(f"SELECT COUNT(*) FROM {table} WHERE project_id=?", (project_id,)).fetchone()[0])


def _require_provenance_binding(provenance, attachment, expected: Expected) -> None:
    _require(
        provenance["project_id"] == provenance["outbox_project_id"] == expected.project_id
        and provenance["revision_id"] == provenance["outbox_revision_id"] == expected.document_revision_id
        and provenance["event_type"]
        == provenance["outbox_event_type"]
        == "org.research-observatory.document.revision-recorded.v1"
        and provenance["actor_type"] == "human"
        and provenance["actor_id"] == attachment["actor_id"]
        and provenance["occurred_at"] == attachment["committed_at"]
        and provenance["record_sha256"] == provenance["outbox_record_sha256"]
        and provenance["idempotency_key"] == "document-attachment-" + expected.command_id,
        "attachment-provenance-binding-mismatch",
    )


def _inspect_database(database: Path, expected: Expected, source_length: int) -> dict[str, str]:
    with open_canonical_database(database, expected_project_id=expected.project_id) as connection:
        for table in (
            "document_attachment_operations",
            "document_attachment_candidates",
            "document_attachment_assertions",
        ):
            _require(_count(connection, table, expected.project_id) == 1, "attachment-count-not-exact")

        candidate = _one(
            connection,
            "SELECT c.*,o.candidate_id AS operation_candidate_id,o.actor_id AS operation_actor_id "
            "FROM document_attachment_operations o JOIN document_attachment_candidates c "
            "ON c.project_id=o.project_id AND c.candidate_id=o.candidate_id "
            "WHERE o.project_id=? AND o.operation_id=?",
            (expected.project_id, expected.operation_id),
            "operation-candidate-unavailable",
        )
        candidate_id = str(candidate["candidate_id"])
        selection = (
            expected.source_assertion_revision_id,
            expected.work_id,
            expected.work_revision_id,
            expected.version_id,
            expected.version_revision_id,
        )
        _require(
            tuple(
                candidate[key]
                for key in (
                    "source_assertion_revision_id",
                    "work_id",
                    "work_revision_id",
                    "version_id",
                    "version_revision_id",
                )
            )
            == selection,
            "candidate-selection-mismatch",
        )
        _require(expected.candidate_id is None or candidate_id == expected.candidate_id, "candidate-id-mismatch")
        _require(
            candidate["operation_candidate_id"] == candidate_id
            and candidate["object_sha256"] == expected.source_sha256
            and candidate["byte_length"] == source_length
            and candidate["format_name"] == "plain-text"
            and candidate["media_type"] == "text/plain"
            and candidate["source_name"] == _SOURCE_NAME
            and candidate["confirmation_required"] == 1,
            "candidate-content-mismatch",
        )
        _require(
            connection.execute(
                "SELECT 1 FROM document_attachment_cancellations WHERE project_id=? AND candidate_id=?",
                (expected.project_id, candidate_id),
            ).fetchone()
            is None,
            "candidate-was-cancelled",
        )

        attachment = _one(
            connection,
            "SELECT * FROM document_attachment_assertions WHERE project_id=? AND attachment_id=?",
            (expected.project_id, expected.attachment_id),
            "committed-attachment-unavailable",
        )
        _require(
            attachment["candidate_id"] == candidate_id
            and attachment["command_id"] == expected.command_id
            and attachment["document_revision_id"] == expected.document_revision_id
            and attachment["object_sha256"] == expected.source_sha256
            and attachment["confirmation_sha256"] == candidate["candidate_sha256"]
            and attachment["actor_id"] == candidate["actor_id"] == candidate["operation_actor_id"]
            and tuple(
                attachment[key]
                for key in (
                    "source_assertion_revision_id",
                    "work_id",
                    "work_revision_id",
                    "version_id",
                    "version_revision_id",
                )
            )
            == selection,
            "committed-attachment-binding-mismatch",
        )
        document = _one(
            connection,
            "SELECT d.object_sha256,r.aggregate_id,r.aggregate_kind,r.rights_status,r.revision "
            "FROM documents d JOIN aggregate_revisions r "
            "ON r.project_id=d.project_id AND r.revision_id=d.revision_id "
            "WHERE d.project_id=? AND d.revision_id=?",
            (expected.project_id, expected.document_revision_id),
            "document-revision-unavailable",
        )
        _require(
            document["object_sha256"] == expected.source_sha256
            and document["aggregate_id"] == attachment["document_id"]
            and document["aggregate_kind"] == "document"
            and document["rights_status"] == "allowed"
            and document["revision"] == 0,
            "document-revision-binding-mismatch",
        )

        provenance = _one(
            connection,
            "SELECT p.project_id,p.revision_id,p.event_type,p.actor_type,p.actor_id,p.occurred_at,"
            "p.record_sha256,o.project_id AS outbox_project_id,o.revision_id AS outbox_revision_id,"
            "o.event_type AS outbox_event_type,o.record_sha256 AS outbox_record_sha256,"
            "o.idempotency_key FROM provenance_events p JOIN outbox_events o "
            "ON o.outbox_id=? WHERE p.event_id=?",
            (attachment["outbox_id"], attachment["provenance_event_id"]),
            "attachment-provenance-unavailable",
        )
        _require_provenance_binding(provenance, attachment, expected)
        dependencies = connection.execute(
            "SELECT dependency_kind,dependency_revision_id FROM material_dependencies "
            "WHERE project_id=? AND output_revision_id=?",
            (expected.project_id, expected.document_revision_id),
        ).fetchall()
        _require(
            len(dependencies) == 4
            and {(row[0], row[1]) for row in dependencies}
            == {
                ("source-revision", expected.source_assertion_revision_id),
                ("source-revision", expected.work_revision_id),
                ("source-revision", expected.version_revision_id),
                ("human-decision", attachment["rights_policy_revision_id"]),
            },
            "document-dependencies-mismatch",
        )

        subject = _one(
            connection,
            "SELECT subject_sha256,copy_location,resource_class,source_assertion_revision_id "
            "FROM rights_policy_subjects WHERE project_id=? AND copy_id=?",
            (expected.project_id, candidate_id),
            "attachment-rights-subject-unavailable",
        )
        _require(
            subject["subject_sha256"] == attachment["subject_sha256"]
            and subject["copy_location"] == "local-project-object"
            and subject["resource_class"] == "full-text"
            and subject["source_assertion_revision_id"] == expected.source_assertion_revision_id,
            "attachment-rights-subject-mismatch",
        )
        policy_row = _one(
            connection,
            "SELECT revision_id,subject_sha256,policy_json FROM rights_policy_revisions "
            "WHERE project_id=? AND revision_id=?",
            (expected.project_id, attachment["rights_policy_revision_id"]),
            "attachment-rights-policy-unavailable",
        )
        current = _one(
            connection,
            "SELECT revision_id FROM rights_policy_revisions WHERE project_id=? AND subject_sha256=? "
            "ORDER BY revision_number DESC LIMIT 1",
            (expected.project_id, subject["subject_sha256"]),
            "attachment-current-rights-unavailable",
        )
        policy = RightsPolicyRevision.model_validate_json(str(policy_row["policy_json"]))
        _require(
            current["revision_id"] == policy.revision_id == policy_row["revision_id"]
            and policy_row["subject_sha256"] == subject["subject_sha256"]
            and policy.subject.project_id == expected.project_id
            and policy.subject.source_assertion_revision_id == expected.source_assertion_revision_id
            and policy.subject.copy_id == candidate_id
            and policy.subject.copy_location == "local-project-object"
            and policy.subject.resource_class == "full-text",
            "attachment-rights-policy-mismatch",
        )
        _require(
            len(policy.permissions) == 2
            and {(item.use.action, item.use.purpose, item.use.destination_kind) for item in policy.permissions}
            == {
                ("store", "document-attachment", "local-project"),
                ("inspect", "document-analysis", "local-project"),
            }
            and all(
                item.value == "permitted"
                and item.basis == "researcher-confirmed"
                and item.confidence == "confirmed"
                and item.asserted_by_actor_id == attachment["actor_id"]
                and item.grantee_actor_id == attachment["actor_id"]
                and item.evidence_revision_ids == (expected.source_assertion_revision_id,)
                and item.use.provider is None
                and item.use.region is None
                and item.use.share_group is None
                for item in policy.permissions
            ),
            "attachment-rights-not-project-local-only",
        )

        obj = _one(
            connection,
            "SELECT object_sha256,byte_length,media_type,protection_profile,retention_class,"
            "creation_source,storage_state,envelope_version,key_version,wrapped_key,wrap_nonce,"
            "ciphertext_byte_length FROM object_records WHERE project_id=? AND object_sha256=?",
            (expected.project_id, expected.source_sha256),
            "attachment-object-unavailable",
        )
        _require(
            obj["object_sha256"] == expected.source_sha256
            and obj["byte_length"] == source_length
            and obj["media_type"] == "text/plain"
            and obj["protection_profile"] == "project-encrypted-v1"
            and obj["retention_class"] == "project-lifetime"
            and obj["creation_source"] == "local-import"
            and obj["storage_state"] == "available"
            and obj["envelope_version"] == "secretstream-xchacha20poly1305-v1"
            and obj["key_version"] is not None
            and obj["wrapped_key"] is not None
            and obj["wrap_nonce"] is not None
            and obj["ciphertext_byte_length"] > source_length,
            "attachment-object-not-encrypted",
        )
        return {
            "candidateId": candidate_id,
            "attachmentId": str(attachment["attachment_id"]),
            "documentRevisionId": str(attachment["document_revision_id"]),
            "rightsPolicyRevisionId": str(attachment["rights_policy_revision_id"]),
            "provenanceEventId": str(attachment["provenance_event_id"]),
            "outboxId": str(attachment["outbox_id"]),
            "objectSha256": str(obj["object_sha256"]),
            "ciphertextByteLength": str(obj["ciphertext_byte_length"]),
        }


def verify(fixture_root: Path, expected: Expected) -> dict[str, object]:
    ids = (
        expected.work_id,
        expected.work_revision_id,
        expected.version_id,
        expected.version_revision_id,
        expected.source_assertion_revision_id,
        expected.operation_id,
        expected.command_id,
        expected.attachment_id,
        expected.document_revision_id,
    )
    _require(_project_id(expected.project_id) and all(is_uuid_v7(value) for value in ids), "expected-identity-invalid")
    _require(expected.candidate_id is None or is_uuid_v7(expected.candidate_id), "expected-candidate-invalid")
    _require(
        _SHA256.fullmatch(expected.source_sha256) is not None and expected.source_sha256 == _SOURCE_SHA256,
        "expected-source-digest-invalid",
    )
    scratch = _directory(ROOT / "artifacts/tmp", "fixture-scratch-unavailable")
    _require(fixture_root.is_absolute() and fixture_root.parent == scratch, "fixture-root-outside-ignored-scratch")
    _require(fixture_root.name.startswith("directory-dialog-"), "fixture-root-name-invalid")
    _directory(fixture_root, "fixture-root-unavailable")
    project = _directory(fixture_root / "projects/document-drop-project", "fixture-project-unavailable")
    vault = _directory(fixture_root / "vault", "fixture-vault-unavailable")
    source = _regular(fixture_root / "temporary" / _SOURCE_NAME, "fixture-source-unavailable")
    database = _regular(project / "state/project.sqlite3", "fixture-database-unavailable")
    source_bytes = source.read_bytes()
    _require(hashlib.sha256(source_bytes).hexdigest() == expected.source_sha256, "fixture-source-digest-mismatch")
    with database.open("rb") as stream:
        header = stream.read(16)
    _require(len(header) == 16 and header != _SQLITE_HEADER, "fixture-database-not-protected")

    configure_protected_database_provider(create_windows_database_key_provider(vault))
    first = _inspect_database(database, expected, len(source_bytes))
    reopened = _inspect_database(database, expected, len(source_bytes))
    _require(first == reopened, "attachment-reopen-drift")

    opaque = hmac.new(
        expected.project_id.encode("ascii"), expected.source_sha256.encode("ascii"), hashlib.sha256
    ).hexdigest()
    blob = _regular(
        project / "objects" / opaque[:2] / opaque[2:4] / f"{opaque}.blob", "encrypted-project-object-unavailable"
    )
    _require(
        blob.stat().st_size == int(first["ciphertextByteLength"]) <= len(source_bytes) + 4096,
        "encrypted-object-length-mismatch",
    )
    with blob.open("rb") as stream:
        ciphertext = stream.read()
    _require(
        ciphertext.startswith(b"ROO1") and ciphertext != source_bytes and source_bytes not in ciphertext,
        "encrypted-project-object-invalid",
    )
    return {
        "schemaVersion": "1.0",
        "status": "passed",
        "projectId": expected.project_id,
        "workId": expected.work_id,
        "versionId": expected.version_id,
        "sourceAssertionRevisionId": expected.source_assertion_revision_id,
        "operationId": expected.operation_id,
        "commandId": expected.command_id,
        **first,
        "ciphertextSha256": hashlib.sha256(ciphertext).hexdigest(),
        "reopenedStatus": "committed",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture-root", type=Path, required=True)
    for name in (
        "project-id",
        "work-id",
        "work-revision-id",
        "version-id",
        "version-revision-id",
        "source-assertion-revision-id",
        "source-sha256",
        "operation-id",
        "command-id",
        "attachment-id",
        "document-revision-id",
    ):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--candidate-id")
    args = parser.parse_args()
    expected = Expected(
        project_id=args.project_id,
        work_id=args.work_id,
        work_revision_id=args.work_revision_id,
        version_id=args.version_id,
        version_revision_id=args.version_revision_id,
        source_assertion_revision_id=args.source_assertion_revision_id,
        source_sha256=args.source_sha256,
        operation_id=args.operation_id,
        command_id=args.command_id,
        attachment_id=args.attachment_id,
        document_revision_id=args.document_revision_id,
        candidate_id=args.candidate_id,
    )
    try:
        result = verify(args.fixture_root, expected)
    except Exception as error:
        # Keep untrusted database and local path details out of retained output.
        code = str(error) if isinstance(error, FixtureFailure) else "fixture-verification-error"
        result = {"schemaVersion": "1.0", "status": "failed", "failureCode": code}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
