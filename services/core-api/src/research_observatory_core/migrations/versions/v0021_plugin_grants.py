"""Add immutable project-local signed-plugin grant and denial authority."""

from typing import Any, cast

from alembic.operations import Operations
from sqlalchemy import text

revision = "0021_plugin_grants"
down_revision = "0020_corpus_source_projection"
source_schema_version = 20
target_schema_version = 21
TARGET_SCHEMA_SHA256 = "c0aa9be9916fbe517f1ae94a86aeac13f19a92ec366b1a4d4d816bff614da034"
TARGET_PROFILE_SHA256 = "74ed7818d261958b0039aef90c00b42ed5f97b3558cc61818fcca93a862a9822"
MATERIAL_MIGRATION_STEPS = (
    "plugin-grant-authority-create",
    "metadata-v20-authority-drop",
    "metadata-v20-rename",
    "metadata-v21-create",
    "metadata-v21-copy",
    "metadata-v20-drop",
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
        raise ValueError("v21 plugin grant migration requires the dedicated migration connection")

    for statement in parameters["pluginGrantAuthority"]:
        operations.execute(statement)
    _migration_step_completed("plugin-grant-authority-create")

    operations.execute("DROP TRIGGER schema_metadata_no_update")
    operations.execute("DROP TRIGGER schema_metadata_no_delete")
    _migration_step_completed("metadata-v20-authority-drop")
    operations.rename_table("schema_metadata", "schema_metadata_v20")
    _migration_step_completed("metadata-v20-rename")
    operations.execute(parameters["schemaMetadataDdl"])
    _migration_step_completed("metadata-v21-create")
    bind.execute(
        text(
            "INSERT INTO schema_metadata SELECT singleton,21,database_profile,application_id,"
            ":profile,:schema,created_at FROM schema_metadata_v20"
        ),
        {"profile": TARGET_PROFILE_SHA256, "schema": TARGET_SCHEMA_SHA256},
    )
    _migration_step_completed("metadata-v21-copy")
    operations.drop_table("schema_metadata_v20")
    _migration_step_completed("metadata-v20-drop")
    for statement in parameters["schemaMetadataTriggers"]:
        operations.execute(statement)
    bind.execute(
        text(
            "INSERT INTO schema_migrations (migration_id,from_schema_version,to_schema_version,applied_at,"
            "backup_manifest_sha256,source_schema_sha256,target_schema_sha256,migration_tool) "
            "VALUES (:migration_id,20,21,:applied_at,:backup_manifest_sha256,:source_schema_sha256,"
            ":target_schema_sha256,'alembic-1.18.5')"
        ),
        parameters,
    )
    _migration_step_completed("migration-history-insert")
    operations.execute("PRAGMA user_version=21")
    _migration_step_completed("user-version-advance")


def upgrade() -> None:
    from alembic import op

    parameters = op.get_context().opts.get("research_observatory_parameters")
    if not isinstance(parameters, dict):
        raise ValueError("governed migration parameters are required")
    apply(cast(Operations, op), parameters)


def downgrade() -> None:
    raise NotImplementedError("forward-only migration; restore the verified pre-migration backup")
