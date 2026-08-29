# Portable provenance contracts

ADR-0024 governs the portable scholarly-provenance boundary. Canonical domain
state remains relational and versioned; provenance is an append-only account of
how exact immutable entities were used, generated, attributed, derived, or
invalidated by bounded activities and responsible agents.

## Event envelope

`packages/contracts/provenance/provenance-event.schema.json` is the Draft
2020-12 wire authority. It uses the CloudEvents 1.0 context model and adds only
lower-case portable extensions:

| Field | Contract |
|---|---|
| `id`, `projectid`, `actorid` | UUIDv7 event/actor identities; project retains the governed UUIDv4 bridge or UUIDv7. |
| `type`, `schemaversion`, `dataschema` | Versioned event meaning and payload schema; future structural types can be retained without interpretation. |
| `subject`, `time` | Exact project/entity/revision subject (or the exact activity for an entity-less acquisition failure) and a year 0001-9999 canonical UTC occurrence time. |
| `correlationid`, `causationid`, `traceparent` | Durable causal/correlation identity and W3C operational trace linkage without retaining telemetry. |
| `sensitivity`, `retentionclass` | Closed content classification and retention duty that every referenced entity must preserve. |
| `data` | One agent, one activity, exact input/output entity references, PROV relations, and an optional protected payload reference. |

Known v1 types cover source acquisition, parsing, extraction, verification,
decision, synthesis, export, and invalidation. Their activity kind and
input/output shape are checked semantically. Unknown future types remain
storable only when the complete structural, minimization, identity, relation,
classification, and time boundary passes; readers must not infer their meaning.
That universal boundary forbids outputs for every non-succeeded activity and
requires exactly one generation and attribution relation for every succeeded
output, including outputs carried by an uncataloged future type.

## PROV mapping and minimization

- Input/output `ProvenanceEntity` records identify immutable aggregate revisions
  and content hashes. They contain no title, passage, prompt, path, filename, or
  generated text.
- `ProvenanceActivity` records bounded operation kind/status/time and an exact
  versioned configuration hash.
- `ProvenanceAgent` uses an opaque UUIDv7 identity, closed agent type, and
  portable role; it carries no name, email, OS account, provider secret, or
  impersonation token.
- Relations use `used`, `wasGeneratedBy`, `wasAssociatedWith`,
  `wasDerivedFrom`, `wasInvalidatedBy`, and `wasAttributedTo`, and all endpoints
  carry both stable entity and exact revision identity and close over the
  event's own objects. Relation IDs and facts are unique.
- One stable entity identity retains one entity kind across revisions. A
  cross-kind transformation mints a distinct stable identity and derives its
  exact output revision from the exact input revision. Project identity is in
  the event-local collision set, and entity subjects use the same portable-key
  kind grammar as entity records.
- Relation roles and outcomes fail closed: use targets inputs; generation and
  attribution target outputs; derivation runs from an output revision to a
  distinct input revision; and invalidation is asserted only for a succeeded
  invalidation. Failed, cancelled, and denied activities cannot assert completed
  result facts, and denial cannot claim input use.
- Sensitive detail, when needed, is a protected object identity/revision/hash
  and media type. It remains behind the object-store rights, access, encryption,
  egress, and retention boundary.

## Canonical record and compatibility

The generated TypeScript and Python contracts own immutable snapshots and
produce deterministic RFC 8785-compatible JSON for the schema's restricted
I-JSON subset. Python also returns the exact `sha256:` record identity. The v7
SQLite adapter persists the original record, record hash, normalized query
projection, versioned chain segment/checkpoint identity, atomic narrow audit
binding, and atomic outbox fact. The historical `rfc8785.sha256.v1` segment
retains its exact record-and-sequence formula. New writes use the distinct
`rfc8785.sha256.v2` segment, whose chain additionally binds the retry fingerprint
and a digest of every immutable outbox-authority field; each segment starts at
sequence one and is verified under only its declared formula. Lineage integrity
compares event and project authority plus every normalized entity/relation field
back to the canonical record, and cross-checks event, project, output revision,
type, time, actor identity/type, trace identity, and record digest against the
narrow audit row. Canonicalization, hash material, or algorithm changes always
start a declared new segment; they never rewrite or reinterpret historical
bytes.

The two runtimes and Draft 2020-12 schema accept only canonical millisecond UTC
instants from `0001-01-01T00:00:00.000Z` through
`9999-12-31T23:59:59.999Z`. This explicit range avoids platform-specific year
zero behavior and keeps wire validation, canonical bytes, and hashes aligned.

Hash chains are tamper-evidence for supported operation, not legal
nonrepudiation or protection from a fully compromised host. Checkpoint mismatch
must enter integrity-review mode and block unsafe export/claim use while
preserving read-only inspection.

## Task handoff

T01 owns the schema, generated decoders, fixture, ADR, and package inventory.
It deliberately does not create a second persistence system or reinterpret the
existing narrow `provenance_events` rows. T02 adds the governed migration,
atomic ledger/outbox write, idempotent retry, restart bridge, bounded paged
lineage queries, and checkpoint verification. Earlier narrow rows remain
explicit legacy bridges and are never reinterpreted as complete portable
events. T03 consumes those APIs for the approved
Audit and Lineage workspace; the renderer never reads SQLite directly.

## Audit and Lineage desktop boundary

The desktop workspace reaches the ledger only through the authenticated Core
`POST /projects/provenance/lineage` boundary. One workspace selection followed
by one exact UUIDv7 submission returns a depth- and page-bounded ancestor or
descendant trace. Read-only projects remain inspectable; closed projects do not
issue a lineage request.

Each returned row identifies the exact entity revision, event, transformation,
configuration ID/version/hash, responsible agent type/role, and occurrence
time. Same-entity historical revisions and distinct source or alternate inputs
remain visible rather than being collapsed. Invalidation events are marked
stale, while missing revisions, legacy bridges, or failed integrity verification
remain visible as an integrity-review state that is unsuitable for export or
claim use until repaired.

The response deliberately contains no source text, passage text, prompt text,
researcher name, secret, or model rationale. A configuration hash and version
make the governed prompt/model/tool setup traceable without representing hidden
chain-of-thought as evidence; protected content remains behind its separate
rights and access boundary.
