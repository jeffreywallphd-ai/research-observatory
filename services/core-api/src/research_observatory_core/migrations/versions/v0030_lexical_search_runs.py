"""Preserve exact v29 history and add typed immutable lexical observations."""

from typing import Any, cast

from alembic.operations import Operations
from sqlalchemy import text

from ...search.run_schema import DDL, TABLES

revision = "0030_lexical_search_runs"
down_revision = "0029_lexical_index_generations"
source_schema_version = 29
target_schema_version = 30
SOURCE_SCHEMA_SHA256 = "278e4c7f6e7b219cc022ca0d71dee2199ba0bbb6cb5587ce6ea9acd84895a0e3"
SOURCE_PROFILE_SHA256 = "662d2a272faec2d6bad6d292140dca80e9c803bf6df0763f69bf63b223dd3dbb"
TARGET_SCHEMA_SHA256 = "482afee1e46c8c867d6a216c243dd77f688cb3aa7f7aaf05f96aa171687f27fc"
TARGET_PROFILE_SHA256 = "6c9afe22b62f6dbca7da0ddbc0ad3e3c42fd23b3d920b465a5375a651751ed19"

MATERIAL_MIGRATION_STEPS = (
    *(f"search-run-ddl-{index:02}" for index in range(len(DDL))),
    "metadata-v29-authority-drop",
    "metadata-v29-rename",
    "metadata-v30-create",
    "metadata-v30-copy",
    "metadata-v29-drop",
    "metadata-v30-authority-create",
    "migration-history-insert",
    "user-version-advance",
)


def _migration_step_completed(_step: str) -> None:
    """Deterministic rollback seam; no production recovery authority."""


def apply(operations: Operations, parameters: dict[str, Any]) -> None:
    if (
        parameters.get("targetSchemaSha256") != TARGET_SCHEMA_SHA256
        or parameters.get("targetProfileSha256") != TARGET_PROFILE_SHA256
        or parameters.get("source_schema_sha256") != SOURCE_SCHEMA_SHA256
    ):
        raise ValueError("migration target authority mismatch")
    bind = operations.get_bind()
    if bind is None or bind.exec_driver_sql("PRAGMA foreign_keys").scalar_one() != 0:
        raise ValueError("search observation authority requires the dedicated migration connection")
    for index, statement in enumerate(DDL):
        operations.execute(statement)
        _migration_step_completed(f"search-run-ddl-{index:02}")
    # Existing raw change/outbox rows remain byte-for-byte untouched. No
    # historical event is relabelled as a newly authenticated observation.
    operations.execute("DROP TRIGGER schema_metadata_no_update")
    operations.execute("DROP TRIGGER schema_metadata_no_delete")
    _migration_step_completed("metadata-v29-authority-drop")
    operations.rename_table("schema_metadata", "schema_metadata_v29")
    _migration_step_completed("metadata-v29-rename")
    operations.execute(parameters["schemaMetadataDdl"])
    _migration_step_completed("metadata-v30-create")
    bind.execute(
        text(
            "INSERT INTO schema_metadata SELECT singleton,30,database_profile,application_id,"
            ":profile,:schema,created_at FROM schema_metadata_v29"
        ),
        {"profile": TARGET_PROFILE_SHA256, "schema": TARGET_SCHEMA_SHA256},
    )
    _migration_step_completed("metadata-v30-copy")
    operations.drop_table("schema_metadata_v29")
    _migration_step_completed("metadata-v29-drop")
    for statement in parameters["schemaMetadataTriggers"]:
        operations.execute(statement)
    _migration_step_completed("metadata-v30-authority-create")
    bind.execute(
        text(
            "INSERT INTO schema_migrations (migration_id,from_schema_version,to_schema_version,applied_at,"
            "backup_manifest_sha256,source_schema_sha256,target_schema_sha256,migration_tool) VALUES "
            "(:migration_id,29,30,:applied_at,:backup_manifest_sha256,:source_schema_sha256,"
            ":target_schema_sha256,'alembic-1.18.5')"
        ),
        parameters,
    )
    _migration_step_completed("migration-history-insert")
    operations.execute("PRAGMA user_version=30")
    _migration_step_completed("user-version-advance")


def upgrade() -> None:
    from alembic import op

    parameters = op.get_context().opts.get("research_observatory_parameters")
    if not isinstance(parameters, dict):
        raise ValueError("governed migration parameters are required")
    apply(cast(Operations, op), parameters)


def downgrade() -> None:
    raise NotImplementedError("forward-only migration; restore the verified pre-migration backup")


__all__ = ["TABLES", "revision", "source_schema_version"]
