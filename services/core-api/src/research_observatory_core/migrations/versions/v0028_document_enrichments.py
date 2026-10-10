"""Add immutable, indexed document enrichments; retain all exact v27 history."""

from typing import Any, cast

from alembic.operations import Operations
from sqlalchemy import text

revision = "0028_document_enrichments"
down_revision = "0027_revision_invalidations"
source_schema_version = 27
target_schema_version = 28
TARGET_SCHEMA_SHA256 = "3f29b29cface11d5355f704c943459243fc7f9d0baf07725747c73547b1e4cb6"
TARGET_PROFILE_SHA256 = "6cc9fc713678dcbaab23bd922a4010098cbd05922932a4b5f4840967f8f377e6"
TABLES = (
    "document_enrichments",
    "document_enrichment_elements",
    "document_enrichment_identifiers",
    "document_enrichment_targets",
)

_TABLE_DDL = (
    (
        "\n    CREATE TABLE document_enrichments (\n        revision_id TEXT PRIMARY "
        "KEY,\n        project_id TEXT NOT NULL,\n        collection_id TEXT NOT "
        "NULL,\n        document_revision_id TEXT NOT NULL,\n        enrichment_kind "
        "TEXT NOT NULL CHECK (enrichment_kind IN "
        "('references','citation-contexts','table-figures')),\n        "
        "previous_revision_id TEXT,\n        command_id TEXT NOT NULL,\n        "
        "command_sha256 TEXT NOT NULL CHECK (length(command_sha256)=64 AND "
        "command_sha256 NOT GLOB '*[^0-9a-f]*'),\n        actor_id TEXT NOT NULL,\n    "
        "    payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256)=64 AND "
        "payload_sha256 NOT GLOB '*[^0-9a-f]*'),\n        UNIQUE "
        "(revision_id,project_id),\n        UNIQUE (project_id,command_id),\n        "
        "FOREIGN KEY (revision_id,project_id) REFERENCES "
        "aggregate_revisions(revision_id,project_id) ON UPDATE RESTRICT ON DELETE "
        "RESTRICT,\n        FOREIGN KEY (collection_id) REFERENCES "
        "aggregate_identities(aggregate_id) ON UPDATE RESTRICT ON DELETE RESTRICT,\n  "
        "      FOREIGN KEY (document_revision_id,project_id) REFERENCES "
        "document_normalized_revisions(revision_id,project_id) ON UPDATE RESTRICT ON "
        "DELETE RESTRICT,\n        FOREIGN KEY (previous_revision_id,project_id) "
        "REFERENCES document_enrichments(revision_id,project_id) ON UPDATE RESTRICT "
        "ON DELETE RESTRICT,\n        FOREIGN KEY (project_id,payload_sha256) "
        "REFERENCES object_records(project_id,object_sha256) ON UPDATE RESTRICT ON "
        "DELETE RESTRICT\n    ) STRICT\n    "
    ),
    (
        "\n    CREATE TABLE document_enrichment_elements (\n        project_id TEXT "
        "NOT NULL,\n        collection_revision_id TEXT NOT NULL,\n        "
        "document_revision_id TEXT NOT NULL,\n        element_id TEXT NOT NULL,\n      "
        "  node_id TEXT NOT NULL,\n        element_order INTEGER NOT NULL CHECK "
        "(element_order BETWEEN 0 AND 999),\n        PRIMARY KEY "
        "(collection_revision_id,element_id),\n        UNIQUE "
        "(collection_revision_id,element_order),\n        UNIQUE "
        "(collection_revision_id,element_id,project_id),\n        FOREIGN KEY "
        "(collection_revision_id,project_id) REFERENCES "
        "document_enrichments(revision_id,project_id) ON UPDATE RESTRICT ON DELETE "
        "RESTRICT,\n        FOREIGN KEY (element_id,document_revision_id,project_id) "
        "REFERENCES document_structure_elements(element_id,revision_id,project_id) "
        "ON UPDATE RESTRICT ON DELETE RESTRICT,\n        FOREIGN KEY "
        "(node_id,document_revision_id,project_id) REFERENCES "
        "document_structure_elements(element_id,revision_id,project_id) ON UPDATE "
        "RESTRICT ON DELETE RESTRICT\n    ) STRICT\n    "
    ),
    (
        "\n    CREATE TABLE document_enrichment_identifiers (\n        project_id TEXT "
        "NOT NULL,\n        collection_revision_id TEXT NOT NULL,\n        element_id "
        "TEXT NOT NULL,\n        ordinal INTEGER NOT NULL CHECK (ordinal BETWEEN 0 "
        "AND 127),\n        scheme TEXT NOT NULL CHECK (length(scheme) BETWEEN 1 AND "
        "64 AND scheme NOT GLOB '*[^a-z0-9-]*'),\n        key_sha256 TEXT NOT NULL "
        "CHECK (length(key_sha256)=64 AND key_sha256 NOT GLOB '*[^0-9a-f]*'),\n       "
        " PRIMARY KEY (collection_revision_id,element_id,ordinal),\n        FOREIGN "
        "KEY (collection_revision_id,element_id,project_id) REFERENCES "
        "document_enrichment_elements(collection_revision_id,element_id,project_id) "
        "ON UPDATE RESTRICT ON DELETE RESTRICT\n    ) STRICT\n    "
    ),
    (
        "\n    CREATE TABLE document_enrichment_targets (\n        project_id TEXT NOT "
        "NULL,\n        collection_revision_id TEXT NOT NULL,\n        element_id TEXT "
        "NOT NULL,\n        ordinal INTEGER NOT NULL CHECK (ordinal BETWEEN 0 AND "
        "255),\n        work_id TEXT NOT NULL,\n        work_revision_id TEXT NOT "
        "NULL,\n        relation_type TEXT NOT NULL CHECK (relation_type IN "
        "('exact','candidate')),\n        score INTEGER NOT NULL CHECK (score BETWEEN "
        "0 AND 10000),\n        PRIMARY KEY "
        "(collection_revision_id,element_id,ordinal),\n        UNIQUE "
        "(collection_revision_id,element_id,work_id),\n        FOREIGN KEY "
        "(collection_revision_id,element_id,project_id) REFERENCES "
        "document_enrichment_elements(collection_revision_id,element_id,project_id) "
        "ON UPDATE RESTRICT ON DELETE RESTRICT,\n        FOREIGN KEY "
        "(work_revision_id,project_id) REFERENCES "
        "aggregate_revisions(revision_id,project_id) ON UPDATE RESTRICT ON DELETE "
        "RESTRICT\n    ) STRICT\n    "
    ),
)
_BINDING_DDL = (
    (
        "\n    CREATE TRIGGER document_enrichment_binding BEFORE INSERT ON "
        "document_enrichments\n    WHEN NOT EXISTS (SELECT 1 FROM aggregate_revisions "
        "r\n        JOIN documents d ON d.revision_id=r.revision_id AND "
        "d.project_id=r.project_id\n        JOIN object_records o ON "
        "o.project_id=d.project_id AND o.object_sha256=d.object_sha256\n        JOIN "
        "provenance_events p ON p.revision_id=r.revision_id AND "
        "p.project_id=r.project_id\n        JOIN material_dependency_outputs m ON "
        "m.output_revision_id=r.revision_id AND m.project_id=r.project_id\n        "
        "WHERE r.revision_id=NEW.revision_id AND r.project_id=NEW.project_id AND "
        "r.aggregate_id=NEW.collection_id\n            AND "
        "r.aggregate_kind='document' AND r.knowledge_status='inferred'\n            "
        "AND d.object_sha256=NEW.payload_sha256 AND "
        "o.protection_profile='project-encrypted-v1'\n            AND "
        "p.actor_type='human' AND p.actor_id=NEW.actor_id AND m.coverage='complete'\n "
        "           AND r.revision=CASE WHEN NEW.previous_revision_id IS NULL THEN 0 "
        "ELSE\n                (SELECT old.revision+1 FROM aggregate_revisions old "
        "WHERE old.revision_id=NEW.previous_revision_id AND "
        "old.project_id=NEW.project_id) END)\n      OR (NEW.previous_revision_id IS "
        "NOT NULL AND NOT EXISTS (SELECT 1 FROM document_enrichments prior\n        "
        "WHERE prior.revision_id=NEW.previous_revision_id AND "
        "prior.project_id=NEW.project_id\n            AND "
        "prior.collection_id=NEW.collection_id AND "
        "prior.document_revision_id=NEW.document_revision_id\n            AND "
        "prior.enrichment_kind=NEW.enrichment_kind))\n    BEGIN SELECT "
        "RAISE(ABORT,'document enrichment binding denied'); END\n    "
    ),
    (
        "\n    CREATE TRIGGER document_enrichment_element_binding BEFORE INSERT ON "
        "document_enrichment_elements\n    WHEN NOT EXISTS (SELECT 1 FROM "
        "document_enrichments c\n        JOIN document_structure_elements e ON "
        "e.revision_id=c.document_revision_id AND e.project_id=c.project_id\n        "
        "JOIN document_structure_elements n ON n.revision_id=e.revision_id AND "
        "n.project_id=e.project_id\n        WHERE "
        "c.revision_id=NEW.collection_revision_id AND c.project_id=NEW.project_id\n   "
        "         AND c.document_revision_id=NEW.document_revision_id AND "
        "e.element_id=NEW.element_id\n            AND n.element_id=NEW.node_id AND "
        "n.role='node' AND e.element_order=NEW.element_order\n            AND "
        "((c.enrichment_kind='references' AND e.role='reference' AND "
        "e.related_node_id=n.element_id)\n                OR "
        "(c.enrichment_kind='citation-contexts' AND e.role='citation' AND "
        "e.related_node_id=n.element_id)\n                OR "
        "(c.enrichment_kind='table-figures' AND e.role='node' AND "
        "e.element_id=n.element_id AND n.node_kind IN ('table','figure'))))\n    "
        "BEGIN SELECT RAISE(ABORT,'document enrichment element binding denied'); "
        "END\n    "
    ),
    (
        "\n"
        "    CREATE TRIGGER document_enrichment_target_binding BEFORE INSERT ON "
        "document_enrichment_targets\n"
        "    WHEN NOT EXISTS (SELECT 1 FROM aggregate_revisions r JOIN reconciliation_work_states s\n"
        "        ON s.revision_id=r.revision_id AND s.project_id=r.project_id\n"
        "        JOIN reconciliation_work_seals z ON z.work_revision_id=s.revision_id AND "
        "z.project_id=s.project_id\n"
        "        WHERE r.revision_id=NEW.work_revision_id AND r.project_id=NEW.project_id AND "
        "r.aggregate_id=NEW.work_id\n"
        "            AND r.aggregate_kind='record' AND s.disposition='active')\n"
        "    BEGIN SELECT RAISE(ABORT,'document enrichment target binding denied'); END\n"
        "    "
    ),
)
DDL = (
    *_TABLE_DDL,
    *_BINDING_DDL,
    *(
        f"CREATE TRIGGER {table}_no_{operation} BEFORE {operation.upper()} ON {table} "
        "BEGIN SELECT RAISE(ABORT,'document enrichment history is append-only'); END"
        for table in TABLES
        for operation in ("update", "delete")
    ),
    (
        "CREATE INDEX document_enrichments_document ON "
        "document_enrichments(project_id,document_revision_id,enrichment_kind)"
    ),
    (
        "CREATE INDEX document_enrichment_elements_order ON "
        "document_enrichment_elements(project_id,collection_revision_id,element_order"
        ")"
    ),
    (
        "CREATE INDEX document_enrichment_identifiers_key ON "
        "document_enrichment_identifiers(project_id,scheme,key_sha256)"
    ),
    (
        "CREATE INDEX document_enrichment_targets_work ON "
        "document_enrichment_targets(project_id,work_id,work_revision_id)"
    ),
)
MATERIAL_MIGRATION_STEPS = (
    *(f"enrichment-ddl-{index:02}" for index in range(len(DDL))),
    "metadata-v27-authority-drop",
    "metadata-v27-rename",
    "metadata-v28-create",
    "metadata-v28-copy",
    "metadata-v27-drop",
    "metadata-v28-authority-create",
    "migration-history-insert",
    "user-version-advance",
)


