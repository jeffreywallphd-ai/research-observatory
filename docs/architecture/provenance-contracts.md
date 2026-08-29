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
| `subject`, `time` | Portable project/entity subject and the exact UTC occurrence time. |
| `correlationid`, `causationid`, `traceparent` | Durable causal/correlation identity and W3C operational trace linkage without retaining telemetry. |
| `sensitivity`, `retentionclass` | Closed content classification and retention duty that every referenced entity must preserve. |
| `data` | One agent, one activity, exact input/output entity references, PROV relations, and an optional protected payload reference. |

Known v1 types cover source acquisition, parsing, extraction, verification,
decision, synthesis, export, and invalidation. Their activity kind and
input/output shape are checked semantically. Unknown future types remain
storable only when the complete structural, minimization, identity, relation,
classification, and time boundary passes; readers must not infer their meaning.

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
  must close over the event's own objects.
- Sensitive detail, when needed, is a protected object identity/revision/hash
  and media type. It remains behind the object-store rights, access, encryption,
  egress, and retention boundary.

## Canonical record and compatibility

The generated TypeScript and Python contracts own immutable snapshots and
produce deterministic RFC 8785-compatible JSON for the schema's restricted
I-JSON subset. Python also returns the exact `sha256:` record identity. T02 will
persist the original record, record hash, chain segment/checkpoint identity,
and atomic outbox fact. A canonicalization or hash change starts a new segment;
it never rewrites historical bytes.

Hash chains are tamper-evidence for supported operation, not legal
nonrepudiation or protection from a fully compromised host. Checkpoint mismatch
must enter integrity-review mode and block unsafe export/claim use while
preserving read-only inspection.

## Task handoff

T01 owns the schema, generated decoders, fixture, ADR, and package inventory.
It deliberately does not create a second persistence system or reinterpret the
existing narrow `provenance_events` rows. T02 owns the governed migration,
atomic ledger/outbox write, idempotent retry, restart bridge, paged lineage
queries, and checkpoint verification. T03 consumes those APIs for the approved
Audit and Lineage workspace; the renderer never reads SQLite directly.
