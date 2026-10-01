"""Add immutable, source-bound corpus report projections without rewriting v18."""

from typing import Any, cast

from alembic.operations import Operations
from sqlalchemy import text

revision = "0019_corpus_reports"
down_revision = "0018_rights_policy"
source_schema_version = 18
target_schema_version = 19
TARGET_SCHEMA_SHA256 = "829684b8a5274b6666400c2719ea9302384a8bdd01024b8f952b49a834ae52ba"
TARGET_PROFILE_SHA256 = "e22cb614472013b6ed3fac45c9778e7fb9c987018d20f416911a2f805db4a50f"
MATERIAL_MIGRATION_STEPS = (
    "report-snapshots-create",
    "report-members-create",
    "report-sources-create",
    "report-paths-create",
    "report-authority-create",
    "metadata-v18-authority-drop",
    "metadata-v18-rename",
    "metadata-v19-create",
    "metadata-v19-copy",
    "metadata-v18-drop",
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
        raise ValueError("v19 corpus report migration requires the dedicated migration connection")

    for statement in parameters["reportAuthority"]:
        operations.execute(statement)
        for prefix, step in (
            ("CREATE TABLE corpus_report_snapshots", "report-snapshots-create"),
            ("CREATE TABLE corpus_report_members", "report-members-create"),
            ("CREATE TABLE corpus_report_sources", "report-sources-create"),
            ("CREATE TABLE corpus_report_paths", "report-paths-create"),
        ):
            if prefix in statement:
                _migration_step_completed(step)
    _migration_step_completed("report-authority-create")

    operations.execute("DROP TRIGGER schema_metadata_no_update")
    operations.execute("DROP TRIGGER schema_metadata_no_delete")
    _migration_step_completed("metadata-v18-authority-drop")
    operations.rename_table("schema_metadata", "schema_metadata_v18")
    _migration_step_completed("metadata-v18-rename")
    operations.execute(parameters["schemaMetadataDdl"])
    _migration_step_completed("metadata-v19-create")
    bind.execute(
        text(
            "INSERT INTO schema_metadata SELECT singleton,19,database_profile,application_id,"
            ":profile,:schema,created_at FROM schema_metadata_v18"
        ),
        {"profile": TARGET_PROFILE_SHA256, "schema": TARGET_SCHEMA_SHA256},
    )
    _migration_step_completed("metadata-v19-copy")
    operations.drop_table("schema_metadata_v18")
    _migration_step_completed("metadata-v18-drop")
    for statement in parameters["schemaMetadataTriggers"]:
        operations.execute(statement)
    bind.execute(
        text(
            "INSERT INTO schema_migrations (migration_id,from_schema_version,to_schema_version,applied_at,"
            "backup_manifest_sha256,source_schema_sha256,target_schema_sha256,migration_tool) "
            "VALUES (:migration_id,18,19,:applied_at,:backup_manifest_sha256,:source_schema_sha256,"
            ":target_schema_sha256,'alembic-1.18.5')"
        ),
        parameters,
    )
    _migration_step_completed("migration-history-insert")
    operations.execute("PRAGMA user_version=19")
    _migration_step_completed("user-version-advance")


def upgrade() -> None:
    from alembic import op

    parameters = op.get_context().opts.get("research_observatory_parameters")
    if not isinstance(parameters, dict):
        raise ValueError("governed migration parameters are required")
    apply(cast(Operations, op), parameters)


def downgrade() -> None:
    raise NotImplementedError("forward-only migration; restore the verified pre-migration backup")
