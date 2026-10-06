"""Add durable, exact operation-to-candidate acquisition bindings."""

from typing import Any, cast

from alembic.operations import Operations
from sqlalchemy import text

revision = "0024_open_access_acquisition"
down_revision = "0023_attachment_operations"
source_schema_version = 23
target_schema_version = 24
TARGET_SCHEMA_SHA256 = "8078a6f7132200e6cf9e729f116c7b8ad6cd7c2bcf61d56f337e594dc7552a97"
TARGET_PROFILE_SHA256 = "b8f925467533ee5810343ce3a83a0035b8bf5e1f1989d421279994e0f73b9e1e"
MATERIAL_MIGRATION_STEPS = (
    "acquisition-authority-create",
    "metadata-v23-authority-drop",
    "metadata-v23-rename",
    "metadata-v24-create",
    "metadata-v24-copy",
    "metadata-v23-drop",
    "migration-history-insert",
    "user-version-advance",
)


def _migration_step_completed(_step: str) -> None:
    """Deterministic interruption seam for verified-backup/rollback tests."""


def apply(operations: Operations, parameters: dict[str, Any]) -> None:
    if parameters.get("targetSchemaSha256") != TARGET_SCHEMA_SHA256:
        raise ValueError("migration target schema authority mismatch")
    if parameters.get("targetProfileSha256") != TARGET_PROFILE_SHA256:
        raise ValueError("migration target profile authority mismatch")
    bind = operations.get_bind()
    if bind is None or bind.exec_driver_sql("PRAGMA foreign_keys").scalar_one() != 0:
        raise ValueError("v24 acquisition migration requires the dedicated migration connection")

    for statement in parameters["acquisitionAuthority"]:
        operations.execute(statement)
    _migration_step_completed("acquisition-authority-create")

    operations.execute("DROP TRIGGER schema_metadata_no_update")
    operations.execute("DROP TRIGGER schema_metadata_no_delete")
    _migration_step_completed("metadata-v23-authority-drop")
    operations.rename_table("schema_metadata", "schema_metadata_v23")
    _migration_step_completed("metadata-v23-rename")
    operations.execute(parameters["schemaMetadataDdl"])
    _migration_step_completed("metadata-v24-create")
    bind.execute(
        text(
            "INSERT INTO schema_metadata SELECT singleton,24,database_profile,application_id,"
            ":profile,:schema,created_at FROM schema_metadata_v23"
        ),
        {"profile": TARGET_PROFILE_SHA256, "schema": TARGET_SCHEMA_SHA256},
    )
    _migration_step_completed("metadata-v24-copy")
    operations.drop_table("schema_metadata_v23")
    _migration_step_completed("metadata-v23-drop")
    for statement in parameters["schemaMetadataTriggers"]:
        operations.execute(statement)
    bind.execute(
        text(
            "INSERT INTO schema_migrations (migration_id,from_schema_version,to_schema_version,applied_at,"
            "backup_manifest_sha256,source_schema_sha256,target_schema_sha256,migration_tool) "
            "VALUES (:migration_id,23,24,:applied_at,:backup_manifest_sha256,:source_schema_sha256,"
            ":target_schema_sha256,'alembic-1.18.5')"
        ),
        parameters,
    )
    _migration_step_completed("migration-history-insert")
    operations.execute("PRAGMA user_version=24")
    _migration_step_completed("user-version-advance")


def upgrade() -> None:
    from alembic import op

    parameters = op.get_context().opts.get("research_observatory_parameters")
    if not isinstance(parameters, dict):
        raise ValueError("governed migration parameters are required")
    apply(cast(Operations, op), parameters)


def downgrade() -> None:
    raise NotImplementedError("forward-only migration; restore the verified pre-migration backup")
