"""Additive typed lexical observations; the published v29 DDL stays unchanged."""

from .canonical_schema import _hash, _utc, _uuid

TABLES = (
    "search_lexical_jobs",
    "search_input_manifests",
    "search_lexical_runs",
    "search_observation_events",
    "search_source_epochs",
)
IMMUTABLE_TABLES = TABLES
REVISION_EVENT = "org.research-observatory.workflow.revision-recorded.v1"
_REQUEST_KEYS = (
    "schemaVersion",
    "projectId",
    "commandId",
    "actorId",
    "sessionId",
    "intent",
    "policySha256",
    "queryDocument",
    "filters",
    "rankingVersion",
    "fieldWeights",
)
_MANIFEST_KEYS = (
    "schemaVersion",
    "kind",
    "projectId",
    "jobId",
    "inputSha256",
    "level",
    "ordinal",
    "sourceRevisionIds",
)
_RUN_KEYS = (
    "schemaVersion",
    "kind",
    "searchRunId",
    "projectId",
    "jobId",
    "attemptId",
    "requestSha256",
    "request",
    "inputs",
    "sourceRoots",
    "resultCount",
    "resultSha256",
    "executedAt",
    "semanticState",
    "rerankState",
)


def _body(column: str, keys: tuple[str, ...], limit: int = 1048576) -> str:
    paths = ",".join("'$." + key + "'" for key in keys)
    return (
        f"json_valid({column}) AND length(CAST({column} AS BLOB)) BETWEEN 2 AND {limit} "
        f"AND json_type({column}) IS 'object' AND json_extract({column},'$.schemaVersion') IS '1.0' "
        f"AND json_remove({column},{paths})='{{}}'"
    )


TABLE_DDL = (
    """CREATE TABLE search_source_epochs (
        sequence INTEGER PRIMARY KEY AUTOINCREMENT CHECK(sequence BETWEEN 1 AND 9007199254740991),
        project_id TEXT NOT NULL,
        source_kind TEXT NOT NULL CHECK(source_kind IN (
            'import-draft','import-decision','import-state','object-state')),
        source_identity TEXT NOT NULL,
        FOREIGN KEY(project_id) REFERENCES projects(project_id)
    ) STRICT""",
    f"""
    CREATE TABLE search_lexical_jobs (
        job_id TEXT PRIMARY KEY CHECK({_uuid("job_id")}),
        project_id TEXT NOT NULL,
        command_id TEXT NOT NULL CHECK({_uuid("command_id")}),
        input_json TEXT NOT NULL CHECK({_body("input_json", _REQUEST_KEYS)}
            AND json_extract(input_json,'$.projectId') IS project_id
            AND json_extract(input_json,'$.commandId') IS command_id
            AND json_extract(input_json,'$.actorId') IS actor_id
            AND json_extract(input_json,'$.sessionId') IS session_id
            AND json_type(input_json,'$.queryDocument') IS 'text'
            AND json_extract(input_json,'$.rankingVersion') IS 'ro-lexical-best-row-per-leaf-bm25-1'),
        input_sha256 TEXT NOT NULL CHECK({_hash("input_sha256")}),
        actor_id TEXT NOT NULL CHECK({_uuid("actor_id")}),
        session_id TEXT NOT NULL CHECK({_hash("session_id", 32)}),
        created_at TEXT NOT NULL CHECK({_utc("created_at")}),
        UNIQUE(project_id,command_id), UNIQUE(job_id,project_id),
        FOREIGN KEY(job_id) REFERENCES workflow_queue_jobs(job_id),
        FOREIGN KEY(project_id) REFERENCES projects(project_id)
    ) STRICT
    """,
    f"""
    CREATE TABLE search_input_manifests (
        revision_id TEXT PRIMARY KEY CHECK({_uuid("revision_id")}),
        project_id TEXT NOT NULL,
        aggregate_kind TEXT NOT NULL DEFAULT 'workflow' CHECK(aggregate_kind='workflow'),
        job_id TEXT NOT NULL,
        payload_sha256 TEXT NOT NULL CHECK({_hash("payload_sha256")}),
        manifest_json TEXT NOT NULL CHECK({_body("manifest_json", _MANIFEST_KEYS)}
            AND json_extract(manifest_json,'$.kind') IS 'lexical-input-manifest'
            AND json_extract(manifest_json,'$.projectId') IS project_id
            AND json_extract(manifest_json,'$.jobId') IS job_id
            AND json_type(manifest_json,'$.sourceRevisionIds') IS 'array'
            AND json_array_length(manifest_json,'$.sourceRevisionIds') BETWEEN 1 AND 60),
        UNIQUE(revision_id,project_id),
        FOREIGN KEY(revision_id,aggregate_kind,project_id)
            REFERENCES aggregate_revisions(revision_id,aggregate_kind,project_id),
        FOREIGN KEY(job_id,project_id) REFERENCES search_lexical_jobs(job_id,project_id)
    ) STRICT
    """,
    f"""
    CREATE TABLE search_lexical_runs (
        revision_id TEXT PRIMARY KEY CHECK({_uuid("revision_id")}),
        project_id TEXT NOT NULL,
        aggregate_kind TEXT NOT NULL DEFAULT 'workflow' CHECK(aggregate_kind='workflow'),
        job_id TEXT NOT NULL,
        search_run_id TEXT NOT NULL CHECK({_uuid("search_run_id")}),
        payload_sha256 TEXT NOT NULL CHECK({_hash("payload_sha256")}),
        run_json TEXT NOT NULL CHECK({_body("run_json", _RUN_KEYS)}
            AND json_extract(run_json,'$.kind') IS 'lexical-search-run'
            AND json_extract(run_json,'$.projectId') IS project_id
            AND json_extract(run_json,'$.jobId') IS job_id
            AND json_extract(run_json,'$.searchRunId') IS search_run_id
            AND json_type(run_json,'$.sourceRoots') IS 'array'
            AND json_array_length(run_json,'$.sourceRoots') BETWEEN 0 AND 60
            AND json_extract(run_json,'$.semanticState') IS 'unqualified'
            AND json_extract(run_json,'$.rerankState') IS 'not-run'),
        UNIQUE(project_id,job_id), UNIQUE(revision_id,project_id), UNIQUE(search_run_id,project_id),
        FOREIGN KEY(revision_id,aggregate_kind,project_id)
            REFERENCES aggregate_revisions(revision_id,aggregate_kind,project_id),
        FOREIGN KEY(job_id,project_id) REFERENCES search_lexical_jobs(job_id,project_id)
    ) STRICT
    """,
    f"""
    CREATE TABLE search_observation_events (
        outbox_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        revision_id TEXT NOT NULL,
        record_sha256 TEXT NOT NULL CHECK({_hash("record_sha256")}),
        node_sha256 TEXT NOT NULL CHECK({_hash("node_sha256")}),
        kind TEXT NOT NULL CHECK(kind IN ('node-created','job-completed')),
        FOREIGN KEY(outbox_id) REFERENCES outbox_events(outbox_id),
        FOREIGN KEY(project_id) REFERENCES projects(project_id)
    ) STRICT
    """,
)

