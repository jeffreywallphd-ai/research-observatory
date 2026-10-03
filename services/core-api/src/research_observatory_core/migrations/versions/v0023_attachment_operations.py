"""Add durable, exact operation-to-candidate attachment bindings."""

from typing import Any, cast

from alembic.operations import Operations
from sqlalchemy import text

revision = "0023_attachment_operations"
down_revision = "0022_document_attachments"
source_schema_version = 22
target_schema_version = 23
TARGET_SCHEMA_SHA256 = "0d5eb89a3975aa1d95fa4d190ce8debfee2ae43d390669ce8b3acb5f10a1a41e"
TARGET_PROFILE_SHA256 = "bc4f7aa4029ed660329b407362c017a42de2966f1d18bbbcbe7c75f1afa837f5"
MATERIAL_MIGRATION_STEPS = (
    "attachment-operation-authority-create",
    "metadata-v22-authority-drop",
    "metadata-v22-rename",
    "metadata-v23-create",
    "metadata-v23-copy",
    "metadata-v22-drop",
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
        raise ValueError("v23 attachment-operation migration requires the dedicated migration connection")

    for statement in parameters["attachmentOperationAuthority"]:
        operations.execute(statement)
    _migration_step_completed("attachment-operation-authority-create")

    operations.execute("DROP TRIGGER schema_metadata_no_update")
    operations.execute("DROP TRIGGER schema_metadata_no_delete")
    _migration_step_completed("metadata-v22-authority-drop")
    operations.rename_table("schema_metadata", "schema_metadata_v22")
    _migration_step_completed("metadata-v22-rename")
    operations.execute(parameters["schemaMetadataDdl"])
    _migration_step_completed("metadata-v23-create")
    bind.execute(
        text(
            "INSERT INTO schema_metadata SELECT singleton,23,database_profile,application_id,"
            ":profile,:schema,created_at FROM schema_metadata_v22"
        ),
        {"profile": TARGET_PROFILE_SHA256, "schema": TARGET_SCHEMA_SHA256},
    )
    _migration_step_completed("metadata-v23-copy")
    operations.drop_table("schema_metadata_v22")
    _migration_step_completed("metadata-v22-drop")
    for statement in parameters["schemaMetadataTriggers"]:
        operations.execute(statement)
    bind.execute(
        text(
            "INSERT INTO schema_migrations (migration_id,from_schema_version,to_schema_version,applied_at,"
            "backup_manifest_sha256,source_schema_sha256,target_schema_sha256,migration_tool) "
            "VALUES (:migration_id,22,23,:applied_at,:backup_manifest_sha256,:source_schema_sha256,"
            ":target_schema_sha256,'alembic-1.18.5')"
        ),
        parameters,
    )
    _migration_step_completed("migration-history-insert")
    operations.execute("PRAGMA user_version=23")
    _migration_step_completed("user-version-advance")


def upgrade() -> None:
    from alembic import op

    parameters = op.get_context().opts.get("research_observatory_parameters")
    if not isinstance(parameters, dict):
        raise ValueError("governed migration parameters are required")
    apply(cast(Operations, op), parameters)


def downgrade() -> None:
    raise NotImplementedError("forward-only migration; restore the verified pre-migration backup")
