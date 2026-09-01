# Local storage contracts

`sqlite-profile.v1.json` is the exact portable profile contract for the current
version-10 canonical local database. It fixes the database identity, version, scalar storage domain,
connection controls, checkpoint authority, integrity checks, and normalized
table inventory. It also fixes the immutable-row and intentionally mutable-state
table sets plus the dedicated backed-up migration-only schema-change boundary.
`sqlite-profile.schema.json` fails closed on any undeclared override.

The profile is not an API for issuing SQL. Core owns the SQLite adapter, the
desktop never opens the database, and downstream modules consume repository
ports introduced by the storage slice. Ordinary connections deny schema DDL.
The separately constructed T02 Alembic authority is never returned to ordinary
callers: it checkpoints and validates exact supported version-1 through version-5 fixtures, reserves the
writer, creates and verifies an online backup, and only then replaces the
affected controls in one transaction. `sqlite-migration-recovery.schema.json`
binds the immutable backup manifest to exact backup bytes, the reviewed revision,
and both schema fingerprints.

The committed v3 envelope migration remains immutable. Version 4 adds the
`object_envelope_upgrades` mutable-state journal and records v2-origin plaintext
objects as upgrade work rather than release-compatible fixtures. Key-dependent
copy-on-write work runs after the schema transaction and before ordinary project
access, retaining a verified rollback outside `.tmp` until the encrypted production
reader succeeds.
Version 5 adds only bounded technical object creation-source metadata. Existing
rows become `legacy-unreported`; that value reports missing technical history and
does not invent a citation, research observation, actor claim, or scholarly
provenance event.
Version 6 preserves those contracts and extends the nullable provenance actor
field to accept UUIDv7 profile actors as well as the earlier canonical technical
identifiers. Its table-rebuild migration retains every provenance row, restores
the append-only triggers and index, and advances immutable migration history only
after the reviewed target schema is exact.
Version 7 adds the canonical provenance ledger, version 8 adds durable workflow
execution, and version 9 adds immutable material-dependency coverage, typed
revision/configuration edges, and content-free completion-denial diagnostics.
Existing v8 output revisions migrate as `legacy-unreported` with no fabricated
edges. New recalculable outputs must register a nonempty canonical edge set in
the same transaction as revision, provenance, and outbox authority before a
workflow can commit them.

Version 10 adds durable dependency-impact runs, immutable content-free
conditional-decision authority, graph-bound items, append-only stale causes,
bounded compare-and-swap checkpoints, and content-free impact audit facts. The
preview digest binds the complete change, policy, actor, exact endpoint,
conditional decisions, graph, and bounded traversal configuration. Each
checkpoint revalidates that authority and the current graph before writing. The
bounded path representation always retains the affected terminal revision and
binds the full revision count and truncation state in both impact-item and
stale-cause authority; its configured sample bound is the maximum number of
stored revision identities. The v9-to-v10 migration creates no run, decision,
or stale state for historical
outputs, so missing recalculation knowledge remains explicit rather than
invented.

The Core repository layer is the executable consumer boundary for this profile.
Business modules type against dependency-neutral aggregate-repository and
unit-of-work ports under the Core `ports` package; the SQLite/SQLAlchemy adapter
stays private to the data layer. Each aggregate write
atomically appends the common revision, its kind extension, a provenance fact,
and a pending outbox record. The shared record digest binds the full command,
expected revision, schedule, and event identity so an exact idempotent replay
returns the original projection while changed reuse conflicts. Stale expected
revisions, unknown aggregate IDs, incompatible authority, and writer contention
are distinct bounded outcomes. These Python ports are adapter APIs, not new
portable storage documents, so they do not change this JSON profile or its
schema fingerprint.

`object-store-profile.v1.json` is the exact portable policy for the
project-scoped object adapter introduced by CAP-02.S03. It binds plaintext
SHA-256 identity, project-only deduplication, opaque HMAC-derived physical
identity, complete-file publication before metadata, immutable document
references, bounded technical creation source, rights-aware verified streams,
corruption quarantine, conservative
wrapped-key failure classification, and the journaled prior-envelope upgrade phases.
The mandatory Core pre-open coordinator and pre/post journal, fsync, rename,
verification, metadata-commit, cleanup, and cancellation recovery boundary are
portable obligations rather than optional composition details. The profile also
states that the unencrypted fixture adapter is explicitly test-only. It carries
no operating-system path.

Known local-read purposes are allowed by the default object access policy.
Unknown purposes and controlled egress fail closed before path resolution or
decryption. CAP-02.S04 may inject the dependency-neutral policy port to return an
exact allow decision after applying project privacy, consent, and destination
rules; deny, require-confirmation, exceptions, and malformed decisions expose no
stream.

The same profile fixes T03's categorized physical accounting and maintenance
boundary. Deployment configuration supplies optional project and shared-cache
soft/hard byte limits plus the mandatory local free-space reserve. Low disk or a
hard project limit denies new object writes without denying verified reads or
cleanup. Cleanup is always preceded by an attributable one-time preview lease;
execution revalidates immutable references, active readers, file identity, size,
link count, and category authority. Automatic canonical reclamation is limited to
unreferenced `derived-rebuildable` objects. Durable and export-retained objects
remain non-reclaimable, shared-cache authority requires an explicit root, and its
layout remains owned by CAP-02.S05.
