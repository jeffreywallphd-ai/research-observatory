"""Add rebuildable incremental source-overlap counts without changing v19 reports."""

from typing import Any, cast

from alembic.operations import Operations
from sqlalchemy import text

from research_observatory_core.corpus_source_projection import backfill_source_projection

revision = "0020_corpus_source_projection"
down_revision = "0019_corpus_reports"
source_schema_version = 19
target_schema_version = 20
TARGET_SCHEMA_SHA256 = "c6bdef5f65d5f688747a1effed96f3cd79556e37891946e1985841bce4ae1cd6"
TARGET_PROFILE_SHA256 = "1e5b92e8e82cc64a191b4e3d5c1935d1931c4c3639678c26860fc317e1e11515"
MATERIAL_MIGRATION_STEPS = (
    "projection-authority-create",
    "projection-backfill",
    "metadata-v19-authority-drop",
    "metadata-v19-rename",
    "metadata-v20-create",
    "metadata-v20-copy",
    "metadata-v19-drop",
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
        raise ValueError("v20 source projection migration requires the dedicated migration connection")

    for statement in parameters["projectionAuthority"]:
        operations.execute(statement)
    _migration_step_completed("projection-authority-create")
    driver_connection = bind.connection.driver_connection
    if driver_connection is None:
        raise ValueError("migration driver connection is unavailable")
    backfill_source_projection(driver_connection)
    _migration_step_completed("projection-backfill")

    operations.execute("DROP TRIGGER schema_metadata_no_update")
    operations.execute("DROP TRIGGER schema_metadata_no_delete")
    _migration_step_completed("metadata-v19-authority-drop")
    operations.rename_table("schema_metadata", "schema_metadata_v19")
    _migration_step_completed("metadata-v19-rename")
    operations.execute(parameters["schemaMetadataDdl"])
    _migration_step_completed("metadata-v20-create")
    bind.execute(
        text(
            "INSERT INTO schema_metadata SELECT singleton,20,database_profile,application_id,"
            ":profile,:schema,created_at FROM schema_metadata_v19"
        ),
        {"profile": TARGET_PROFILE_SHA256, "schema": TARGET_SCHEMA_SHA256},
    )
    _migration_step_completed("metadata-v20-copy")
    operations.drop_table("schema_metadata_v19")
    _migration_step_completed("metadata-v19-drop")
    for statement in parameters["schemaMetadataTriggers"]:
        operations.execute(statement)
    bind.execute(
        text(
            "INSERT INTO schema_migrations (migration_id,from_schema_version,to_schema_version,applied_at,"
            "backup_manifest_sha256,source_schema_sha256,target_schema_sha256,migration_tool) "
            "VALUES (:migration_id,19,20,:applied_at,:backup_manifest_sha256,:source_schema_sha256,"
            ":target_schema_sha256,'alembic-1.18.5')"
        ),
        parameters,
    )
    _migration_step_completed("migration-history-insert")
    operations.execute("PRAGMA user_version=20")
    _migration_step_completed("user-version-advance")


def upgrade() -> None:
    from alembic import op

    parameters = op.get_context().opts.get("research_observatory_parameters")
    if not isinstance(parameters, dict):
        raise ValueError("governed migration parameters are required")
    apply(cast(Operations, op), parameters)


def downgrade() -> None:
    raise NotImplementedError("forward-only migration; restore the verified pre-migration backup")
