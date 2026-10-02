"""Add exact, immutable local document candidates and attachment assertions."""

from typing import Any, cast

from alembic.operations import Operations
from sqlalchemy import text

revision = "0022_document_attachments"
down_revision = "0021_plugin_grants"
source_schema_version = 21
target_schema_version = 22
TARGET_SCHEMA_SHA256 = "32dc9a2b87efdd8b69b92271b8b1841e40da07bbc86e9943f59dbe5784f2617e"
TARGET_PROFILE_SHA256 = "67361cdaa6b082a552f89a40c5a83036526da3a1230c8f6d3bef4cb57cc43997"
MATERIAL_MIGRATION_STEPS = (
    "document-attachment-authority-create",
    "metadata-v21-authority-drop",
    "metadata-v21-rename",
    "metadata-v22-create",
    "metadata-v22-copy",
    "metadata-v21-drop",
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
        raise ValueError("v22 document migration requires the dedicated migration connection")

    for statement in parameters["documentAttachmentAuthority"]:
        operations.execute(statement)
    _migration_step_completed("document-attachment-authority-create")

    operations.execute("DROP TRIGGER schema_metadata_no_update")
    operations.execute("DROP TRIGGER schema_metadata_no_delete")
    _migration_step_completed("metadata-v21-authority-drop")
    operations.rename_table("schema_metadata", "schema_metadata_v21")
    _migration_step_completed("metadata-v21-rename")
    operations.execute(parameters["schemaMetadataDdl"])
    _migration_step_completed("metadata-v22-create")
    bind.execute(
        text(
            "INSERT INTO schema_metadata SELECT singleton,22,database_profile,application_id,"
            ":profile,:schema,created_at FROM schema_metadata_v21"
        ),
        {"profile": TARGET_PROFILE_SHA256, "schema": TARGET_SCHEMA_SHA256},
    )
    _migration_step_completed("metadata-v22-copy")
    operations.drop_table("schema_metadata_v21")
    _migration_step_completed("metadata-v21-drop")
    for statement in parameters["schemaMetadataTriggers"]:
        operations.execute(statement)
    bind.execute(
        text(
            "INSERT INTO schema_migrations (migration_id,from_schema_version,to_schema_version,applied_at,"
            "backup_manifest_sha256,source_schema_sha256,target_schema_sha256,migration_tool) "
            "VALUES (:migration_id,21,22,:applied_at,:backup_manifest_sha256,:source_schema_sha256,"
            ":target_schema_sha256,'alembic-1.18.5')"
        ),
        parameters,
    )
    _migration_step_completed("migration-history-insert")
    operations.execute("PRAGMA user_version=22")
    _migration_step_completed("user-version-advance")


def upgrade() -> None:
    from alembic import op

    parameters = op.get_context().opts.get("research_observatory_parameters")
    if not isinstance(parameters, dict):
        raise ValueError("governed migration parameters are required")
    apply(cast(Operations, op), parameters)


def downgrade() -> None:
    raise NotImplementedError("forward-only migration; restore the verified pre-migration backup")
