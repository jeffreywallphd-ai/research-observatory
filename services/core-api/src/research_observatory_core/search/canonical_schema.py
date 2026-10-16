"""Additive canonical search authority; text remains only in protected derivatives."""

from __future__ import annotations

IMMUTABLE_TABLES = ("search_changes", "search_generations", "search_generation_events", "search_selections")
MUTABLE_TABLES = ("search_generation_leases",)
TABLES = (
    "search_changes",
    "search_generations",
    "search_generation_leases",
    "search_generation_events",
    "search_selections",
)
CONTROL_EVENTS = (
    "search.index-generation-created",
    "search.index-checkpoint",
    "search.index-incomplete",
    "search.index-selected",
    "search.index-retired",
    "search.index-lease-claimed",
)
# Exact content-free controller events cannot recursively schedule themselves.
# Every scholarly revision and every other event remains a source change.
_CONTROL_SQL = ",".join("'" + value + "'" for value in CONTROL_EVENTS)
SOURCE_EVENT_WHERE = "NOT (revision_id IS NULL AND event_type IN (" + _CONTROL_SQL + "))"


def _hash(column: str, length: int = 64) -> str:
    return f"length({column})={length} AND {column} NOT GLOB '*[^0-9a-f]*'"


def _uuid(column: str) -> str:
    return (
        f"length({column})=36 AND substr({column},9,1)='-' AND substr({column},14,1)='-' "
        f"AND substr({column},19,1)='-' AND substr({column},24,1)='-' "
        f"AND substr({column},15,1)='7' AND substr({column},20,1) IN ('8','9','a','b') "
        f"AND length(replace({column},'-',''))=32 AND replace({column},'-','') NOT GLOB '*[^0-9a-f]*'"
    )


def _utc(column: str) -> str:
    return (
        f"length({column})=24 AND substr({column},1,4) BETWEEN '0001' AND '9999' "
        f"AND strftime('%Y-%m-%dT%H:%M:%fZ',{column}) IS NOT NULL "
        f"AND strftime('%Y-%m-%dT%H:%M:%fZ',{column})={column}"
    )


