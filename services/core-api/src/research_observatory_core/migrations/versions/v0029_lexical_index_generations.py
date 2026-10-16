"""Preserve literal v28 history; add protected derivative generation authority."""

from typing import Any, cast

from alembic.operations import Operations
from sqlalchemy import text

from ...search.canonical_schema import DDL, TABLES

revision = "0029_lexical_index_generations"
down_revision = "0028_document_enrichments"
source_schema_version = 28
target_schema_version = 29
SOURCE_SCHEMA_SHA256 = "3f29b29cface11d5355f704c943459243fc7f9d0baf07725747c73547b1e4cb6"
SOURCE_PROFILE_SHA256 = "6cc9fc713678dcbaab23bd922a4010098cbd05922932a4b5f4840967f8f377e6"
TARGET_SCHEMA_SHA256 = "278e4c7f6e7b219cc022ca0d71dee2199ba0bbb6cb5587ce6ea9acd84895a0e3"
TARGET_PROFILE_SHA256 = "662d2a272faec2d6bad6d292140dca80e9c803bf6df0763f69bf63b223dd3dbb"

MATERIAL_MIGRATION_STEPS = (
    *(f"search-ddl-{index:02}" for index in range(len(DDL))),
    "outbox-history-backfill",
    "metadata-v28-authority-drop",
    "metadata-v28-rename",
    "metadata-v29-create",
    "metadata-v29-copy",
    "metadata-v28-drop",
    "metadata-v29-authority-create",
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
        raise ValueError("search authority requires the dedicated migration connection")
    for index, statement in enumerate(DDL):
        operations.execute(statement)
        _migration_step_completed(f"search-ddl-{index:02}")
    # Every pre-existing outbox row is preserved and covered. Sorting gives a
    # deterministic one-time backfill, not a claim that UUID order is a live
    # commit clock. All future source changes acquire their persisted sequence
    # in the same writer as the outbox insert. Exact controller-only events are
    # excluded by the new trigger, preventing recursive index scheduling.
    operations.execute(
        "INSERT INTO search_changes(project_id,outbox_id,revision_id,event_type,occurred_at,record_sha256) "
        "SELECT project_id,outbox_id,revision_id,event_type,occurred_at,record_sha256 FROM outbox_events ORDER "
        "BY outbox_id"
    )
    _migration_step_completed("outbox-history-backfill")
    operations.execute("DROP TRIGGER schema_metadata_no_update")
    operations.execute("DROP TRIGGER schema_metadata_no_delete")
    _migration_step_completed("metadata-v28-authority-drop")
    operations.rename_table("schema_metadata", "schema_metadata_v28")
    _migration_step_completed("metadata-v28-rename")
    operations.execute(parameters["schemaMetadataDdl"])
    _migration_step_completed("metadata-v29-create")
    bind.execute(
        text(
            "INSERT INTO schema_metadata SELECT singleton,29,database_profile,application_id,"
            ":profile,:schema,created_at FROM schema_metadata_v28"
        ),
        {"profile": TARGET_PROFILE_SHA256, "schema": TARGET_SCHEMA_SHA256},
    )
    _migration_step_completed("metadata-v29-copy")
    operations.drop_table("schema_metadata_v28")
    _migration_step_completed("metadata-v28-drop")
    for statement in parameters["schemaMetadataTriggers"]:
        operations.execute(statement)
    _migration_step_completed("metadata-v29-authority-create")
    bind.execute(
        text(
            "INSERT INTO schema_migrations "
            "(migration_id,from_schema_version,to_schema_version,applied_at,backup_manifest_sha256,"
            "source_schema_sha256,target_schema_sha256,migration_tool) VALUES "
            "(:migration_id,28,29,:applied_at,:backup_manifest_sha256,:source_schema_sha256,"
            ":target_schema_sha256,'alembic-1.18.5')"
        ),
        parameters,
    )
    _migration_step_completed("migration-history-insert")
    operations.execute("PRAGMA user_version=29")
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
