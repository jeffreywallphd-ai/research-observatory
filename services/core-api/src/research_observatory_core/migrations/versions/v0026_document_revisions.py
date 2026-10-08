"""Add immutable normalized parse results and accepted document revisions."""

from typing import Any, cast

from alembic.operations import Operations
from sqlalchemy import text

revision = "0026_document_revisions"
down_revision = "0025_document_intake_recovery"
source_schema_version = 25
target_schema_version = 26
TARGET_SCHEMA_SHA256 = "39e3fdd0fffedd2b226f74ebf48190efdecc0e53b9376dfce30e924de2206f2c"
TARGET_PROFILE_SHA256 = "b29c98353dc218688eb20ce1dc60ca05ee7b62e59cdbe1e514caffa75544289c"
MATERIAL_MIGRATION_STEPS = (
    "revision-authority-create",
    "metadata-v25-authority-drop",
    "metadata-v25-rename",
    "metadata-v26-create",
    "metadata-v26-copy",
    "metadata-v25-drop",
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
        raise ValueError("v26 document revision migration requires the dedicated migration connection")
    for statement in parameters["revisionAuthority"]:
        operations.execute(statement)
    _migration_step_completed("revision-authority-create")
    operations.execute("DROP TRIGGER schema_metadata_no_update")
    operations.execute("DROP TRIGGER schema_metadata_no_delete")
    _migration_step_completed("metadata-v25-authority-drop")
    operations.rename_table("schema_metadata", "schema_metadata_v25")
    _migration_step_completed("metadata-v25-rename")
    operations.execute(parameters["schemaMetadataDdl"])
    _migration_step_completed("metadata-v26-create")
    bind.execute(
        text(
            "INSERT INTO schema_metadata SELECT singleton,26,database_profile,application_id,"
            ":profile,:schema,created_at FROM schema_metadata_v25"
        ),
        {"profile": TARGET_PROFILE_SHA256, "schema": TARGET_SCHEMA_SHA256},
    )
    _migration_step_completed("metadata-v26-copy")
    operations.drop_table("schema_metadata_v25")
    _migration_step_completed("metadata-v25-drop")
    for statement in parameters["schemaMetadataTriggers"]:
        operations.execute(statement)
    bind.execute(
        text(
            "INSERT INTO schema_migrations (migration_id,from_schema_version,to_schema_version,applied_at,"
            "backup_manifest_sha256,source_schema_sha256,target_schema_sha256,migration_tool) "
            "VALUES (:migration_id,25,26,:applied_at,:backup_manifest_sha256,:source_schema_sha256,"
            ":target_schema_sha256,'alembic-1.18.5')"
        ),
        parameters,
    )
    _migration_step_completed("migration-history-insert")
    operations.execute("PRAGMA user_version=26")
    _migration_step_completed("user-version-advance")


def upgrade() -> None:
    from alembic import op

    parameters = op.get_context().opts.get("research_observatory_parameters")
    if not isinstance(parameters, dict):
        raise ValueError("governed migration parameters are required")
    apply(cast(Operations, op), parameters)


def downgrade() -> None:
    raise NotImplementedError("forward-only migration; restore the verified pre-migration backup")
