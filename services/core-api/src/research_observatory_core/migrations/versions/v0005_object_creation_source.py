"""Add bounded object creation-source metadata and advance schema to v5."""

from __future__ import annotations

from typing import Any, cast

from alembic.operations import Operations
from sqlalchemy import text

revision = "0005_object_creation_source"
down_revision = "0004_object_envelope_upgrades"
source_schema_version = 4
target_schema_version = 5

# Filled from the exact compiled target DDL/profile. The governed migration
# refuses caller-supplied authority that differs from these reviewed values.
TARGET_SCHEMA_SHA256 = "4d505b3f925e9df09b137cae61b56125878aa84fd0d6cb353e5d415a0602e2fd"
TARGET_PROFILE_SHA256 = "949f2d60ebe020ad8e8e049ac9d58307213d7aa7008025e5b340e543064ffaa7"

OBJECT_CREATION_SOURCE_COLUMN = """
    ALTER TABLE object_records ADD COLUMN creation_source TEXT NOT NULL
    DEFAULT 'legacy-unreported'
    CHECK (creation_source IN (
        'local-import', 'connector-acquisition', 'local-derivation',
        'test-fixture', 'legacy-unreported'
    ))
"""

SCHEMA_METADATA_V5_DDL = """
    CREATE TABLE schema_metadata (
        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
        schema_version INTEGER NOT NULL CHECK (schema_version = 5),
        database_profile TEXT NOT NULL CHECK (database_profile = 'sqlite-wal-v1'),
        application_id INTEGER NOT NULL CHECK (application_id = 1380926035),
        profile_sha256 TEXT NOT NULL CHECK (
            length(profile_sha256) = 64 AND profile_sha256 NOT GLOB '*[^0-9a-f]*'
        ),
        schema_sha256 TEXT NOT NULL CHECK (
            length(schema_sha256) = 64 AND schema_sha256 NOT GLOB '*[^0-9a-f]*'
        ),
        created_at TEXT NOT NULL CHECK (
            length(created_at) = 24 AND substr(created_at, 5, 1) = '-'
            AND substr(created_at, 8, 1) = '-' AND substr(created_at, 11, 1) = 'T'
            AND substr(created_at, 14, 1) = ':' AND substr(created_at, 17, 1) = ':'
            AND substr(created_at, 20, 1) = '.' AND substr(created_at, 24, 1) = 'Z'
            AND created_at NOT GLOB '*[^0-9TZ:.-]*'
        )
    ) STRICT
"""

MATERIAL_MIGRATION_STEPS = (
    "object-creation-source-column",
    "metadata-trigger-removal",
    "metadata-v4-rename",
    "metadata-v5-create",
    "metadata-v5-copy",
    "metadata-v4-drop",
    "migration-history-insert",
    "user-version-advance",
)


def _migration_step_completed(_step: str) -> None:
    """Private deterministic failpoint seam for transactional rollback proof."""


def apply(operations: Operations, parameters: dict[str, Any]) -> None:
    """Apply the exact v4-to-v5 DDL inside the caller-owned transaction."""

    if parameters.get("targetSchemaSha256") != TARGET_SCHEMA_SHA256:
        raise ValueError("migration target schema authority mismatch")
    if parameters.get("targetProfileSha256") != TARGET_PROFILE_SHA256:
        raise ValueError("migration target profile authority mismatch")
    bind = operations.get_bind()
    if bind is None:
        raise ValueError("online migration connection is required")
    operations.execute(OBJECT_CREATION_SOURCE_COLUMN)
    _migration_step_completed("object-creation-source-column")
    operations.execute("DROP TRIGGER schema_metadata_no_update")
    operations.execute("DROP TRIGGER schema_metadata_no_delete")
    _migration_step_completed("metadata-trigger-removal")
    operations.rename_table("schema_metadata", "schema_metadata_v4")
    _migration_step_completed("metadata-v4-rename")
    operations.execute(SCHEMA_METADATA_V5_DDL)
    _migration_step_completed("metadata-v5-create")
    bind.execute(
        text(
            """
            INSERT INTO schema_metadata (
                singleton, schema_version, database_profile, application_id,
                profile_sha256, schema_sha256, created_at
            )
            SELECT singleton, 5, database_profile, application_id,
                   :profile_sha256, :schema_sha256, created_at
            FROM schema_metadata_v4
            """
        ),
        {"profile_sha256": TARGET_PROFILE_SHA256, "schema_sha256": TARGET_SCHEMA_SHA256},
    )
    _migration_step_completed("metadata-v5-copy")
    operations.drop_table("schema_metadata_v4")
    _migration_step_completed("metadata-v4-drop")
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
                :migration_id, 4, 5, :applied_at, :backup_manifest_sha256,
                :source_schema_sha256, :target_schema_sha256, 'alembic-1.18.5'
            )
            """
        ),
        parameters,
    )
    _migration_step_completed("migration-history-insert")
    operations.execute("PRAGMA user_version=5")
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