TABLE_DDL = (
    f"""
    CREATE TABLE search_changes (
        sequence INTEGER PRIMARY KEY AUTOINCREMENT CHECK(sequence BETWEEN 1 AND 9007199254740991),
        project_id TEXT NOT NULL,
        outbox_id TEXT NOT NULL UNIQUE,
        revision_id TEXT,
        event_type TEXT NOT NULL,
        occurred_at TEXT NOT NULL CHECK({_utc("occurred_at")}),
        record_sha256 TEXT NOT NULL CHECK({_hash("record_sha256")}),
        FOREIGN KEY(project_id) REFERENCES projects(project_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
        FOREIGN KEY(outbox_id) REFERENCES outbox_events(outbox_id) ON UPDATE RESTRICT ON DELETE RESTRICT
    ) STRICT
    """,
    f"""
    CREATE TABLE search_generations (
        generation_id TEXT PRIMARY KEY CHECK({_uuid("generation_id")}),
        project_id TEXT NOT NULL,
        purpose TEXT NOT NULL CHECK(purpose='lexical-fts5-v1'),
        analyzer_id TEXT NOT NULL CHECK(analyzer_id='ro-unicode61-diacritics2-1'),
        derivative_schema_version INTEGER NOT NULL CHECK(derivative_schema_version=1),
        canonical_key_version TEXT NOT NULL CHECK({_hash("canonical_key_version", 32)}),
        derivative_key_version TEXT NOT NULL CHECK({_hash("derivative_key_version", 32)}),
        lifecycle_sha256 TEXT NOT NULL CHECK({_hash("lifecycle_sha256")}),
        initial_watermark INTEGER NOT NULL CHECK(initial_watermark BETWEEN 0 AND 9007199254740991),
        authority_sha256 TEXT NOT NULL CHECK({_hash("authority_sha256")}),
        configuration_sha256 TEXT NOT NULL CHECK({_hash("configuration_sha256")}),
        created_at TEXT NOT NULL CHECK({_utc("created_at")}),
        UNIQUE(generation_id,project_id),
        FOREIGN KEY(project_id) REFERENCES projects(project_id) ON UPDATE RESTRICT ON DELETE RESTRICT
    ) STRICT
    """,
    f"""
    CREATE TABLE search_generation_leases (
        generation_id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        owner_sha256 TEXT NOT NULL CHECK({_hash("owner_sha256")}),
        epoch INTEGER NOT NULL CHECK(epoch BETWEEN 1 AND 9007199254740991),
        issued_at TEXT NOT NULL CHECK({_utc("issued_at")}),
        renewed_at TEXT NOT NULL CHECK({_utc("renewed_at")} AND renewed_at>=issued_at),
        expires_at TEXT NOT NULL CHECK({_utc("expires_at")} AND expires_at>renewed_at),
        FOREIGN KEY(generation_id,project_id) REFERENCES search_generations(generation_id,project_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT
    ) STRICT
    """,
    f"""
    CREATE TABLE search_generation_events (
        event_sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id TEXT NOT NULL UNIQUE CHECK({_uuid("event_id")}),
        generation_id TEXT NOT NULL,
        project_id TEXT NOT NULL,
        previous_event_id TEXT,
        stage TEXT NOT NULL CHECK(stage IN ('Building','Incomplete','Ready','Retired')),
        checkpoint INTEGER NOT NULL CHECK(checkpoint BETWEEN 0 AND 9007199254740991),
        cursor_item_id TEXT CHECK(cursor_item_id IS NULL OR ({_uuid("cursor_item_id")})),
        owner_sha256 TEXT NOT NULL CHECK({_hash("owner_sha256")}),
        lease_epoch INTEGER NOT NULL CHECK(lease_epoch BETWEEN 1 AND 9007199254740991),
        authority_sha256 TEXT NOT NULL CHECK({_hash("authority_sha256")}),
        projection_sha256 TEXT CHECK(projection_sha256 IS NULL OR ({_hash("projection_sha256")})),
        entry_count INTEGER CHECK(entry_count IS NULL OR entry_count BETWEEN 0 AND 9007199254740991),
        record_sha256 TEXT NOT NULL CHECK({_hash("record_sha256")}),
        occurred_at TEXT NOT NULL CHECK({_utc("occurred_at")}),
        CHECK((stage='Ready' AND projection_sha256 IS NOT NULL AND entry_count IS NOT NULL)
            OR (stage<>'Ready' AND projection_sha256 IS NULL AND entry_count IS NULL)),
        UNIQUE(event_id,generation_id,project_id),
        FOREIGN KEY(generation_id,project_id) REFERENCES search_generations(generation_id,project_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT,
        FOREIGN KEY(previous_event_id,generation_id,project_id)
            REFERENCES search_generation_events(event_id,generation_id,project_id) ON UPDATE RESTRICT ON DELETE RESTRICT
    ) STRICT
    """,
    f"""
    CREATE TABLE search_selections (
        event_id TEXT PRIMARY KEY CHECK({_uuid("event_id")}),
        project_id TEXT NOT NULL,
        selection_revision INTEGER NOT NULL CHECK(selection_revision BETWEEN 0 AND 9007199254740991),
        previous_event_id TEXT,
        generation_id TEXT,
        generation_event_id TEXT,
        checkpoint INTEGER NOT NULL CHECK(checkpoint BETWEEN 0 AND 9007199254740991),
        authority_sha256 TEXT NOT NULL CHECK({_hash("authority_sha256")}),
        record_sha256 TEXT NOT NULL CHECK({_hash("record_sha256")}),
        occurred_at TEXT NOT NULL CHECK({_utc("occurred_at")}),
        UNIQUE(project_id,selection_revision),
        UNIQUE(event_id,project_id),
        CHECK((generation_id IS NULL AND generation_event_id IS NULL AND checkpoint=0)
            OR (generation_id IS NOT NULL AND generation_event_id IS NOT NULL)),
        FOREIGN KEY(project_id) REFERENCES projects(project_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
        FOREIGN KEY(previous_event_id,project_id) REFERENCES search_selections(event_id,project_id)
            ON UPDATE RESTRICT ON DELETE RESTRICT,
        FOREIGN KEY(generation_event_id,generation_id,project_id)
            REFERENCES search_generation_events(event_id,generation_id,project_id) ON UPDATE RESTRICT ON DELETE RESTRICT
    ) STRICT
    """,
)

