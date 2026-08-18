"""Add the durable prior-envelope upgrade journal and advance schema to v4."""

from __future__ import annotations

from typing import Any, cast

from alembic.operations import Operations
from sqlalchemy import text

revision = "0004_object_envelope_upgrades"
down_revision = "0003_object_envelopes"
source_schema_version = 3
target_schema_version = 4

TARGET_SCHEMA_SHA256 = "0b957b48a4280c0dd3c3f9ec518ac44b5fff9354e828572cd2af8aa95e496ff6"
TARGET_PROFILE_SHA256 = "12cd2d187b6abf8e3cc597288c103277f1079e77b2cd206ad2821730181dbffb"

SCHEMA_METADATA_V4_DDL = """
    CREATE TABLE schema_metadata (
        singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
        schema_version INTEGER NOT NULL CHECK (schema_version = 4),
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

OBJECT_ENVELOPE_UPGRADES_DDL = """
    CREATE TABLE object_envelope_upgrades (
        object_sha256 TEXT NOT NULL CHECK (
            length(object_sha256) = 64 AND object_sha256 = lower(object_sha256)
            AND object_sha256 NOT GLOB '*[^0-9a-f]*'
        ),
        project_id TEXT NOT NULL,
        phase TEXT NOT NULL CHECK (phase IN (
            'legacy-detected', 'replacement-writing', 'replacement-verified',
            'swap-intent', 'metadata-committed', 'complete'
        )),
        source_device TEXT CHECK (
            source_device IS NULL OR (
                length(source_device) BETWEEN 1 AND 32
                AND source_device NOT GLOB '*[^0-9]*'
            )
        ),
        source_inode TEXT CHECK (
            source_inode IS NULL OR (
                length(source_inode) BETWEEN 1 AND 32
                AND source_inode NOT GLOB '*[^0-9]*'
            )
        ),
        replacement_device TEXT CHECK (
            replacement_device IS NULL OR (
                length(replacement_device) BETWEEN 1 AND 32
                AND replacement_device NOT GLOB '*[^0-9]*'
            )
        ),
        replacement_inode TEXT CHECK (
            replacement_inode IS NULL OR (
                length(replacement_inode) BETWEEN 1 AND 32
                AND replacement_inode NOT GLOB '*[^0-9]*'
            )
        ),
        rollback_device TEXT CHECK (
            rollback_device IS NULL OR (
                length(rollback_device) BETWEEN 1 AND 32
                AND rollback_device NOT GLOB '*[^0-9]*'
            )
        ),
        rollback_inode TEXT CHECK (
            rollback_inode IS NULL OR (
                length(rollback_inode) BETWEEN 1 AND 32
                AND rollback_inode NOT GLOB '*[^0-9]*'
            )
        ),
        key_version TEXT CHECK (key_version IS NULL OR (
            length(key_version) BETWEEN 1 AND 120
            AND key_version = lower(key_version)
            AND substr(key_version, 1, 1) GLOB '[a-z]'
            AND key_version NOT GLOB '*[^a-z0-9.-]*'
            AND key_version NOT GLOB '*..*' AND key_version NOT GLOB '*--*'
            AND substr(key_version, -1, 1) GLOB '[a-z0-9]'
        )),
        wrapped_key TEXT CHECK (wrapped_key IS NULL OR (
            length(wrapped_key) = 96 AND wrapped_key = lower(wrapped_key)
            AND wrapped_key NOT GLOB '*[^0-9a-f]*'
        )),
        wrap_nonce TEXT CHECK (wrap_nonce IS NULL OR (
            length(wrap_nonce) = 48 AND wrap_nonce = lower(wrap_nonce)
            AND wrap_nonce NOT GLOB '*[^0-9a-f]*'
        )),
        ciphertext_byte_length INTEGER CHECK (
            ciphertext_byte_length IS NULL
            OR ciphertext_byte_length BETWEEN 45 AND 9007199254740991
        ),
        failure_code TEXT CHECK (failure_code IS NULL OR (
            length(failure_code) BETWEEN 1 AND 120
            AND failure_code = lower(failure_code)
            AND failure_code NOT GLOB '*[^a-z0-9.-]*'
        )),
        started_at TEXT NOT NULL CHECK (
            length(started_at) = 24 AND substr(started_at, 5, 1) = '-'
            AND substr(started_at, 8, 1) = '-' AND substr(started_at, 11, 1) = 'T'
            AND substr(started_at, 14, 1) = ':' AND substr(started_at, 17, 1) = ':'
            AND substr(started_at, 20, 1) = '.' AND substr(started_at, 24, 1) = 'Z'
            AND started_at NOT GLOB '*[^0-9TZ:.-]*'
        ),
        updated_at TEXT NOT NULL CHECK (
            length(updated_at) = 24 AND substr(updated_at, 5, 1) = '-'
            AND substr(updated_at, 8, 1) = '-' AND substr(updated_at, 11, 1) = 'T'
            AND substr(updated_at, 14, 1) = ':' AND substr(updated_at, 17, 1) = ':'
            AND substr(updated_at, 20, 1) = '.' AND substr(updated_at, 24, 1) = 'Z'
            AND updated_at NOT GLOB '*[^0-9TZ:.-]*'
        ),
        PRIMARY KEY (object_sha256, project_id),
        FOREIGN KEY (object_sha256, project_id)
            REFERENCES object_records (object_sha256, project_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT,
        CHECK ((source_device IS NULL) = (source_inode IS NULL)),
        CHECK ((replacement_device IS NULL) = (replacement_inode IS NULL)),
        CHECK ((rollback_device IS NULL) = (rollback_inode IS NULL)),
        CHECK (
            (key_version IS NULL AND wrapped_key IS NULL AND wrap_nonce IS NULL
             AND ciphertext_byte_length IS NULL)
            OR
            (key_version IS NOT NULL AND wrapped_key IS NOT NULL AND wrap_nonce IS NOT NULL
             AND ciphertext_byte_length IS NOT NULL)
        ),
        CHECK (updated_at >= started_at)
    ) STRICT
"""

MATERIAL_MIGRATION_STEPS = (
    "upgrade-journal-create",
    "legacy-object-backfill",
    "metadata-trigger-removal",
    "metadata-v3-rename",
    "metadata-v4-create",
    "metadata-v4-copy",
    "metadata-v3-drop",
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
    bind = operations.get_bind()
    if bind is None:
        raise ValueError("online migration connection is required")
    operations.execute(OBJECT_ENVELOPE_UPGRADES_DDL)
    _migration_step_completed("upgrade-journal-create")
    bind.execute(
        text(
            """
            INSERT INTO object_envelope_upgrades (
                object_sha256, project_id, phase, started_at, updated_at
            )
            SELECT object.object_sha256, object.project_id, 'legacy-detected', :applied_at, :applied_at
              FROM object_records AS object
             WHERE object.envelope_version='plaintext-fixture-v1'
               AND EXISTS (
                   SELECT 1 FROM schema_migrations AS history
                    WHERE history.migration_id='0003_object_envelopes'
               )
            """
        ),
        {"applied_at": parameters["applied_at"]},
    )
    _migration_step_completed("legacy-object-backfill")
    operations.execute("DROP TRIGGER schema_metadata_no_update")
    operations.execute("DROP TRIGGER schema_metadata_no_delete")
    _migration_step_completed("metadata-trigger-removal")
    operations.rename_table("schema_metadata", "schema_metadata_v3")
    _migration_step_completed("metadata-v3-rename")
    operations.execute(SCHEMA_METADATA_V4_DDL)
    _migration_step_completed("metadata-v4-create")
    bind.execute(
        text(
            """
            INSERT INTO schema_metadata (
                singleton, schema_version, database_profile, application_id,
                profile_sha256, schema_sha256, created_at
            )
            SELECT singleton, 4, database_profile, application_id,
                   :profile_sha256, :schema_sha256, created_at
            FROM schema_metadata_v3
            """
        ),
        {"profile_sha256": TARGET_PROFILE_SHA256, "schema_sha256": TARGET_SCHEMA_SHA256},
    )
    _migration_step_completed("metadata-v4-copy")
    operations.drop_table("schema_metadata_v3")
    _migration_step_completed("metadata-v3-drop")
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
                :migration_id, 3, 4, :applied_at, :backup_manifest_sha256,
                :source_schema_sha256, :target_schema_sha256, 'alembic-1.18.5'
            )
            """
        ),
        parameters,
    )
    _migration_step_completed("migration-history-insert")
    operations.execute("PRAGMA user_version=4")
    _migration_step_completed("user-version-advance")


def upgrade() -> None:
    from alembic import op

    parameters = op.get_context().opts.get("research_observatory_parameters")
    if not isinstance(parameters, dict):
        raise ValueError("governed migration parameters are required")
    apply(cast(Operations, op), parameters)


def downgrade() -> None:
    raise NotImplementedError("forward-only migration; restore the verified pre-migration backup")
