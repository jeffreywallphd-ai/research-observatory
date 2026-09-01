"""Add dependency impact, stale-state, and propagation audit authority."""

from __future__ import annotations

from typing import Any, cast

from alembic.operations import Operations
from sqlalchemy import text

revision = "0010_dependency_impacts"
down_revision = "0009_material_dependencies"
source_schema_version = 9
target_schema_version = 10

TARGET_SCHEMA_SHA256 = "14806bb190c892b15a2f7804765c8e8617c47e5369eb3c2744da4d73ed0fdbd9"
TARGET_PROFILE_SHA256 = "7ef1523ac2b4e2dd60843bc055d3b6e3f764260fecd92cc2eff45262b429ba9b"

IMPACT_MIGRATION_STEPS = (
    "dependency-impact-authority-create",
    "metadata-v9-authority-drop",
    "metadata-v9-rename",
    "metadata-v10-create",
    "metadata-v10-copy",
    "metadata-v9-drop",
    "migration-history-insert",
    "user-version-advance",
)


def _migration_step_completed(_step: str) -> None:
    """Private deterministic failpoint seam for transactional rollback proof."""


def apply(operations: Operations, parameters: dict[str, Any]) -> None:
    """Apply the exact v9-to-v10 DDL inside the caller-owned transaction."""

    if parameters.get("targetSchemaSha256") != TARGET_SCHEMA_SHA256:
        raise ValueError("migration target schema authority mismatch")
    if parameters.get("targetProfileSha256") != TARGET_PROFILE_SHA256:
        raise ValueError("migration target profile authority mismatch")
    bind = operations.get_bind()
    if bind is None:
        raise ValueError("online migration connection is required")
    for statement in parameters["dependencyImpactAuthority"]:
        operations.execute(statement)
    _migration_step_completed("dependency-impact-authority-create")

    operations.execute("DROP TRIGGER schema_metadata_no_update")
    operations.execute("DROP TRIGGER schema_metadata_no_delete")
    _migration_step_completed("metadata-v9-authority-drop")
    operations.rename_table("schema_metadata", "schema_metadata_v9")
    _migration_step_completed("metadata-v9-rename")
    operations.execute(parameters["schemaMetadataDdl"])
    _migration_step_completed("metadata-v10-create")
    bind.execute(
        text(
            """
            INSERT INTO schema_metadata (
                singleton, schema_version, database_profile, application_id,
                profile_sha256, schema_sha256, created_at
            )
            SELECT singleton, 10, database_profile, application_id,
                   :profile_sha256, :schema_sha256, created_at
            FROM schema_metadata_v9
            """
        ),
        {"profile_sha256": TARGET_PROFILE_SHA256, "schema_sha256": TARGET_SCHEMA_SHA256},
    )
    _migration_step_completed("metadata-v10-copy")
    operations.drop_table("schema_metadata_v9")
    _migration_step_completed("metadata-v9-drop")
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
                :migration_id, 9, 10, :applied_at, :backup_manifest_sha256,
                :source_schema_sha256, :target_schema_sha256, 'alembic-1.18.5'
            )
            """
        ),
        parameters,
    )
    _migration_step_completed("migration-history-insert")
    operations.execute("PRAGMA user_version=10")
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