BINDING_DDL = (
    """
    CREATE TRIGGER search_change_binding BEFORE INSERT ON search_changes
    WHEN NOT EXISTS(SELECT 1 FROM outbox_events o WHERE o.outbox_id=NEW.outbox_id
        AND o.project_id=NEW.project_id AND o.revision_id IS NEW.revision_id
        AND o.event_type=NEW.event_type AND o.occurred_at=NEW.occurred_at AND o.record_sha256=NEW.record_sha256)
    BEGIN SELECT RAISE(ABORT,'search change authority denied'); END
    """,
    f"""
    CREATE TRIGGER search_change_after_outbox AFTER INSERT ON outbox_events
    WHEN NOT (NEW.revision_id IS NULL AND NEW.event_type IN ({_CONTROL_SQL}))
    BEGIN INSERT INTO search_changes(project_id,outbox_id,revision_id,event_type,occurred_at,record_sha256)
        VALUES(NEW.project_id,NEW.outbox_id,NEW.revision_id,NEW.event_type,NEW.occurred_at,NEW.record_sha256); END
    """,
    """
    CREATE TRIGGER search_generation_watermark BEFORE INSERT ON search_generations
    WHEN NEW.initial_watermark<>coalesce((SELECT max(sequence) FROM search_changes WHERE project_id=NEW.project_id),0)
    BEGIN SELECT RAISE(ABORT,'search generation watermark denied'); END
    """,
    """
    CREATE TRIGGER search_lease_creation_binding BEFORE INSERT ON search_generation_leases
    WHEN NOT EXISTS(SELECT 1 FROM search_generations g WHERE g.generation_id=NEW.generation_id
        AND g.project_id=NEW.project_id AND g.created_at<=NEW.issued_at)
    BEGIN SELECT RAISE(ABORT,'search lease creation denied'); END
    """,
    (
        "\n"
        "    CREATE TRIGGER search_lease_identity BEFORE UPDATE ON search_generation_leases\n"
        "    WHEN NEW.generation_id<>OLD.generation_id OR NEW.project_id<>OLD.project_id\n"
        "        OR (NEW.owner_sha256=OLD.owner_sha256 AND\n"
        "            (NEW.epoch<>OLD.epoch OR NEW.issued_at<>OLD.issued_at OR NEW.expires_at<OLD.expires_at\n"
        "                OR NEW.renewed_at<OLD.renewed_at OR NEW.renewed_at>=OLD.expires_at))\n"
        "        OR (NEW.owner_sha256<>OLD.owner_sha256 AND\n"
        "            (NEW.epoch<>OLD.epoch+1 OR NEW.issued_at<OLD.renewed_at OR NEW.renewed_at<>NEW.issued_at\n"
        "                OR NEW.issued_at<coalesce((SELECT occurred_at FROM search_generation_events\n"
        "                    WHERE generation_id=OLD.generation_id ORDER BY event_sequence DESC LIMIT "
        "1),OLD.issued_at)\n"
        "                OR (NEW.issued_at<OLD.expires_at AND coalesce((SELECT stage FROM search_generation_events\n"
        "                    WHERE generation_id=OLD.generation_id ORDER BY event_sequence DESC LIMIT "
        "1),'Building')<>'Incomplete')))\n"
        "    BEGIN SELECT RAISE(ABORT,'search lease transition denied'); END\n"
        "    "
    ),
    (
        "\n"
        "    CREATE TRIGGER search_generation_event_binding BEFORE INSERT ON search_generation_events\n"
        "    WHEN NOT EXISTS(SELECT 1 FROM search_generation_leases l WHERE l.generation_id=NEW.generation_id\n"
        "        AND l.project_id=NEW.project_id AND l.owner_sha256=NEW.owner_sha256 AND l.epoch=NEW.lease_epoch\n"
        "        AND l.renewed_at<=NEW.occurred_at AND NEW.occurred_at<l.expires_at)\n"
        "      OR NEW.checkpoint>coalesce((SELECT max(sequence) FROM search_changes WHERE "
        "project_id=NEW.project_id),0)\n"
        "      OR (NEW.previous_event_id IS NULL AND (NEW.stage<>'Building' OR NEW.checkpoint<>0 OR EXISTS(\n"
        "        SELECT 1 FROM search_generation_events e WHERE e.generation_id=NEW.generation_id)))\n"
        "      OR (NEW.previous_event_id IS NOT NULL AND NOT EXISTS(\n"
        "        SELECT 1 FROM search_generation_events e WHERE e.event_id=NEW.previous_event_id\n"
        "            AND e.generation_id=NEW.generation_id AND e.project_id=NEW.project_id\n"
        "            AND e.event_sequence=(SELECT max(event_sequence) FROM search_generation_events WHERE "
        "generation_id=NEW.generation_id)\n"
        "            AND NEW.checkpoint>=e.checkpoint\n"
        "            AND NEW.occurred_at>=e.occurred_at\n"
        "            AND ((e.stage='Building' AND NEW.stage IN ('Building','Incomplete','Ready','Retired'))\n"
        "                OR (e.stage='Incomplete' AND NEW.stage IN ('Building','Retired'))\n"
        "                OR (e.stage='Ready' AND NEW.stage IN ('Ready','Retired','Incomplete')))))\n"
        "      OR (NEW.stage='Ready' AND NEW.checkpoint<(SELECT initial_watermark FROM search_generations WHERE "
        "generation_id=NEW.generation_id))\n"
        "    BEGIN SELECT RAISE(ABORT,'search generation transition denied'); END\n"
        "    "
    ),
    (
        "\n"
        "    CREATE TRIGGER search_selection_binding BEFORE INSERT ON search_selections\n"
        "    WHEN (NEW.previous_event_id IS NULL AND (NEW.selection_revision<>0 OR EXISTS(\n"
        "        SELECT 1 FROM search_selections s WHERE s.project_id=NEW.project_id)))\n"
        "      OR (NEW.previous_event_id IS NOT NULL AND NOT EXISTS(\n"
        "        SELECT 1 FROM search_selections s WHERE s.event_id=NEW.previous_event_id AND "
        "s.project_id=NEW.project_id\n"
        "            AND s.selection_revision=NEW.selection_revision-1 AND NEW.occurred_at>=s.occurred_at AND "
        "s.selection_revision=(\n"
        "                SELECT max(selection_revision) FROM search_selections WHERE project_id=NEW.project_id)))\n"
        "      OR (NEW.generation_id IS NOT NULL AND NOT EXISTS(\n"
        "        SELECT 1 FROM search_generation_events e JOIN search_generation_leases l\n"
        "            ON l.generation_id=e.generation_id AND l.project_id=e.project_id\n"
        "        WHERE e.event_id=NEW.generation_event_id AND e.generation_id=NEW.generation_id AND "
        "e.project_id=NEW.project_id\n"
        "            AND e.stage='Ready' AND e.checkpoint=NEW.checkpoint AND e.authority_sha256=NEW.authority_sha256\n"
        "            AND NEW.checkpoint=coalesce((SELECT max(sequence) FROM search_changes WHERE "
        "project_id=NEW.project_id),0)\n"
        "            AND e.event_sequence=(SELECT max(event_sequence) FROM search_generation_events WHERE "
        "generation_id=NEW.generation_id)\n"
        "            AND l.owner_sha256=e.owner_sha256 AND l.epoch=e.lease_epoch\n"
        "            AND NEW.occurred_at>=e.occurred_at AND NEW.occurred_at>=l.issued_at AND "
        "NEW.occurred_at<l.expires_at))\n"
        "    BEGIN SELECT RAISE(ABORT,'search selection transition denied'); END\n"
        "    "
    ),
    """
    CREATE TRIGGER search_lease_no_delete BEFORE DELETE ON search_generation_leases
    BEGIN SELECT RAISE(ABORT,'search lease history cannot be reset'); END
    """,
)

