"""Add protected action-rights policy authority without rewriting v17 history."""

from typing import Any, cast

from alembic.operations import Operations
from sqlalchemy import text

revision = "0018_rights_policy"
down_revision = "0017_corpus_items"
source_schema_version = 17
target_schema_version = 18
TARGET_SCHEMA_SHA256 = "a9812a5fad0394652a070b3fd8466961eb3e88a928965d56e89d57008b89b503"
TARGET_PROFILE_SHA256 = "4617f88a662f50b6286f399158ca4477e2cad34bad68033be99149cbdfb4ed30"
MATERIAL_MIGRATION_STEPS = (
    "rights-subjects-create",
    "rights-revisions-create",
    "rights-rechecks-create",
    "rights-scopes-create",
    "rights-completions-create",
    "rights-generic-rechecks-create",
    "rights-legacy-rechecks-create",
    "rights-use-decisions-create",
    "rights-authority-create",
    "rights-legacy-rechecks-populated",
    "metadata-v17-authority-drop",
    "metadata-v17-rename",
    "metadata-v18-create",
    "metadata-v18-copy",
    "metadata-v17-drop",
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
    if bind is None:
        raise ValueError("online migration connection is required")
    if bind.exec_driver_sql("PRAGMA foreign_keys").scalar_one() != 0:
        raise ValueError("v18 rights migration requires the dedicated migration connection")

    for statement in parameters["rightsAuthority"]:
        operations.execute(statement)
        if "CREATE TABLE rights_policy_subjects" in statement:
            _migration_step_completed("rights-subjects-create")
        elif "CREATE TABLE rights_policy_revisions" in statement:
            _migration_step_completed("rights-revisions-create")
        elif "CREATE TABLE rights_policy_rechecks" in statement:
            _migration_step_completed("rights-rechecks-create")
        elif "CREATE TABLE rights_policy_recheck_scopes" in statement:
            _migration_step_completed("rights-scopes-create")
        elif "CREATE TABLE rights_policy_recheck_completions" in statement:
            _migration_step_completed("rights-completions-create")
        elif "CREATE TABLE rights_policy_generic_rechecks" in statement:
            _migration_step_completed("rights-generic-rechecks-create")
        elif "CREATE TABLE rights_legacy_output_rechecks" in statement:
            _migration_step_completed("rights-legacy-rechecks-create")
        elif "CREATE TABLE rights_use_decisions" in statement:
            _migration_step_completed("rights-use-decisions-create")
    _migration_step_completed("rights-authority-create")
    bind.execute(
        text(
            "INSERT INTO rights_legacy_output_rechecks "
            "(project_id,item_id,path_id,output_revision_id,source_assertion_revision_id,"
            "reason,disposition,detected_at) "
            "SELECT membership.project_id,membership.item_id,membership.path_id,membership.revision_id,"
            "(SELECT CASE WHEN COUNT(*)=1 THEN MIN(a.revision_id) ELSE NULL END "
            "FROM reconciliation_assertions AS a WHERE a.project_id=path.project_id AND ("
            "(path.kind IN ('import-member','connector-record') "
            "AND path.source_revision_id=a.source_revision_id "
            "AND path.kind=json_extract(a.assertion_json,'$.address.kind') "
            "AND path.context_id=json_extract(a.assertion_json,'$.address.contextId') "
            "AND path.context_revision_id=json_extract(a.assertion_json,'$.address.revisionId') "
            "AND path.ordinal IS json_extract(a.assertion_json,'$.address.ordinal') "
            "AND path.record_key_sha256 IS json_extract(a.assertion_json,'$.address.recordKey')) "
            "OR (path.kind='citation' AND path.source_revision_id=a.revision_id))),"
            "'RIGHTS_POLICY','requires-review',:applied_at "
            "FROM corpus_item_discovery_paths AS membership "
            "JOIN corpus_discovery_paths AS path ON path.path_id=membership.path_id "
            "AND path.project_id=membership.project_id AND path.item_id=membership.item_id "
            "WHERE path.direction='source-to-corpus-item'"
        ),
        {"applied_at": parameters["applied_at"]},
    )
    _migration_step_completed("rights-legacy-rechecks-populated")

    operations.execute("DROP TRIGGER schema_metadata_no_update")
    operations.execute("DROP TRIGGER schema_metadata_no_delete")
    _migration_step_completed("metadata-v17-authority-drop")
    operations.rename_table("schema_metadata", "schema_metadata_v17")
    _migration_step_completed("metadata-v17-rename")
    operations.execute(parameters["schemaMetadataDdl"])
    _migration_step_completed("metadata-v18-create")
    bind.execute(
        text(
            "INSERT INTO schema_metadata SELECT singleton,18,database_profile,application_id,"
            ":profile,:schema,created_at FROM schema_metadata_v17"
        ),
        {"profile": TARGET_PROFILE_SHA256, "schema": TARGET_SCHEMA_SHA256},
    )
    _migration_step_completed("metadata-v18-copy")
    operations.drop_table("schema_metadata_v17")
    _migration_step_completed("metadata-v17-drop")
    for statement in parameters["schemaMetadataTriggers"]:
        operations.execute(statement)
    bind.execute(
        text(
            "INSERT INTO schema_migrations (migration_id,from_schema_version,to_schema_version,applied_at,"
            "backup_manifest_sha256,source_schema_sha256,target_schema_sha256,migration_tool) "
            "VALUES (:migration_id,17,18,:applied_at,:backup_manifest_sha256,:source_schema_sha256,"
            ":target_schema_sha256,'alembic-1.18.5')"
        ),
        parameters,
    )
    _migration_step_completed("migration-history-insert")
    operations.execute("PRAGMA user_version=18")
    _migration_step_completed("user-version-advance")


def upgrade() -> None:
    from alembic import op

    parameters = op.get_context().opts.get("research_observatory_parameters")
    if not isinstance(parameters, dict):
        raise ValueError("governed migration parameters are required")
    apply(cast(Operations, op), parameters)


def downgrade() -> None:
    raise NotImplementedError("forward-only migration; restore the verified pre-migration backup")
