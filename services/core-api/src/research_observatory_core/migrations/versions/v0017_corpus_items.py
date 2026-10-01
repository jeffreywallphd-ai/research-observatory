"""Widen the common aggregate authority for v2 CorpusItem and retain v16 rows."""

from typing import Any, cast

from alembic.operations import Operations
from sqlalchemy import text

revision = "0017_corpus_items"
down_revision = "0016_work_versions"
source_schema_version = 16
target_schema_version = 17
TARGET_SCHEMA_SHA256 = "719d520126380b3807e657ed080b5ca1b22190dda1b9d7204091d34d4e9049b3"
TARGET_PROFILE_SHA256 = "ceba26263dec5f1afb5a7a0a2e9587bf7eb99bf9a69ed2da35e42dec4c78c002"
MATERIAL_MIGRATION_STEPS = (
    "common-v16-snapshot",
    "common-v16-drop",
    "common-v17-create",
    "common-v17-copy",
    "common-v17-authority-create",
    "impact-v16-snapshot",
    "impact-v16-drop",
    "impact-v17-create",
    "impact-v17-copy",
    "impact-v17-authority-create",
    "corpus-authority-create",
    "metadata-v16-authority-drop",
    "metadata-v16-rename",
    "metadata-v17-create",
    "metadata-v17-copy",
    "metadata-v16-drop",
    "migration-history-insert",
    "user-version-advance",
)


def _migration_step_completed(_step: str) -> None:
    """Deterministic interruption seam for rollback and verified-backup tests."""


def apply(operations: Operations, parameters: dict[str, Any]) -> None:
    if parameters.get("targetSchemaSha256") != TARGET_SCHEMA_SHA256:
        raise ValueError("migration target schema authority mismatch")
    if parameters.get("targetProfileSha256") != TARGET_PROFILE_SHA256:
        raise ValueError("migration target profile authority mismatch")
    bind = operations.get_bind()
    if bind is None:
        raise ValueError("online migration connection is required")
    if bind.exec_driver_sql("PRAGMA foreign_keys").scalar_one() != 0:
        raise ValueError("v17 common-table rebuild requires migration-only foreign key suspension")

    # Keep the original names out of ALTER TABLE RENAME: SQLite would rewrite
    # child references to a historical parent name. Temporary row snapshots
    # let us recreate the canonical DDL verbatim in one rollbackable transaction.
    operations.execute("CREATE TEMP TABLE corpus_v16_identities AS SELECT * FROM aggregate_identities")
    operations.execute("CREATE TEMP TABLE corpus_v16_revisions AS SELECT * FROM aggregate_revisions")
    _migration_step_completed("common-v16-snapshot")
    operations.execute("DROP TABLE aggregate_revisions")
    operations.execute("DROP TABLE aggregate_identities")
    _migration_step_completed("common-v16-drop")
    operations.execute(parameters["aggregateIdentitiesDdl"])
    operations.execute(parameters["aggregateRevisionsDdl"])
    _migration_step_completed("common-v17-create")
    operations.execute(
        "INSERT INTO aggregate_identities (aggregate_id,project_id,aggregate_kind,created_at) "
        "SELECT aggregate_id,project_id,aggregate_kind,created_at FROM corpus_v16_identities"
    )
    operations.execute(
        "INSERT INTO aggregate_revisions (revision_id,aggregate_id,aggregate_kind,project_id,revision,"
        "contract_version,created_at,modified_at,display_label_observed,display_label_normalized,"
        "knowledge_status,rights_status) "
        "SELECT revision_id,aggregate_id,aggregate_kind,project_id,revision,contract_version,"
        "created_at,modified_at,display_label_observed,display_label_normalized,knowledge_status,rights_status "
        "FROM corpus_v16_revisions"
    )
    operations.execute("DROP TABLE corpus_v16_revisions")
    operations.execute("DROP TABLE corpus_v16_identities")
    _migration_step_completed("common-v17-copy")
    for statement in parameters["commonAuthority"]:
        operations.execute(statement)
    _migration_step_completed("common-v17-authority-create")
    operations.execute("CREATE TEMP TABLE corpus_v16_impact_items AS SELECT * FROM dependency_impact_items")
    _migration_step_completed("impact-v16-snapshot")
    operations.execute("DROP TABLE dependency_impact_items")
    _migration_step_completed("impact-v16-drop")
    operations.execute(parameters["impactItemsDdl"])
    _migration_step_completed("impact-v17-create")
    operations.execute(
        "INSERT INTO dependency_impact_items (item_id,run_id,item_sequence,project_id,output_revision_id,"
        "output_kind,disposition,depth,relation_type,path_json,path_sha256,path_length,path_truncated,"
        "cycle_group_id,confidence,review_required,created_at) "
        "SELECT item_id,run_id,item_sequence,project_id,output_revision_id,output_kind,disposition,depth,"
        "relation_type,path_json,path_sha256,path_length,path_truncated,cycle_group_id,confidence,"
        "review_required,created_at FROM corpus_v16_impact_items"
    )
    operations.execute("DROP TABLE corpus_v16_impact_items")
    _migration_step_completed("impact-v17-copy")
    for statement in parameters["impactAuthority"]:
        operations.execute(statement)
    _migration_step_completed("impact-v17-authority-create")
    for statement in parameters["corpusAuthority"]:
        operations.execute(statement)
    _migration_step_completed("corpus-authority-create")

    operations.execute("DROP TRIGGER schema_metadata_no_update")
    operations.execute("DROP TRIGGER schema_metadata_no_delete")
    _migration_step_completed("metadata-v16-authority-drop")
    operations.rename_table("schema_metadata", "schema_metadata_v16")
    _migration_step_completed("metadata-v16-rename")
    operations.execute(parameters["schemaMetadataDdl"])
    _migration_step_completed("metadata-v17-create")
    bind.execute(
        text(
            "INSERT INTO schema_metadata SELECT singleton,17,database_profile,application_id,"
            ":profile,:schema,created_at FROM schema_metadata_v16"
        ),
        {"profile": TARGET_PROFILE_SHA256, "schema": TARGET_SCHEMA_SHA256},
    )
    _migration_step_completed("metadata-v17-copy")
    operations.drop_table("schema_metadata_v16")
    _migration_step_completed("metadata-v16-drop")
    for statement in parameters["schemaMetadataTriggers"]:
        operations.execute(statement)
    bind.execute(
        text(
            "INSERT INTO schema_migrations (migration_id,from_schema_version,to_schema_version,applied_at,"
            "backup_manifest_sha256,source_schema_sha256,target_schema_sha256,migration_tool) "
            "VALUES (:migration_id,16,17,:applied_at,:backup_manifest_sha256,:source_schema_sha256,"
            ":target_schema_sha256,'alembic-1.18.5')"
        ),
        parameters,
    )
    _migration_step_completed("migration-history-insert")
    operations.execute("PRAGMA user_version=17")
    _migration_step_completed("user-version-advance")


def upgrade() -> None:
    from alembic import op

    parameters = op.get_context().opts.get("research_observatory_parameters")
    if not isinstance(parameters, dict):
        raise ValueError("governed migration parameters are required")
    apply(cast(Operations, op), parameters)


def downgrade() -> None:
    raise NotImplementedError("forward-only migration; restore the verified pre-migration backup")
