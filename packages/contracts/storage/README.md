# Local storage contracts

`sqlite-profile.v1.json` is the exact portable profile contract for the current
version-4 canonical local database. It fixes the database identity, version, scalar storage domain,
connection controls, checkpoint authority, integrity checks, and normalized
table inventory. It also fixes the immutable-row and intentionally mutable-state
table sets plus the dedicated backed-up migration-only schema-change boundary.
`sqlite-profile.schema.json` fails closed on any undeclared override.

The profile is not an API for issuing SQL. Core owns the SQLite adapter, the
desktop never opens the database, and downstream modules consume repository
ports introduced by the storage slice. Ordinary connections deny schema DDL.
The separately constructed T02 Alembic authority is never returned to ordinary
callers: it checkpoints and validates exact supported version-1 through version-3 fixtures, reserves the
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
references, rights-aware verified streams, corruption quarantine, conservative
wrapped-key failure classification, and the journaled prior-envelope upgrade phases.
It also states that the unencrypted fixture adapter is explicitly test-only. It
carries no operating-system path.