INDEX_DDL = (
    "CREATE INDEX search_changes_project_sequence ON search_changes(project_id,sequence)",
    "CREATE INDEX search_generation_events_head ON search_generation_events(generation_id,event_sequence)",
    "CREATE INDEX search_selections_head ON search_selections(project_id,selection_revision)",
)
HISTORY_DDL = tuple(
    f"CREATE TRIGGER {table}_no_{operation} BEFORE {operation.upper()} ON {table} "
    "BEGIN SELECT RAISE(ABORT,'search authority history is append-only'); END"
    for table in IMMUTABLE_TABLES
    for operation in ("update", "delete")
)
_CONFLICTS = {
    "search_changes": "outbox_id=NEW.outbox_id OR sequence=NEW.sequence",
    "search_generations": "generation_id=NEW.generation_id",
    "search_generation_events": "event_id=NEW.event_id OR event_sequence=NEW.event_sequence",
    "search_selections": "event_id=NEW.event_id OR (project_id=NEW.project_id AND "
    "selection_revision=NEW.selection_revision)",
    "search_generation_leases": "generation_id=NEW.generation_id",
}
REPLACEMENT_DDL = tuple(
    f"CREATE TRIGGER {table}_no_replace BEFORE INSERT ON {table} "
    f"WHEN EXISTS(SELECT 1 FROM {table} WHERE {predicate}) "
    "BEGIN SELECT RAISE(ABORT,'search authority replacement denied'); END"
    for table, predicate in _CONFLICTS.items()
)
DDL = (*TABLE_DDL, *BINDING_DDL, *INDEX_DDL, *HISTORY_DDL, *REPLACEMENT_DDL)


__all__ = ["CONTROL_EVENTS", "DDL", "IMMUTABLE_TABLES", "MUTABLE_TABLES", "SOURCE_EVENT_WHERE", "TABLES"]
