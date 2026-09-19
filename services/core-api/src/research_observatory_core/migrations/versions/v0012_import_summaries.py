"""Add fixed-draft inspection projections; never fabricate historical results."""

from __future__ import annotations

from typing import Any, cast

from alembic.operations import Operations
from sqlalchemy import text

revision = "0012_import_summaries"
down_revision = "0011_import_previews"
source_schema_version = 11
target_schema_version = 12
TARGET_SCHEMA_SHA256 = "42a9886d0b9d132071cebe3170d12b46a048148f9c69dcf624178d4f281840fa"
TARGET_PROFILE_SHA256 = "9d6ac8532068f3271c42140525a6c106208f92ca6f8362c36eee4e25b02d863f"
MATERIAL_MIGRATION_STEPS = (
    "import-summary-authority-create",
    "metadata-v11-authority-drop",
    "metadata-v11-rename",
    "metadata-v12-create",
    "metadata-v12-copy",
    "metadata-v11-drop",
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
    for statement in parameters["importSummaryAuthority"]:
        operations.execute(statement)
    _migration_step_completed("import-summary-authority-create")
    operations.execute("DROP TRIGGER schema_metadata_no_update")
    operations.execute("DROP TRIGGER schema_metadata_no_delete")
    _migration_step_completed("metadata-v11-authority-drop")
    operations.rename_table("schema_metadata", "schema_metadata_v11")
    _migration_step_completed("metadata-v11-rename")
    operations.execute(parameters["schemaMetadataDdl"])
    _migration_step_completed("metadata-v12-create")
    bind.execute(
        text(
            "INSERT INTO schema_metadata SELECT singleton, 12, database_profile, application_id, "
            ":profile, :schema, created_at FROM schema_metadata_v11"
        ),
        {"profile": TARGET_PROFILE_SHA256, "schema": TARGET_SCHEMA_SHA256},
    )
    _migration_step_completed("metadata-v12-copy")
    operations.drop_table("schema_metadata_v11")
    _migration_step_completed("metadata-v11-drop")
    for statement in parameters["schemaMetadataTriggers"]:
        operations.execute(statement)
    bind.execute(
        text(
            "INSERT INTO schema_migrations (migration_id, from_schema_version, to_schema_version, applied_at, "
            "backup_manifest_sha256, source_schema_sha256, target_schema_sha256, migration_tool) "
            "VALUES (:migration_id, 11, 12, :applied_at, :backup_manifest_sha256, :source_schema_sha256, "
            ":target_schema_sha256, 'alembic-1.18.5')"
        ),
        parameters,
    )
    _migration_step_completed("migration-history-insert")
    operations.execute("PRAGMA user_version=12")
    _migration_step_completed("user-version-advance")


def upgrade() -> None:
    from alembic import op

    parameters = op.get_context().opts.get("research_observatory_parameters")
    if not isinstance(parameters, dict):
        raise ValueError("governed migration parameters are required")
    apply(cast(Operations, op), parameters)


def downgrade() -> None:
    raise NotImplementedError("forward-only migration; restore the verified pre-migration backup")
