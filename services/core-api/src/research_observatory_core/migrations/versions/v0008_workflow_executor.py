"""Add the durable local workflow queue and advance the local schema to v8."""

from __future__ import annotations

from typing import Any, cast

from alembic.operations import Operations
from sqlalchemy import text

revision = "0008_workflow_executor"
down_revision = "0007_provenance_ledger"
source_schema_version = 7
target_schema_version = 8

# These reviewed fingerprints are synchronized with storage.py after the exact
# DDL is assembled. Static values deliberately make migration authority fail
# closed if either side changes independently.
TARGET_SCHEMA_SHA256 = "1f5d94ac9a17732c72405fdda945df75d1558c444eaf7b6a5dcf286a50443b04"
TARGET_PROFILE_SHA256 = "c55bb71d5c9553de5d104ae591fee39e06407b479f9f3583b8f1ce42db8ecba7"

MATERIAL_MIGRATION_STEPS = (
    "workflow-authority-create",
    "metadata-v7-authority-drop",
    "metadata-v7-rename",
    "metadata-v8-create",
    "metadata-v8-copy",
    "metadata-v7-drop",
    "migration-history-insert",
    "user-version-advance",
)


def _migration_step_completed(_step: str) -> None:
    """Private deterministic failpoint seam for transactional rollback proof."""


def apply(operations: Operations, parameters: dict[str, Any]) -> None:
    """Apply the exact v7-to-v8 DDL inside the caller-owned transaction."""

    if parameters.get("targetSchemaSha256") != TARGET_SCHEMA_SHA256:
        raise ValueError("migration target schema authority mismatch")
    if parameters.get("targetProfileSha256") != TARGET_PROFILE_SHA256:
        raise ValueError("migration target profile authority mismatch")
    bind = operations.get_bind()
    if bind is None:
        raise ValueError("online migration connection is required")
    for statement in parameters["workflowAuthority"]:
        operations.execute(statement)
    _migration_step_completed("workflow-authority-create")

    operations.execute("DROP TRIGGER schema_metadata_no_update")
    operations.execute("DROP TRIGGER schema_metadata_no_delete")
    _migration_step_completed("metadata-v7-authority-drop")
    operations.rename_table("schema_metadata", "schema_metadata_v7")
    _migration_step_completed("metadata-v7-rename")
    operations.execute(parameters["schemaMetadataDdl"])
    _migration_step_completed("metadata-v8-create")
    bind.execute(
        text(
            """
            INSERT INTO schema_metadata (
                singleton, schema_version, database_profile, application_id,
                profile_sha256, schema_sha256, created_at
            )
            SELECT singleton, 8, database_profile, application_id,
                   :profile_sha256, :schema_sha256, created_at
            FROM schema_metadata_v7
            """
        ),
        {"profile_sha256": TARGET_PROFILE_SHA256, "schema_sha256": TARGET_SCHEMA_SHA256},
    )
    _migration_step_completed("metadata-v8-copy")
    operations.drop_table("schema_metadata_v7")
    _migration_step_completed("metadata-v7-drop")
    for statement in parameters["schemaMetadataTriggers"]:
        operations.execute(statement)
    bind.execute(
        text(
            """
            INSERT INTO schema_migrations (
                migration_id, from_schema_version, to_schema_version, applied_at,
                backup_manifest_sha256, source_schema_sha256, target_schema_sha256,
                migration_tool
            ) VALUES (
                :migration_id, 7, 8, :applied_at, :backup_manifest_sha256,
                :source_schema_sha256, :target_schema_sha256, 'alembic-1.18.5'
            )
            """
        ),
        parameters,
    )
    _migration_step_completed("migration-history-insert")
    operations.execute("PRAGMA user_version=8")
    _migration_step_completed("user-version-advance")


def upgrade() -> None:
    """Standard Alembic entry point; the governed runner supplies parameters."""

    from alembic import op

    parameters = op.get_context().opts.get("research_observatory_parameters")
    if not isinstance(parameters, dict):
        raise ValueError("governed migration parameters are required")
    apply(cast(Operations, op), parameters)


def downgrade() -> None:
    """Research Observatory schema migrations are deliberately forward-only."""

    raise NotImplementedError("forward-only migration; restore the verified pre-migration backup")
