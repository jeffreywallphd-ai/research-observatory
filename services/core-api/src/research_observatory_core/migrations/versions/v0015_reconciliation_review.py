"""Add sealed Work membership and review history, preserving every v14 fact."""

from __future__ import annotations

import hashlib
import json
from typing import Any, cast

from alembic.operations import Operations
from sqlalchemy import text

revision = "0015_reconciliation_review"
down_revision = "0014_scholarly_reconciliation"
source_schema_version = 14
target_schema_version = 15
TARGET_SCHEMA_SHA256 = "4f200959ff5c3d51e589d7d4f4818bc2a85b6ba085f9164979b7fcc8cf7ac178"
TARGET_PROFILE_SHA256 = "59e35e778a137c97a47f474bb0b4abed30fb3dbbbace86677865a28aa2a59c60"
MATERIAL_MIGRATION_STEPS = (
    "review-authority-create",
    "membership-backfill-row",
    "membership-backfill-complete",
    "metadata-v14-authority-drop",
    "metadata-v14-rename",
    "metadata-v15-create",
    "metadata-v15-copy",
    "metadata-v14-drop",
    "migration-history-insert",
    "user-version-advance",
)


def _migration_step_completed(_step: str) -> None:
    """Private deterministic failpoint for transactional interruption tests."""


def apply(operations: Operations, parameters: dict[str, Any]) -> None:
    if parameters.get("targetSchemaSha256") != TARGET_SCHEMA_SHA256:
        raise ValueError("migration target schema authority mismatch")
    if parameters.get("targetProfileSha256") != TARGET_PROFILE_SHA256:
        raise ValueError("migration target profile authority mismatch")
    bind = operations.get_bind()
    if bind is None:
        raise ValueError("online migration connection is required")
    for statement in parameters["reviewAuthority"]:
        operations.execute(statement)
    _migration_step_completed("review-authority-create")

    # Stream exact canonical sequence, never UUID order or today's full members.
    # Only the current Work prefix is held in memory. No canonical fact is edited.
    previous_key, previous_revision = None, None
    members: list[str] = []
    rows = bind.execute(
        text(
            "SELECT w.project_id,w.work_id,w.revision_id,w.previous_revision_id,w.assertion_revision_id "
            "FROM reconciliation_work_revisions w JOIN aggregate_revisions r ON r.revision_id=w.revision_id "
            "ORDER BY w.project_id,w.work_id,r.revision"
        )
    )
    for project, work, current, predecessor, assertion in rows:
        if previous_key != (project, work):
            previous_key, previous_revision, members = (project, work), None, []
        if predecessor != previous_revision or assertion in members:
            raise ValueError("migration legacy membership chain invalid")
        members.append(assertion)
        ordered_members = sorted(members)
        state = {
            "schemaVersion": "1.0",
            "workId": work,
            "revisionId": current,
            "previousRevisionId": predecessor,
            "disposition": "active",
            "aliasTarget": None,
            "assertionRevisionIds": ordered_members,
            "decisionRevisionId": None,
        }
        digest = hashlib.sha256(
            json.dumps(state, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        bind.execute(
            text(
                "INSERT INTO reconciliation_work_states "
                "(revision_id,project_id,work_id,previous_revision_id,disposition) "
                "VALUES (:revision,:project,:work,:previous,'active')"
            ),
            {"revision": current, "project": project, "work": work, "previous": predecessor},
        )
        for ordinal, member in enumerate(ordered_members, 1):
            bind.execute(
                text("INSERT INTO reconciliation_work_members VALUES (:revision,:project,:ordinal,:assertion)"),
                {"revision": current, "project": project, "ordinal": ordinal, "assertion": member},
            )
        bind.execute(
            text("INSERT INTO reconciliation_work_seals VALUES (:revision,:project,:count,:digest)"),
            {"revision": current, "project": project, "count": len(members), "digest": digest},
        )
        previous_revision = current
        _migration_step_completed("membership-backfill-row")
    _migration_step_completed("membership-backfill-complete")

    operations.execute("DROP TRIGGER schema_metadata_no_update")
    operations.execute("DROP TRIGGER schema_metadata_no_delete")
    _migration_step_completed("metadata-v14-authority-drop")
    operations.rename_table("schema_metadata", "schema_metadata_v14")
    _migration_step_completed("metadata-v14-rename")
    operations.execute(parameters["schemaMetadataDdl"])
    _migration_step_completed("metadata-v15-create")
    bind.execute(
        text(
            "INSERT INTO schema_metadata SELECT singleton,15,database_profile,application_id,"
            ":profile,:schema,created_at FROM schema_metadata_v14"
        ),
        {"profile": TARGET_PROFILE_SHA256, "schema": TARGET_SCHEMA_SHA256},
    )
    _migration_step_completed("metadata-v15-copy")
    operations.drop_table("schema_metadata_v14")
    _migration_step_completed("metadata-v14-drop")
    for statement in parameters["schemaMetadataTriggers"]:
        operations.execute(statement)
    bind.execute(
        text(
            "INSERT INTO schema_migrations (migration_id,from_schema_version,to_schema_version,applied_at,"
            "backup_manifest_sha256,source_schema_sha256,target_schema_sha256,migration_tool) "
            "VALUES (:migration_id,14,15,:applied_at,:backup_manifest_sha256,:source_schema_sha256,"
            ":target_schema_sha256,'alembic-1.18.5')"
        ),
        parameters,
    )
    _migration_step_completed("migration-history-insert")
    operations.execute("PRAGMA user_version=15")
    _migration_step_completed("user-version-advance")


def upgrade() -> None:
    from alembic import op

    parameters = op.get_context().opts.get("research_observatory_parameters")
    if not isinstance(parameters, dict):
        raise ValueError("governed migration parameters are required")
    apply(cast(Operations, op), parameters)


def downgrade() -> None:
    raise NotImplementedError("forward-only migration; restore the verified pre-migration backup")
