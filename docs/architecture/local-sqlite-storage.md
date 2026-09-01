# Local SQLite storage profile

The local Core service is the sole authority that opens
`state/project.sqlite3`. The desktop renderer, native shell, workers, and
business modules do not receive filesystem paths or SQLite connection objects.
ADR-0014 governs the logical database profile; ADR-0020 adds the mandatory W1
Windows production protection profile. The portable machine records are
[`sqlite-profile.v1.json`](../../packages/contracts/storage/sqlite-profile.v1.json)
and [`protected-database-profile.v1.json`](../../packages/contracts/storage/protected-database-profile.v1.json).

## W1 protected production profile

Production Core uses SQLCipher 4.12 Community through the pinned `sqlcipher3`
binding. Every project receives a distinct random raw 256-bit database key from
the Windows current-user DPAPI profile vault. Core rejects a plaintext SQLite
header before opening an existing production project and cannot initialize a
database until the key authority is configured. The explicit
`development_plaintext_database_fixture()` scope is the sole plaintext
exception and is never selected by runtime composition.

Compatibility level 4, a zero-byte plaintext header, 4096-byte cipher pages,
HMAC-SHA-512, extensions off, trusted schema off, and the canonical authorizer
are verified for every protected connection. Integrity reports now expose the
content-free protection profile, SQLCipher version, and cipher-integrity result.
Missing keys, incompatible profiles, or corruption fail closed and retain the
original bytes.

Legacy plaintext conversion is an explicit-consent, validated copy-on-write
operation. Protected backup uses SQLite's online backup API into a keyed,
checkpointed, independently verified SQLCipher file. Restore verifies a
quiescent copy-on-write candidate before atomic publication and rolls back the
displaced encrypted database on failure. Rekey stages a new vault record,
retains an encrypted rollback copy, verifies the staged key after restart, and
only then activates it with compare-and-swap. Schema migrations use the same
protected connection and create encrypted migration backups.

## Current version-10 authority

| Concern | Current rule |
|---|---|
| Database identity | application ID `0x524f4253`, `user_version=10`, profile `sqlite-wal-v1` |
| Durable identities | lowercase UUIDv7 text; project UUIDv4 bridge and prior canonical actor identifiers are explicitly retained |
| Time | UTC RFC 3339 text at fixed millisecond precision |
| Types | STRICT `INTEGER`, `REAL`, and `TEXT`; no `ANY` or `BLOB` columns |
| Concurrency | WAL, normal locking, one writer, concurrent reader snapshots, 5-second busy timeout |
| Durability | `synchronous=FULL`; 1000-page passive auto-checkpoint |
| Trust | foreign keys on, trusted schema off, defensive mode on, DQS and extensions off |
| Integrity | exact table/trigger inventory, immutable-row denial triggers, `quick_check`, and `foreign_key_check` |

Every connection is created by the canonical storage factory and re-verifies
these controls. WAL activation is accepted only when SQLite returns `wal`.
Project creation builds and checks the database before the staging directory is
published. Compatible project open validates application, profile, exact schema
fingerprint, and project identity while holding the exclusive session lock; any
required object-envelope upgrade completes before the open audit record. Full
`quick_check` and `foreign_key_check` scans are
explicit integrity operations so interactive open cost does not scale with the
database; T02/T03 must schedule them at startup/maintenance and surface recovery.

## Normalized table inventory

