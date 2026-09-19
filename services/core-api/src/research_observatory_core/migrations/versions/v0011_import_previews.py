"""Add protected, append-only import-preview authority."""

from __future__ import annotations

from typing import Any, cast

from alembic.operations import Operations
from sqlalchemy import text

revision = "0011_import_previews"
down_revision = "0010_dependency_impacts"
source_schema_version = 10
target_schema_version = 11

TARGET_SCHEMA_SHA256 = "33f607dea1a2b20e0d1b451cafdbcaa5d1bb58e1b91499525adad40bc5a8f5c0"
TARGET_PROFILE_SHA256 = "c751146ae0301c14716e8fa1f0c29b9929a1dd4caa9a3b9fd6d98595a7888c91"

MATERIAL_MIGRATION_STEPS = (
    "import-preview-authority-create",
    "metadata-v10-authority-drop",
    "metadata-v10-rename",
    "metadata-v11-create",
    "metadata-v11-copy",
    "metadata-v10-drop",
    "migration-history-insert",
    "user-version-advance",
)


def _migration_step_completed(_step: str) -> None:
    """Private deterministic failpoint seam for transactional rollback proof."""


def apply(operations: Operations, parameters: dict[str, Any]) -> None:
    """Apply the exact v10-to-v11 DDL inside the caller-owned transaction."""

    if parameters.get("targetSchemaSha256") != TARGET_SCHEMA_SHA256:
        raise ValueError("migration target schema authority mismatch")
    if parameters.get("targetProfileSha256") != TARGET_PROFILE_SHA256:
        raise ValueError("migration target profile authority mismatch")
    bind = operations.get_bind()
    if bind is None:
        raise ValueError("online migration connection is required")
    for statement in parameters["importPreviewAuthority"]:
        operations.execute(statement)
    _migration_step_completed("import-preview-authority-create")

    operations.execute("DROP TRIGGER schema_metadata_no_update")
    operations.execute("DROP TRIGGER schema_metadata_no_delete")
    _migration_step_completed("metadata-v10-authority-drop")
    operations.rename_table("schema_metadata", "schema_metadata_v10")
    _migration_step_completed("metadata-v10-rename")
    operations.execute(parameters["schemaMetadataDdl"])
    _migration_step_completed("metadata-v11-create")
    bind.execute(
        text(
            """
            INSERT INTO schema_metadata (
                singleton, schema_version, database_profile, application_id,
                profile_sha256, schema_sha256, created_at
            )
            SELECT singleton, 11, database_profile, application_id,
                   :profile_sha256, :schema_sha256, created_at
            FROM schema_metadata_v10
            """
        ),
        {"profile_sha256": TARGET_PROFILE_SHA256, "schema_sha256": TARGET_SCHEMA_SHA256},
    )
    _migration_step_completed("metadata-v11-copy")
    operations.drop_table("schema_metadata_v10")
    _migration_step_completed("metadata-v10-drop")
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
                :migration_id, 10, 11, :applied_at, :backup_manifest_sha256,
                :source_schema_sha256, :target_schema_sha256, 'alembic-1.18.5'
            )
            """
        ),
        parameters,
    )
    _migration_step_completed("migration-history-insert")
    operations.execute("PRAGMA user_version=11")
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