# This predicate is checked on classification AND consumption. Exact canonical
# subtype/output bindings distinguish observation from a real lexical input;
# names, NULL revisions and the workflow namespace alone confer no exclusion.
VALID_OBSERVATION = f"""
EXISTS(SELECT 1 FROM outbox_events o JOIN aggregate_revisions a
    ON a.revision_id=o.revision_id AND a.project_id=o.project_id AND a.aggregate_kind='workflow'
    WHERE o.outbox_id=e.outbox_id AND o.project_id=e.project_id AND o.revision_id=e.revision_id
        AND o.record_sha256=e.record_sha256 AND (
        (e.kind='node-created' AND (
            (o.event_type='{REVISION_EVENT}' AND EXISTS(SELECT 1 FROM search_input_manifests m
                WHERE m.revision_id=e.revision_id AND m.project_id=e.project_id AND m.payload_sha256=e.node_sha256))
            OR (o.event_type='{REVISION_EVENT}' AND EXISTS(SELECT 1 FROM search_lexical_runs r
                WHERE r.revision_id=e.revision_id AND r.project_id=e.project_id AND r.payload_sha256=e.node_sha256
                    AND r.search_run_id=a.aggregate_id))))
        OR (e.kind='job-completed' AND o.event_type='org.research-observatory.workflow.job-succeeded.v1'
            AND EXISTS(SELECT 1 FROM search_lexical_runs r JOIN workflow_committed_outputs w
                ON w.job_id=r.job_id AND w.project_id=r.project_id AND w.outbox_id=o.outbox_id
                WHERE r.revision_id=e.revision_id AND r.project_id=e.project_id AND r.payload_sha256=e.node_sha256
                    AND r.search_run_id=a.aggregate_id AND json_array_length(w.output_manifest_json,'$.outputs')=1
                    AND json_extract(w.output_manifest_json,'$.outputs[0].revisionId') IS r.revision_id
                    AND json_extract(w.output_manifest_json,'$.outputs[0].artifactId') IS r.search_run_id
                    AND json_extract(w.output_manifest_json,'$.outputs[0].provenanceEntityId') IS r.search_run_id
                    AND json_extract(w.output_manifest_json,'$.outputs[0].mediaType') IS
                        'application/vnd.research-observatory.lexical-search-run+json'))))
"""

