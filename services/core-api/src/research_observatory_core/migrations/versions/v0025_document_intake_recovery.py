"""Add immutable document intake, recovery and local access-need records."""

from typing import Any, cast

from alembic.operations import Operations
from sqlalchemy import text

revision = "0025_document_intake_recovery"
down_revision = "0024_open_access_acquisition"
source_schema_version = 24
target_schema_version = 25
TARGET_SCHEMA_SHA256 = "5c2090bb9586117f8f0e521efcb74ab10bd64a855fdcdc943035385cd1742951"
TARGET_PROFILE_SHA256 = "50c8583b7958c4e035690fdcf305c8d968b3a4c26a21f18e8744436eabf45721"
MATERIAL_MIGRATION_STEPS = (
    "intake-authority-create",
    "metadata-v24-authority-drop",
    "metadata-v24-rename",
    "metadata-v25-create",
    "metadata-v25-copy",
    "metadata-v24-drop",
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
        raise ValueError("v25 intake migration requires the dedicated migration connection")
    for statement in parameters["intakeAuthority"]:
        operations.execute(statement)
    _migration_step_completed("intake-authority-create")
    operations.execute("DROP TRIGGER schema_metadata_no_update")
    operations.execute("DROP TRIGGER schema_metadata_no_delete")
    _migration_step_completed("metadata-v24-authority-drop")
    operations.rename_table("schema_metadata", "schema_metadata_v24")
    _migration_step_completed("metadata-v24-rename")
    operations.execute(parameters["schemaMetadataDdl"])
    _migration_step_completed("metadata-v25-create")
    bind.execute(
        text(
            "INSERT INTO schema_metadata SELECT singleton,25,database_profile,application_id,"
            ":profile,:schema,created_at FROM schema_metadata_v24"
        ),
        {"profile": TARGET_PROFILE_SHA256, "schema": TARGET_SCHEMA_SHA256},
    )
    _migration_step_completed("metadata-v25-copy")
    operations.drop_table("schema_metadata_v24")
    _migration_step_completed("metadata-v24-drop")
    for statement in parameters["schemaMetadataTriggers"]:
        operations.execute(statement)
    bind.execute(
        text(
            "INSERT INTO schema_migrations (migration_id,from_schema_version,to_schema_version,applied_at,"
            "backup_manifest_sha256,source_schema_sha256,target_schema_sha256,migration_tool) "
            "VALUES (:migration_id,24,25,:applied_at,:backup_manifest_sha256,:source_schema_sha256,"
            ":target_schema_sha256,'alembic-1.18.5')"
        ),
        parameters,
    )
    _migration_step_completed("migration-history-insert")
    operations.execute("PRAGMA user_version=25")
    _migration_step_completed("user-version-advance")


def upgrade() -> None:
    from alembic import op

    parameters = op.get_context().opts.get("research_observatory_parameters")
    if not isinstance(parameters, dict):
        raise ValueError("governed migration parameters are required")
    apply(cast(Operations, op), parameters)


def downgrade() -> None:
    raise NotImplementedError("forward-only migration; restore the verified pre-migration backup")
