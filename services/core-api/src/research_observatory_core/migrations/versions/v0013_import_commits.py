"""Add source assertions and complete import manifests; never fabricate historical results."""

from __future__ import annotations

from typing import Any, cast

from alembic.operations import Operations
from sqlalchemy import text

revision = "0013_import_commits"
down_revision = "0012_import_summaries"
source_schema_version = 12
target_schema_version = 13
TARGET_SCHEMA_SHA256 = "13e54503130f8e40036beed26659c5bda2787928c56444987619366e4310b064"
TARGET_PROFILE_SHA256 = "9ef28bc5d42188c63b50f31eb714c69d040a685311c1dcc5aaf1e89faec42e0b"
MATERIAL_MIGRATION_STEPS = (
    "import-commit-authority-create",
    "metadata-v12-authority-drop",
    "metadata-v12-rename",
    "metadata-v13-create",
    "metadata-v13-copy",
    "metadata-v12-drop",
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
    for statement in parameters["importCommitAuthority"]:
        operations.execute(statement)
    _migration_step_completed("import-commit-authority-create")
    operations.execute("DROP TRIGGER schema_metadata_no_update")
    operations.execute("DROP TRIGGER schema_metadata_no_delete")
    _migration_step_completed("metadata-v12-authority-drop")
    operations.rename_table("schema_metadata", "schema_metadata_v12")
    _migration_step_completed("metadata-v12-rename")
    operations.execute(parameters["schemaMetadataDdl"])
    _migration_step_completed("metadata-v13-create")
    bind.execute(
        text(
            "INSERT INTO schema_metadata SELECT singleton, 13, database_profile, application_id, "
            ":profile, :schema, created_at FROM schema_metadata_v12"
        ),
        {"profile": TARGET_PROFILE_SHA256, "schema": TARGET_SCHEMA_SHA256},
    )
    _migration_step_completed("metadata-v13-copy")
    operations.drop_table("schema_metadata_v12")
    _migration_step_completed("metadata-v12-drop")
    for statement in parameters["schemaMetadataTriggers"]:
        operations.execute(statement)
    bind.execute(
        text(
            "INSERT INTO schema_migrations (migration_id, from_schema_version, to_schema_version, applied_at, "
            "backup_manifest_sha256, source_schema_sha256, target_schema_sha256, migration_tool) "
            "VALUES (:migration_id, 12, 13, :applied_at, :backup_manifest_sha256, :source_schema_sha256, "
            ":target_schema_sha256, 'alembic-1.18.5')"
        ),
        parameters,
    )
    _migration_step_completed("migration-history-insert")
    operations.execute("PRAGMA user_version=13")
    _migration_step_completed("user-version-advance")


def upgrade() -> None:
    from alembic import op

    parameters = op.get_context().opts.get("research_observatory_parameters")
    if not isinstance(parameters, dict):
        raise ValueError("governed migration parameters are required")
    apply(cast(Operations, op), parameters)


def downgrade() -> None:
    raise NotImplementedError("forward-only migration; restore the verified pre-migration backup")
