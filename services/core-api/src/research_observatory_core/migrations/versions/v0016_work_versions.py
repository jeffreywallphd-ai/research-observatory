"""Add scholarly manifestation and status authority without rewriting v15 history."""

from typing import Any, cast

from alembic.operations import Operations
from sqlalchemy import text

revision = "0016_work_versions"
down_revision = "0015_reconciliation_review"
source_schema_version = 15
target_schema_version = 16
TARGET_SCHEMA_SHA256 = "faa1dcd5823f086986ea3a86a8cc85369edd826f2a0c1d724f923bdff9f293f5"
TARGET_PROFILE_SHA256 = "2cf19511744a6536b5da695027768893bd54946460f57172dd790050bdafda72"
MATERIAL_MIGRATION_STEPS = (
    "version-authority-created",
    "metadata-v15-authority-drop",
    "metadata-v15-rename",
    "metadata-v16-create",
    "metadata-v16-copy",
    "metadata-v15-drop",
    "migration-history-insert",
    "user-version-advance",
)


def _migration_step_completed(_step: str) -> None:
    """Deterministic interruption seam; normal migration rollback remains authority."""


def apply(operations: Operations, parameters: dict[str, Any]) -> None:
    if parameters.get("targetSchemaSha256") != TARGET_SCHEMA_SHA256:
        raise ValueError("migration target schema authority mismatch")
    if parameters.get("targetProfileSha256") != TARGET_PROFILE_SHA256:
        raise ValueError("migration target profile authority mismatch")
    bind = operations.get_bind()
    if bind is None:
        raise ValueError("online migration connection is required")
    for statement in parameters["versionAuthority"]:
        operations.execute(statement)
    _migration_step_completed("version-authority-created")
    operations.execute("DROP TRIGGER schema_metadata_no_update")
    operations.execute("DROP TRIGGER schema_metadata_no_delete")
    _migration_step_completed("metadata-v15-authority-drop")
    operations.rename_table("schema_metadata", "schema_metadata_v15")
    _migration_step_completed("metadata-v15-rename")
    operations.execute(parameters["schemaMetadataDdl"])
    _migration_step_completed("metadata-v16-create")
    bind.execute(
        text(
            "INSERT INTO schema_metadata SELECT singleton,16,database_profile,application_id,"
            ":profile,:schema,created_at FROM schema_metadata_v15"
        ),
        {"profile": TARGET_PROFILE_SHA256, "schema": TARGET_SCHEMA_SHA256},
    )
    _migration_step_completed("metadata-v16-copy")
    operations.drop_table("schema_metadata_v15")
    _migration_step_completed("metadata-v15-drop")
    for statement in parameters["schemaMetadataTriggers"]:
        operations.execute(statement)
    bind.execute(
        text(
            "INSERT INTO schema_migrations (migration_id,from_schema_version,to_schema_version,applied_at,"
            "backup_manifest_sha256,source_schema_sha256,target_schema_sha256,migration_tool) "
            "VALUES (:migration_id,15,16,:applied_at,:backup_manifest_sha256,:source_schema_sha256,"
            ":target_schema_sha256,'alembic-1.18.5')"
        ),
        parameters,
    )
    _migration_step_completed("migration-history-insert")
    operations.execute("PRAGMA user_version=16")
    _migration_step_completed("user-version-advance")


def upgrade() -> None:
    from alembic import op

    parameters = op.get_context().opts.get("research_observatory_parameters")
    if not isinstance(parameters, dict):
        raise ValueError("governed migration parameters are required")
    apply(cast(Operations, op), parameters)


def downgrade() -> None:
    raise NotImplementedError("forward-only migration; restore the verified pre-migration backup")
