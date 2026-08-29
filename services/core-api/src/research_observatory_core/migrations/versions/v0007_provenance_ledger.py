"""Add the canonical provenance ledger and advance the local schema to v7."""

from __future__ import annotations

from typing import Any, cast

from alembic.operations import Operations
from sqlalchemy import text

revision = "0007_provenance_ledger"
down_revision = "0006_actor_identity"
source_schema_version = 6
target_schema_version = 7

TARGET_SCHEMA_SHA256 = "49329a82e7ade17d57f09a33e650d81e1b3b1d67dc6e4e3b4c8a79d24b6f7475"
TARGET_PROFILE_SHA256 = "aa59d6f2858f41b7732c91947566fffaf5cd146e1143277deccf2707ceb751e0"

MATERIAL_MIGRATION_STEPS = (
    "ledger-authority-create",
    "legacy-narrow-bridge",
    "metadata-v6-authority-drop",
    "metadata-v6-rename",
    "metadata-v7-create",
    "metadata-v7-copy",
    "metadata-v6-drop",
    "migration-history-insert",
    "user-version-advance",
)


def _migration_step_completed(_step: str) -> None:
    """Private deterministic failpoint seam for transactional rollback proof."""


def apply(operations: Operations, parameters: dict[str, Any]) -> None:
    """Apply the exact v6-to-v7 DDL inside the caller-owned transaction."""

    if parameters.get("targetSchemaSha256") != TARGET_SCHEMA_SHA256:
        raise ValueError("migration target schema authority mismatch")
    if parameters.get("targetProfileSha256") != TARGET_PROFILE_SHA256:
        raise ValueError("migration target profile authority mismatch")
    bind = operations.get_bind()
    if bind is None:
        raise ValueError("online migration connection is required")
    for statement in parameters["ledgerAuthority"]:
        operations.execute(statement)
    _migration_step_completed("ledger-authority-create")
    operations.execute(
        """
        INSERT INTO provenance_legacy_bridges (
            event_id, project_id, revision_id, event_type, occurred_at, trace_id,
            actor_type, actor_id, source_record_sha256, bridge_state
        )
        SELECT event_id, project_id, revision_id, event_type, occurred_at, trace_id,
               actor_type, actor_id, record_sha256, 'legacy-narrow'
          FROM provenance_events
        """
    )
    _migration_step_completed("legacy-narrow-bridge")

    operations.execute("DROP TRIGGER schema_metadata_no_update")
    operations.execute("DROP TRIGGER schema_metadata_no_delete")
    _migration_step_completed("metadata-v6-authority-drop")
    operations.rename_table("schema_metadata", "schema_metadata_v6")
    _migration_step_completed("metadata-v6-rename")
    operations.execute(parameters["schemaMetadataDdl"])
    _migration_step_completed("metadata-v7-create")
    bind.execute(
        text(
            """
            INSERT INTO schema_metadata (
                singleton, schema_version, database_profile, application_id,
                profile_sha256, schema_sha256, created_at
            )
            SELECT singleton, 7, database_profile, application_id,
                   :profile_sha256, :schema_sha256, created_at
            FROM schema_metadata_v6
            """
        ),
        {"profile_sha256": TARGET_PROFILE_SHA256, "schema_sha256": TARGET_SCHEMA_SHA256},
    )
    _migration_step_completed("metadata-v7-copy")
    operations.drop_table("schema_metadata_v6")
    _migration_step_completed("metadata-v6-drop")
    for statement in parameters["schemaMetadataTriggers"]:
        operations.execute(statement)
    bind.execute(
        text(
            """
            INSERT INTO schema_migrations (
                migration_id, from_schema_version, to_schema_version, applied_at,
                backup_manifest_sha256, source_schema_sha256, target_schema_sha256,
                migration_tool
            ) VALUES (
                :migration_id, 6, 7, :applied_at, :backup_manifest_sha256,
                :source_schema_sha256, :target_schema_sha256, 'alembic-1.18.5'
            )
            """
        ),
        parameters,
    )
    _migration_step_completed("migration-history-insert")
    operations.execute("PRAGMA user_version=7")
    _migration_step_completed("user-version-advance")


def upgrade() -> None:
    """Standard Alembic entry point; the governed runner supplies parameters."""

    from alembic import op

    parameters = op.get_context().opts.get("research_observatory_parameters")
    if not isinstance(parameters, dict):
        raise ValueError("governed migration parameters are required")
    apply(cast(Operations, op), parameters)


def downgrade() -> None:
    """Research Observatory schema migrations are deliberately forward-only."""

    raise NotImplementedError("forward-only migration; restore the verified pre-migration backup")