| Table | Authority |
|---|---|
| `schema_metadata` | immutable singleton schema/profile/application identity |
| `schema_migrations` | append-only successful forward-migration identity, backup-manifest binding, and source/target fingerprints |
| `projects` | immutable project identity anchor; mutable lifecycle remains manifest-owned until repository integration |
| `object_records` | content digest, size, media type, rights, protection, retention, bounded technical creation source, and verification metadata; never object bytes or paths |
| `object_envelope_upgrades` | mutable pre-open copy-on-write phase, stable file identities, bounded failure code, and pending encrypted-envelope metadata |
| `aggregate_identities` | immutable project-scoped aggregate identity and kind |
| `aggregate_revisions` | immutable common scholarly aggregate revision envelope |
| `scholarly_records`, `documents`, `workflows`, `evidence`, `ontologies`, `decisions` | immutable kind extension rows keyed to a common revision |
| `workflow_*` | versioned workflow authority, durable queue/attempt state, append-only history/checkpoints, artifacts, and committed output manifests |
| `material_dependency_outputs` | immutable dependency-coverage classification for each exact output revision |
| `material_dependencies` | immutable typed direct edges to exact revision or configuration endpoints, with policy and fingerprint authority |
| `material_dependency_diagnostics` | content-free append-only audit facts for dependency-sensitive completion denials |
| `dependency_impact_runs` | durable graph/change/limit-bound propagation authority, lifecycle state, compare-and-swap checkpoint, cancellation, and bounded failure code |
| `dependency_impact_decisions` | immutable content-free propagate/ignore authority for supplied conditional edge decisions, reconstructable by run after restart |
| `dependency_impact_items` | immutable ordered impact decisions and sampled paths for one exact run preview |
| `dependency_stale_causes` | append-only project/output/change/policy stale authority; repeated propagation cannot erase or replace an earlier cause |
| `dependency_impact_audit_events` | content-free append-only run-start, checkpoint, cancellation, and completion facts |
| `provenance_events` | append-only typed event metadata, stable canonical/UUIDv7 actor authority, and record digest |
| `settings` | append-only versioned, exactly-one-of typed scalar project settings |
| `outbox_events` | transaction-outbox metadata/digest seam for the later unit of work |

Object bytes, document content, indexes, models, caches, and other derived
binary artifacts remain in the classified project-package locations. The
database may retain a SHA-256 reference; it does not admit arbitrary payload or
derived blob columns.

Every row in `schema_metadata`, `projects`, `aggregate_identities`,
`aggregate_revisions`, the six kind-extension tables, `provenance_events`, and
`settings`, and `schema_migrations` deny UPDATE and DELETE in fingerprinted DDL. New revisions and
setting values are inserts. `object_records` may advance availability and
verification state, `object_envelope_upgrades` may advance the durable verified
copy-on-write recovery phases, and `outbox_events` may advance delivery state.
The outbox's identity, project, revision, type, occurrence/scheduling time,
idempotency key, and record digest remain immutable transaction authority even
though the row carries mutable dispatch state; aggregate replay and lineage
verification fail closed if any of those authority fields diverge. These are the
only intentionally mutable current-profile tables.

## Evolution and recovery boundary

T01 established schema version 1 and its sealed ordinary connection factory.
The backup-first migration authority now advances exact supported v1 through v9
profiles to current schema v10. It owns forward migrations, backup-before-migrate,
checkpointed snapshots, frozen source fixtures, and failure recovery. The migration
runner validates and checkpoints the source, reserves SQLite's writer lock, creates and verifies an online backup
through a second held connection, and only then runs the reviewed Alembic
revision in one transaction. The immutable recovery manifest binds the backup
bytes and both schema fingerprints; a failed transaction rolls back while the
verified backup remains available. A current version-10 database is detected
idempotently and is never backed up or rewritten. Committed v3 history is never
rewritten; v4 adds only the post-schema object-envelope upgrade journal and v5
adds the truthful `legacy-unreported` backfill for missing technical object
creation routes. Version 6 rebuilds only the provenance table so a stable
profile-scoped UUIDv7 researcher identity can be carried exactly while preserving
legacy canonical actor identifiers, append-only triggers, indexes, and every
prior row. Version 7 adds the portable provenance ledger, version 8 adds the
durable local workflow executor, and version 9 adds material-dependency
authority. The v8-to-v9 migration labels every existing output revision
`legacy-unreported` and creates no dependency edge, so missing historical
knowledge stays explicit. T03 owns SQLAlchemy repositories, optimistic
concurrency, transaction/outbox publication, and units of work. Central
bootstrap/migration code is the only allowed source of schema SQL; domain and UI
code must use the repository ports. Ordinary canonical access returns a
restricted connection/cursor capability rather than a raw `sqlite3.Connection`:
authorizer, configuration, extension-loading, raw-cursor, backup, serialization,
and callback escape hatches are not exposed. Its underlying authorizer denies
schema DDL plus write-form identity, security, and durability PRAGMAs. T02
uses a separate, tightly scoped migration connection that is never returned to
ordinary code, operates only after verified backup, replaces the affected denial
triggers as part of the successor DDL, and publishes the new exact fingerprint
before normal access resumes. Version 10 adds only the durable dependency-impact
projection boundary. Complete change and conditional-decision authority is
bound into each preview, supplied conditional decisions remain reconstructable,
and every propagation checkpoint revalidates the exact graph snapshot before it
writes. Traversal limits cannot exceed the durable 20,000-node, 100,000-edge,
128-depth, 64-path-sample, and 100-legacy-sample maxima. Its migration does not
infer changes, fabricate stale causes, or rewrite version-9 material dependency
registrations.

