"""Add versioned encrypted-object envelope metadata and advance schema to v3."""

from __future__ import annotations

from typing import Any, cast

from alembic.operations import Operations
from sqlalchemy import text

revision = "0003_object_envelopes"
down_revision = "0002_schema_history"
source_schema_version = 2
target_schema_version = 3

TARGET_SCHEMA_SHA256 = "246ad968bb1931732c827d0739882c0d59ce91a06c7075867c503c0ef52fd356"
TARGET_PROFILE_SHA256 = "78f1ea999a50641758b0b618af33dc18739d6d6c99644d97823af959583ac2d9"

SCHEMA_METADATA_V3_DDL = """
    CREATE TABLE schema_metadata (
        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
        schema_version INTEGER NOT NULL CHECK (schema_version = 3),
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

OBJECT_ENVELOPE_COLUMNS = (
    """
        ALTER TABLE object_records ADD COLUMN envelope_version TEXT NOT NULL
        DEFAULT 'plaintext-fixture-v1'
        CHECK (envelope_version IN ('plaintext-fixture-v1', 'secretstream-xchacha20poly1305-v1'))
    """,
    """
        ALTER TABLE object_records ADD COLUMN key_version TEXT
        CHECK (key_version IS NULL OR (
            length(key_version) BETWEEN 1 AND 120
            AND key_version = lower(key_version)
            AND substr(key_version, 1, 1) GLOB '[a-z]'
            AND key_version NOT GLOB '*[^a-z0-9.-]*'
            AND key_version NOT GLOB '*..*' AND key_version NOT GLOB '*--*'
            AND substr(key_version, -1, 1) GLOB '[a-z0-9]'
        ))
    """,
    """
        ALTER TABLE object_records ADD COLUMN wrapped_key TEXT
        CHECK (wrapped_key IS NULL OR (
            length(wrapped_key) = 96 AND wrapped_key = lower(wrapped_key)
            AND wrapped_key NOT GLOB '*[^0-9a-f]*'
        ))
    """,
    """
        ALTER TABLE object_records ADD COLUMN wrap_nonce TEXT
        CHECK (wrap_nonce IS NULL OR (
            length(wrap_nonce) = 48 AND wrap_nonce = lower(wrap_nonce)
            AND wrap_nonce NOT GLOB '*[^0-9a-f]*'
        ))
    """,
    """
        ALTER TABLE object_records ADD COLUMN ciphertext_byte_length INTEGER NOT NULL DEFAULT 0
        CHECK (ciphertext_byte_length BETWEEN 0 AND 9007199254740991)
    """,
)

OBJECT_ENVELOPE_TRIGGERS = (
    """
        CREATE TRIGGER object_records_envelope_insert
        BEFORE INSERT ON object_records
        WHEN NOT (
            (NEW.envelope_version = 'plaintext-fixture-v1'
             AND NEW.key_version IS NULL AND NEW.wrapped_key IS NULL AND NEW.wrap_nonce IS NULL
             AND NEW.ciphertext_byte_length = NEW.byte_length)
            OR
            (NEW.envelope_version = 'secretstream-xchacha20poly1305-v1'
             AND NEW.key_version IS NOT NULL AND NEW.wrapped_key IS NOT NULL AND NEW.wrap_nonce IS NOT NULL
             AND NEW.ciphertext_byte_length >= 45)
        )
        BEGIN
            SELECT RAISE(ABORT, 'object encryption envelope is invalid');
        END
    """,
    """
        CREATE TRIGGER object_records_envelope_update
        BEFORE UPDATE ON object_records
        WHEN NOT (
            (NEW.envelope_version = 'plaintext-fixture-v1'
             AND NEW.key_version IS NULL AND NEW.wrapped_key IS NULL AND NEW.wrap_nonce IS NULL
             AND NEW.ciphertext_byte_length = NEW.byte_length)
            OR
            (NEW.envelope_version = 'secretstream-xchacha20poly1305-v1'
             AND NEW.key_version IS NOT NULL AND NEW.wrapped_key IS NOT NULL AND NEW.wrap_nonce IS NOT NULL
             AND NEW.ciphertext_byte_length >= 45)
        )
        BEGIN
            SELECT RAISE(ABORT, 'object encryption envelope is invalid');
        END
    """,
)

MATERIAL_MIGRATION_STEPS = (
    "object-envelope-columns",
    "object-envelope-backfill",
    "object-envelope-triggers",
    "metadata-trigger-removal",
    "metadata-v2-rename",
    "metadata-v3-create",
    "metadata-v3-copy",
    "metadata-v2-drop",
    "migration-history-insert",
    "user-version-advance",
)


def _migration_step_completed(_step: str) -> None:
    """Private deterministic failpoint seam for transactional rollback proof."""


def apply(operations: Operations, parameters: dict[str, Any]) -> None:
    if parameters.get("targetSchemaSha256") != TARGET_SCHEMA_SHA256:
        raise ValueError("migration target schema authority mismatch")
    if parameters.get("targetProfileSha256") != TARGET_PROFILE_SHA256:
        raise ValueError("migration target profile authority mismatch")
    for statement in OBJECT_ENVELOPE_COLUMNS:
        operations.execute(statement)
    _migration_step_completed("object-envelope-columns")
    operations.execute("UPDATE object_records SET ciphertext_byte_length=byte_length")
    _migration_step_completed("object-envelope-backfill")
    for statement in OBJECT_ENVELOPE_TRIGGERS:
        operations.execute(statement)
    _migration_step_completed("object-envelope-triggers")
    operations.execute("DROP TRIGGER schema_metadata_no_update")
    operations.execute("DROP TRIGGER schema_metadata_no_delete")
    _migration_step_completed("metadata-trigger-removal")
    operations.rename_table("schema_metadata", "schema_metadata_v2")
    _migration_step_completed("metadata-v2-rename")
    operations.execute(SCHEMA_METADATA_V3_DDL)
    _migration_step_completed("metadata-v3-create")
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
            SELECT singleton, 3, database_profile, application_id,
                   :profile_sha256, :schema_sha256, created_at
            FROM schema_metadata_v2
            """
        ),
        {"profile_sha256": TARGET_PROFILE_SHA256, "schema_sha256": TARGET_SCHEMA_SHA256},
    )
    _migration_step_completed("metadata-v3-copy")
    operations.drop_table("schema_metadata_v2")
    _migration_step_completed("metadata-v2-drop")
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
                :migration_id, 2, 3, :applied_at, :backup_manifest_sha256,
                :source_schema_sha256, :target_schema_sha256, 'alembic-1.18.5'
            )
            """
        ),
        parameters,
    )
    _migration_step_completed("migration-history-insert")
    operations.execute("PRAGMA user_version=3")
    _migration_step_completed("user-version-advance")


def upgrade() -> None:
    from alembic import op

    parameters = op.get_context().opts.get("research_observatory_parameters")
    if not isinstance(parameters, dict):
        raise ValueError("governed migration parameters are required")
    apply(cast(Operations, op), parameters)


def downgrade() -> None:
    raise NotImplementedError("forward-only migration; restore the verified pre-migration backup")