BINDING_DDL = (
    *(
        f"CREATE TRIGGER search_source_{name}_insert AFTER INSERT ON {table} "
        f"BEGIN INSERT INTO search_source_epochs(project_id,source_kind,source_identity) "
        f"VALUES(NEW.project_id,'{kind}',NEW.{identity}); END"
        for name, table, kind, identity in (
            ("draft", "import_draft_revisions", "import-draft", "preview_id"),
            ("decision", "import_record_decisions", "import-decision", "preview_id"),
            ("import_state", "import_preview_events", "import-state", "preview_id"),
            ("object", "object_records", "object-state", "object_sha256"),
        )
    ),
    """CREATE TRIGGER search_source_object_update AFTER UPDATE ON object_records
    WHEN (OLD.project_id,OLD.object_sha256,OLD.byte_length,OLD.media_type,OLD.rights_status,
          OLD.protection_profile,OLD.retention_class,OLD.storage_state,OLD.envelope_version,
          OLD.key_version,OLD.wrapped_key,OLD.wrap_nonce,OLD.ciphertext_byte_length)
      IS NOT (NEW.project_id,NEW.object_sha256,NEW.byte_length,NEW.media_type,NEW.rights_status,
          NEW.protection_profile,NEW.retention_class,NEW.storage_state,NEW.envelope_version,
          NEW.key_version,NEW.wrapped_key,NEW.wrap_nonce,NEW.ciphertext_byte_length)
    BEGIN INSERT INTO search_source_epochs(project_id,source_kind,source_identity)
        VALUES(OLD.project_id,'object-state',OLD.object_sha256);
        INSERT INTO search_source_epochs(project_id,source_kind,source_identity)
        SELECT NEW.project_id,'object-state',NEW.object_sha256 WHERE NEW.project_id<>OLD.project_id; END""",
    """CREATE TRIGGER search_source_object_delete AFTER DELETE ON object_records
    BEGIN INSERT INTO search_source_epochs(project_id,source_kind,source_identity)
        VALUES(OLD.project_id,'object-state',OLD.object_sha256); END""",
    """CREATE TRIGGER search_lexical_job_binding BEFORE INSERT ON search_lexical_jobs
    WHEN NOT EXISTS(SELECT 1 FROM workflow_queue_jobs j WHERE j.job_id=NEW.job_id
        AND j.project_id=NEW.project_id AND j.activity_type='lexical-search')
    BEGIN SELECT RAISE(ABORT,'search job authority mismatch'); END""",
    """CREATE TRIGGER search_input_manifest_binding BEFORE INSERT ON search_input_manifests
    WHEN EXISTS(SELECT 1 FROM json_each(NEW.manifest_json,'$.sourceRevisionIds') s
        WHERE s.type<>'text' OR NOT EXISTS(SELECT 1 FROM aggregate_revisions a
            WHERE a.revision_id=s.value AND a.project_id=NEW.project_id))
      OR (SELECT count(*) FROM json_each(NEW.manifest_json,'$.sourceRevisionIds'))<>
         (SELECT count(DISTINCT value) FROM json_each(NEW.manifest_json,'$.sourceRevisionIds'))
    BEGIN SELECT RAISE(ABORT,'search manifest source mismatch'); END""",
    """CREATE TRIGGER search_lexical_run_binding BEFORE INSERT ON search_lexical_runs
    WHEN NOT EXISTS(SELECT 1 FROM aggregate_revisions a WHERE a.revision_id=NEW.revision_id
        AND a.project_id=NEW.project_id AND a.aggregate_id=NEW.search_run_id)
      OR NOT EXISTS(SELECT 1 FROM search_lexical_jobs j WHERE j.job_id=NEW.job_id AND j.project_id=NEW.project_id
        AND json_extract(NEW.run_json,'$.requestSha256') IS j.input_sha256
        AND json_extract(NEW.run_json,'$.request')=json(j.input_json))
      OR EXISTS(SELECT 1 FROM json_each(NEW.run_json,'$.sourceRoots') s
        WHERE s.type<>'text' OR NOT EXISTS(SELECT 1 FROM aggregate_revisions a
            WHERE a.revision_id=s.value AND a.project_id=NEW.project_id))
    BEGIN SELECT RAISE(ABORT,'search run authority mismatch'); END""",
    "CREATE TRIGGER search_observation_event_binding BEFORE INSERT ON search_observation_events WHEN NOT ("
    + VALID_OBSERVATION.replace("e.", "NEW.")
    + ") BEGIN SELECT RAISE(ABORT,'search observation authority mismatch'); END",
)

IMMUTABILITY_DDL = tuple(
    f"CREATE TRIGGER {table}_no_{operation} BEFORE {operation.upper()} ON {table} "
    "BEGIN SELECT RAISE(ABORT,'search observation history is append-only'); END"
    for table in IMMUTABLE_TABLES
    for operation in ("update", "delete")
)
INDEX_DDL = (
    "CREATE INDEX search_source_epochs_project ON search_source_epochs(project_id,sequence)",
    "CREATE INDEX search_input_manifests_job ON search_input_manifests(project_id,job_id)",
    "CREATE INDEX search_observation_events_revision ON search_observation_events(project_id,revision_id)",
)
DDL = (*TABLE_DDL, *BINDING_DDL, *IMMUTABILITY_DDL, *INDEX_DDL)
