"""Retain all v26 facts while admitting authenticated output-free invalidations."""

from typing import Any, cast

from alembic.operations import Operations
from sqlalchemy import text

revision = "0027_revision_invalidations"
down_revision = "0026_document_revisions"
source_schema_version = 26
target_schema_version = 27
TARGET_SCHEMA_SHA256 = "6dd6d3f62c0236dd3f810a01ac7b88370ba17b483cf3612fde34b82b29ade913"
TARGET_PROFILE_SHA256 = "034d2b29092d29be8008cc7149287cf92c350aa31cd045451ca8bae0d563bf77"
MATERIAL_MIGRATION_STEPS = (
    "impact-v26-snapshot",
    "impact-v26-drop",
    "impact-v27-create",
    "impact-v27-copy",
    "impact-v27-authority-create",
    "metadata-v26-authority-drop",
    "metadata-v26-rename",
    "metadata-v27-create",
    "metadata-v27-copy",
    "metadata-v26-drop",
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
        raise ValueError("v27 impact rebuild requires the dedicated migration connection")
    # Do not rename the parent table: SQLite would rewrite child FK references.
    # Same-column temporary snapshots preserve every historical value atomically.
    operations.execute("CREATE TEMP TABLE invalidation_v26_runs AS SELECT * FROM dependency_impact_runs")
    _migration_step_completed("impact-v26-snapshot")
    operations.drop_table("dependency_impact_runs")
    _migration_step_completed("impact-v26-drop")
    operations.execute(parameters["impactRunsDdl"])
    _migration_step_completed("impact-v27-create")
    operations.execute("INSERT INTO dependency_impact_runs SELECT * FROM invalidation_v26_runs")
    operations.execute("DROP TABLE invalidation_v26_runs")
    _migration_step_completed("impact-v27-copy")
    for statement in parameters["impactRunsAuthority"]:
        operations.execute(statement)
    _migration_step_completed("impact-v27-authority-create")

    operations.execute("DROP TRIGGER schema_metadata_no_update")
    operations.execute("DROP TRIGGER schema_metadata_no_delete")
    _migration_step_completed("metadata-v26-authority-drop")
    operations.rename_table("schema_metadata", "schema_metadata_v26")
    _migration_step_completed("metadata-v26-rename")
    operations.execute(parameters["schemaMetadataDdl"])
    _migration_step_completed("metadata-v27-create")
    bind.execute(
        text(
            "INSERT INTO schema_metadata SELECT singleton,27,database_profile,application_id,"
            ":profile,:schema,created_at FROM schema_metadata_v26"
        ),
        {"profile": TARGET_PROFILE_SHA256, "schema": TARGET_SCHEMA_SHA256},
    )
    _migration_step_completed("metadata-v27-copy")
    operations.drop_table("schema_metadata_v26")
    _migration_step_completed("metadata-v26-drop")
    for statement in parameters["schemaMetadataTriggers"]:
        operations.execute(statement)
    bind.execute(
        text(
            "INSERT INTO schema_migrations (migration_id,from_schema_version,to_schema_version,applied_at,"
            "backup_manifest_sha256,source_schema_sha256,target_schema_sha256,migration_tool) "
            "VALUES (:migration_id,26,27,:applied_at,:backup_manifest_sha256,:source_schema_sha256,"
            ":target_schema_sha256,'alembic-1.18.5')"
        ),
        parameters,
    )
    _migration_step_completed("migration-history-insert")
    operations.execute("PRAGMA user_version=27")
    _migration_step_completed("user-version-advance")


def upgrade() -> None:
    from alembic import op

    parameters = op.get_context().opts.get("research_observatory_parameters")
    if not isinstance(parameters, dict):
        raise ValueError("governed migration parameters are required")
    apply(cast(Operations, op), parameters)


def downgrade() -> None:
    raise NotImplementedError("forward-only migration; restore the verified pre-migration backup")
