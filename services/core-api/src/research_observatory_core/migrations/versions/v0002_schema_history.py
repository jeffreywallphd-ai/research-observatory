"""Add immutable schema-migration history and advance the SQLite profile to version 2."""

from __future__ import annotations

from typing import Any, cast

from alembic.operations import Operations
from sqlalchemy import text

revision = "0002_schema_history"
down_revision = None
source_schema_version = 1
target_schema_version = 2

# Immutable authority derived from the exact compiled target DDL/profile. The
# migration refuses to run when its caller supplies different values.
TARGET_SCHEMA_SHA256 = "afd48fbe857de4172215e9cb61a0f6137e73edec685dcc116bedbb66eb519dda"
TARGET_PROFILE_SHA256 = "29454c72d0b357c2ece14a8991db57bfb87414d7ade85d1a2e8048a648a17cc2"

SCHEMA_METADATA_V2_DDL = """
    CREATE TABLE schema_metadata (
        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
        schema_version INTEGER NOT NULL CHECK (schema_version = 2),
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

SCHEMA_MIGRATIONS_DDL = """
    CREATE TABLE schema_migrations (
        migration_id TEXT PRIMARY KEY CHECK (
            length(migration_id) BETWEEN 1 AND 100
            AND migration_id NOT GLOB '*[^a-z0-9._-]*'
        ),
        from_schema_version INTEGER NOT NULL CHECK (from_schema_version BETWEEN 1 AND 9007199254740991),
        to_schema_version INTEGER NOT NULL CHECK (to_schema_version = from_schema_version + 1),
        applied_at TEXT NOT NULL CHECK (
            length(applied_at) = 24 AND substr(applied_at, 5, 1) = '-'
            AND substr(applied_at, 8, 1) = '-' AND substr(applied_at, 11, 1) = 'T'
            AND substr(applied_at, 14, 1) = ':' AND substr(applied_at, 17, 1) = ':'
            AND substr(applied_at, 20, 1) = '.' AND substr(applied_at, 24, 1) = 'Z'
            AND applied_at NOT GLOB '*[^0-9TZ:.-]*'
        ),
        backup_manifest_sha256 TEXT NOT NULL CHECK (
            length(backup_manifest_sha256) = 64
            AND backup_manifest_sha256 NOT GLOB '*[^0-9a-f]*'
        ),
        source_schema_sha256 TEXT NOT NULL CHECK (
            length(source_schema_sha256) = 64
            AND source_schema_sha256 NOT GLOB '*[^0-9a-f]*'
        ),
        target_schema_sha256 TEXT NOT NULL CHECK (
            length(target_schema_sha256) = 64
            AND target_schema_sha256 NOT GLOB '*[^0-9a-f]*'
        ),
        migration_tool TEXT NOT NULL CHECK (migration_tool = 'alembic-1.18.5')
    ) STRICT
"""

SCHEMA_MIGRATIONS_TRIGGERS = (
    """
        CREATE TRIGGER schema_migrations_no_update
        BEFORE UPDATE ON schema_migrations
        BEGIN
            SELECT RAISE(ABORT, 'schema migration history is append-only');
        END
    """,
    """
        CREATE TRIGGER schema_migrations_no_delete
        BEFORE DELETE ON schema_migrations
        BEGIN
            SELECT RAISE(ABORT, 'schema migration history is append-only');
        END
    """,
)

SCHEMA_METADATA_TRIGGERS = (
    """
            CREATE TRIGGER schema_metadata_no_update
            BEFORE UPDATE ON schema_metadata
            BEGIN
                SELECT RAISE(ABORT, 'schema metadata is immutable outside a reviewed migration');
            END
    """,
    """
            CREATE TRIGGER schema_metadata_no_delete
            BEFORE DELETE ON schema_metadata
            BEGIN
                SELECT RAISE(ABORT, 'schema metadata is immutable outside a reviewed migration');
            END
    """,
)


def apply(operations: Operations, parameters: dict[str, Any]) -> None:
    """Apply the exact v1-to-v2 DDL inside the caller-owned transaction."""

    if parameters.get("targetSchemaSha256") != TARGET_SCHEMA_SHA256:
        raise ValueError("migration target schema authority mismatch")
    if parameters.get("targetProfileSha256") != TARGET_PROFILE_SHA256:
        raise ValueError("migration target profile authority mismatch")
    operations.execute("DROP TRIGGER schema_metadata_no_update")
    operations.execute("DROP TRIGGER schema_metadata_no_delete")
    operations.rename_table("schema_metadata", "schema_metadata_v1")
    operations.execute(SCHEMA_METADATA_V2_DDL)
    bind = operations.get_bind()
    if bind is None:
        raise ValueError("online migration connection is required")
    bind.execute(
        text(
            """
        INSERT INTO schema_metadata (
            singleton, schema_version, database_profile, application_id,
            profile_sha256, schema_sha256, created_at
        )
        SELECT singleton, 2, database_profile, application_id,
               :profile_sha256, :schema_sha256, created_at
        FROM schema_metadata_v1
        """
        ),
        {"profile_sha256": TARGET_PROFILE_SHA256, "schema_sha256": TARGET_SCHEMA_SHA256},
    )
    operations.drop_table("schema_metadata_v1")
    operations.execute(SCHEMA_MIGRATIONS_DDL)
    for statement in (*SCHEMA_METADATA_TRIGGERS, *SCHEMA_MIGRATIONS_TRIGGERS):
        operations.execute(statement)
    bind.execute(
        text(
            """
        INSERT INTO schema_migrations (
            migration_id, from_schema_version, to_schema_version, applied_at,
            backup_manifest_sha256, source_schema_sha256, target_schema_sha256,
            migration_tool
        ) VALUES (
            :migration_id, 1, 2, :applied_at, :backup_manifest_sha256,
            :source_schema_sha256, :target_schema_sha256, 'alembic-1.18.5'
        )
        """
        ),
        parameters,
    )
    operations.execute("PRAGMA user_version=2")


def upgrade() -> None:
    """Standard Alembic entry point; the governed runner supplies bound parameters."""

    from alembic import op

    parameters = op.get_context().opts.get("research_observatory_parameters")
    if not isinstance(parameters, dict):
        raise ValueError("governed migration parameters are required")
    apply(cast(Operations, op), parameters)


def downgrade() -> None:
    """Research Observatory schema migrations are deliberately forward-only."""

    raise NotImplementedError("forward-only migration; restore the verified pre-migration backup")
