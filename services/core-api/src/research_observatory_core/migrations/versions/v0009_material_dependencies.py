"""Add material dependency authority and advance the local schema to v9."""

from __future__ import annotations

from typing import Any, cast

from alembic.operations import Operations
from sqlalchemy import text

revision = "0009_material_dependencies"
down_revision = "0008_workflow_executor"
source_schema_version = 8
target_schema_version = 9

TARGET_SCHEMA_SHA256 = "a1f8087eda44532e269d19adfc6ee90591e00ca7a69be0ddab0db7c84744d2cc"
TARGET_PROFILE_SHA256 = "4761d833e7d8a25e969e79ea9c740f501ae2a4c119b03f38ffb5d06bd1e46e76"

MATERIAL_MIGRATION_STEPS = (
    "dependency-authority-create",
    "legacy-coverage-backfill",
    "metadata-v8-authority-drop",
    "metadata-v8-rename",
    "metadata-v9-create",
    "metadata-v9-copy",
    "metadata-v8-drop",
    "migration-history-insert",
    "user-version-advance",
)


def _migration_step_completed(_step: str) -> None:
    """Private deterministic failpoint seam for transactional rollback proof."""


def apply(operations: Operations, parameters: dict[str, Any]) -> None:
    """Apply the exact v8-to-v9 DDL inside the caller-owned transaction."""

    if parameters.get("targetSchemaSha256") != TARGET_SCHEMA_SHA256:
        raise ValueError("migration target schema authority mismatch")
    if parameters.get("targetProfileSha256") != TARGET_PROFILE_SHA256:
        raise ValueError("migration target profile authority mismatch")
    bind = operations.get_bind()
    if bind is None:
        raise ValueError("online migration connection is required")
    for statement in parameters["materialDependencyAuthority"]:
        operations.execute(statement)
    _migration_step_completed("dependency-authority-create")
    operations.execute(
        """
        INSERT INTO material_dependency_outputs (
            output_revision_id, project_id, coverage, registration_event_id, registered_at
        )
        SELECT revision_id, project_id, 'legacy-unreported', NULL, NULL
          FROM aggregate_revisions
        """
    )
    _migration_step_completed("legacy-coverage-backfill")

    operations.execute("DROP TRIGGER schema_metadata_no_update")
    operations.execute("DROP TRIGGER schema_metadata_no_delete")
    _migration_step_completed("metadata-v8-authority-drop")
    operations.rename_table("schema_metadata", "schema_metadata_v8")
    _migration_step_completed("metadata-v8-rename")
    operations.execute(parameters["schemaMetadataDdl"])
    _migration_step_completed("metadata-v9-create")
    bind.execute(
        text(
            """
            INSERT INTO schema_metadata (
                singleton, schema_version, database_profile, application_id,
                profile_sha256, schema_sha256, created_at
            )
            SELECT singleton, 9, database_profile, application_id,
                   :profile_sha256, :schema_sha256, created_at
            FROM schema_metadata_v8
            """
        ),
        {"profile_sha256": TARGET_PROFILE_SHA256, "schema_sha256": TARGET_SCHEMA_SHA256},
    )
    _migration_step_completed("metadata-v9-copy")
    operations.drop_table("schema_metadata_v8")
    _migration_step_completed("metadata-v8-drop")
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
                :migration_id, 8, 9, :applied_at, :backup_manifest_sha256,
                :source_schema_sha256, :target_schema_sha256, 'alembic-1.18.5'
            )
            """
        ),
        parameters,
    )
    _migration_step_completed("migration-history-insert")
    operations.execute("PRAGMA user_version=9")
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