def _migration_step_completed(_step: str) -> None:
    """Deterministic interruption seam for exact predecessor rollback tests."""


def apply(operations: Operations, parameters: dict[str, Any]) -> None:
    if (
        parameters.get("targetSchemaSha256") != TARGET_SCHEMA_SHA256
        or parameters.get("targetProfileSha256") != TARGET_PROFILE_SHA256
    ):
        raise ValueError("migration target authority mismatch")
    bind = operations.get_bind()
    if bind is None or bind.exec_driver_sql("PRAGMA foreign_keys").scalar_one() != 0:
        raise ValueError("v28 enrichment requires the dedicated migration connection")
    for index, statement in enumerate(DDL):
        operations.execute(statement)
        _migration_step_completed(f"enrichment-ddl-{index:02}")
    operations.execute("DROP TRIGGER schema_metadata_no_update")
    operations.execute("DROP TRIGGER schema_metadata_no_delete")
    _migration_step_completed("metadata-v27-authority-drop")
    operations.rename_table("schema_metadata", "schema_metadata_v27")
    _migration_step_completed("metadata-v27-rename")
    operations.execute(parameters["schemaMetadataDdl"])
    _migration_step_completed("metadata-v28-create")
    bind.execute(
        text(
            "INSERT INTO schema_metadata SELECT "
            "singleton,28,database_profile,application_id,:profile,:schema,created_at "
            "FROM schema_metadata_v27"
        ),
        {"profile": TARGET_PROFILE_SHA256, "schema": TARGET_SCHEMA_SHA256},
    )
    _migration_step_completed("metadata-v28-copy")
    operations.drop_table("schema_metadata_v27")
    _migration_step_completed("metadata-v27-drop")
    for statement in parameters["schemaMetadataTriggers"]:
        operations.execute(statement)
    _migration_step_completed("metadata-v28-authority-create")
    bind.execute(
        text(
            "INSERT INTO schema_migrations "
            "(migration_id,from_schema_version,to_schema_version,applied_at,backup_manife"
            "st_sha256,source_schema_sha256,target_schema_sha256,migration_tool) VALUES "
            "(:migration_id,27,28,:applied_at,:backup_manifest_sha256,:source_schema_sha2"
            "56,:target_schema_sha256,'alembic-1.18.5')"
        ),
        parameters,
    )
    _migration_step_completed("migration-history-insert")
    operations.execute("PRAGMA user_version=28")
    _migration_step_completed("user-version-advance")


def upgrade() -> None:
    from alembic import op

    parameters = op.get_context().opts.get("research_observatory_parameters")
    if not isinstance(parameters, dict):
        raise ValueError("governed migration parameters are required")
    apply(cast(Operations, op), parameters)


def downgrade() -> None:
    raise NotImplementedError("forward-only migration; restore the verified pre-migration backup")
