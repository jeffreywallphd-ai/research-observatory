"""Add exact scholarly reconciliation without rewriting source assertions or prior records."""

from __future__ import annotations

from typing import Any, cast

from alembic.operations import Operations
from sqlalchemy import text

revision = "0014_scholarly_reconciliation"
down_revision = "0013_import_commits"
source_schema_version = 13
target_schema_version = 14
TARGET_SCHEMA_SHA256 = "4b8b87b1024b855fa1eee932b41b9d4a8d8492823b17968eb3d17eda24b5ccb2"
TARGET_PROFILE_SHA256 = "49ee17767e8a0652a381925181f3a6e38722b9635f15f704c22b648f0e981a89"
MATERIAL_MIGRATION_STEPS = (
    "reconciliation-authority-create",
    "metadata-v13-authority-drop",
    "metadata-v13-rename",
    "metadata-v14-create",
    "metadata-v14-copy",
    "metadata-v13-drop",
    "migration-history-insert",
    "user-version-advance",
)


def _migration_step_completed(_step: str) -> None:
    """Private deterministic failpoint seam for transactional rollback proof."""


def apply(operations: Operations, parameters: dict[str, Any]) -> None:
    if parameters.get("targetSchemaSha256") != TARGET_SCHEMA_SHA256:
        raise ValueError("migration target schema authority mismatch")
    if parameters.get("targetProfileSha256") != TARGET_PROFILE_SHA256:
        raise ValueError("migration target profile authority mismatch")
    bind = operations.get_bind()
    if bind is None:
        raise ValueError("online migration connection is required")
    for statement in parameters["reconciliationAuthority"]:
        operations.execute(statement)
    _migration_step_completed("reconciliation-authority-create")
    operations.execute("DROP TRIGGER schema_metadata_no_update")
    operations.execute("DROP TRIGGER schema_metadata_no_delete")
    _migration_step_completed("metadata-v13-authority-drop")
    operations.rename_table("schema_metadata", "schema_metadata_v13")
    _migration_step_completed("metadata-v13-rename")
    operations.execute(parameters["schemaMetadataDdl"])
    _migration_step_completed("metadata-v14-create")
    bind.execute(
        text(
            "INSERT INTO schema_metadata SELECT singleton, 14, database_profile, application_id, "
            ":profile, :schema, created_at FROM schema_metadata_v13"
        ),
        {"profile": TARGET_PROFILE_SHA256, "schema": TARGET_SCHEMA_SHA256},
    )
    _migration_step_completed("metadata-v14-copy")
    operations.drop_table("schema_metadata_v13")
    _migration_step_completed("metadata-v13-drop")
    for statement in parameters["schemaMetadataTriggers"]:
        operations.execute(statement)
    bind.execute(
        text(
            "INSERT INTO schema_migrations (migration_id, from_schema_version, to_schema_version, applied_at, "
            "backup_manifest_sha256, source_schema_sha256, target_schema_sha256, migration_tool) "
            "VALUES (:migration_id, 13, 14, :applied_at, :backup_manifest_sha256, :source_schema_sha256, "
            ":target_schema_sha256, 'alembic-1.18.5')"
        ),
        parameters,
    )
    _migration_step_completed("migration-history-insert")
    operations.execute("PRAGMA user_version=14")
    _migration_step_completed("user-version-advance")


def upgrade() -> None:
    from alembic import op

    parameters = op.get_context().opts.get("research_observatory_parameters")
    if not isinstance(parameters, dict):
        raise ValueError("governed migration parameters are required")
    apply(cast(Operations, op), parameters)


def downgrade() -> None:
    raise NotImplementedError("forward-only migration; restore the verified pre-migration backup")