## Repository and transaction boundary

Business modules depend on the dependency-neutral `AggregateRepository`,
`UnitOfWork`, and `UnitOfWorkFactory` ports under the Core `ports` package.
Importing those ports loads neither SQLite nor SQLAlchemy. Business modules
never import the concrete adapter and never receive a database connection. The
local adapter uses SQLAlchemy 2 Core
statements behind an opaque unit-of-work token. A single explicit writer
transaction inserts an immutable aggregate revision, its kind-extension row,
one provenance event, and one pending outbox event. `commit()` is explicit;
leaving the context without commit, any constraint failure, or a stale expected
revision rolls the whole transaction back.

The generic aggregate port covers record, document, workflow, evidence,
ontology, and decision revisions. It returns detached frozen domain
projections, reports not-found, optimistic-conflict, busy-writer, and
incompatible-authority outcomes through bounded repository exceptions,
preserves aggregate kind and creation identity across revisions, and never
exposes ORM rows. The outbox and provenance records share a SHA-256 fingerprint
over the full command, precondition, scheduling, and event identity. An exact
idempotency-key/fingerprint retry returns the original projection without
duplicate facts; any changed payload or precondition is a conflict. Dispatch state
transitions remain a later worker concern.

Schema v7 adds the portable provenance ledger beside the existing narrow audit
seam. Each aggregate revision records canonical RFC 8785-compatible event bytes,
the exact record hash, normalized entity/relation projections, a versioned
ordered segment hash, a checkpoint, the narrow audit fact, and the outbox fact
in the same transaction. Historical `rfc8785.sha256.v1` rows retain their exact
record-and-sequence chain. The distinct v2 segment binds the retry fingerprint
and an immutable-outbox-authority digest without invalidating v1 history. Exact
retry verifies the canonical ledger, checkpoint, narrow actor/trace audit, full
outbox authority, and output revision before returning the original projection.
The
v6-to-v7 migration copies earlier narrow rows into an explicitly
`legacy-narrow` bridge without inventing portable entities, activities, agents,
or relations. Migration history is a contiguous hash-verified suffix of the
revision registry, so a database initialized fresh at any supported schema does
not fabricate migrations that never ran and remains current after later upgrades.
Bounded lineage reads verify canonical event/project identity, normalized
entities and relations, version-dispatched checkpoint chains, the immutable
outbox authority, and the atomic narrow actor/trace binding; they return
production activity and responsible-agent identities and label missing
references or mismatches `integrity-review` while retaining read-only
inspection.

Schema v9 extends the aggregate transaction with one explicit dependency
coverage row and, for recalculable outputs, a nonempty canonical set of typed
direct dependencies. Revision endpoints are exact project-scoped aggregate
revisions. Prompt, model, parameter, schema, template, and code dependencies use
immutable configuration identity plus semantic version instead of pretending to
be aggregate kinds. The command fingerprint binds the complete sorted edge set,
so exact retry is idempotent and any changed endpoint, policy, materiality, or
fingerprint conflicts. Workflow completion independently requires `complete`
coverage for every selected staged output; denial leaves job and artifact state
unchanged and persists only a content-free diagnostic. Schema v10 derives
transitive impact from those immutable direct edges without storing inferred
edges. A graph-bound preview records direct, transitive, conditional-review,
non-material, and unknown-impact outcomes. Propagation revalidates the exact
graph and policy hashes inside the writer transaction, advances a bounded
compare-and-swap checkpoint, appends stale causes, and can resume after
interruption without duplicate authority. `legacy-unreported` coverage and
unavailable replacement fingerprints remain unknown; they never produce a
false fresh result.

WAL and SHM files are live database state. A backup or relocation implementation
must use SQLite's backup/checkpoint facilities and never copy only the main file
while a WAL transaction may be pending. Profile mismatch, corruption, redirect,
hardlink, or wrong project identity fails closed and preserves the source for
backup-first repair.

The W1 Windows profile now claims SQLCipher encryption at rest within the
ADR-0020 threat boundary. Same-user malware, unlocked-process memory, OS or
kernel compromise, and loss of all vault/recovery material remain explicit
residual risks; OS sign-in, full-disk encryption, endpoint protection, and
physical security remain required.
