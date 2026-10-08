# Local storage contracts

The current executable database is schema 27. Schema 26 adds immutable parse
jobs/results, accepted normalized revisions and scoped element indices. Schema
27 permits an authenticated, output-free source invalidation without inventing
a replacement revision. It preserves every existing impact run, index, trigger
and historical row under a verified backup and transactional forward migration.
`sqlite-migration-recovery.schema.json` preserves target-v21
through v26 readers and adds exact source-v1 through v26 chains to target-v27,
including source/target fingerprints and backup-path binding. Historical profile
documents and already recorded recovery manifests retain their original meaning.

`sqlite-profile.v1.json` is the exact portable profile contract for the current
canonical local database. It fixes the database identity, version, scalar storage domain,
connection controls, checkpoint authority, integrity checks, and normalized
table inventory. It also fixes the immutable-row and intentionally mutable-state
table sets plus the dedicated backed-up migration-only schema-change boundary.
`sqlite-profile.schema.json` fails closed on any undeclared override.

The profile is not an API for issuing SQL. Core owns the SQLite adapter, the
desktop never opens the database, and downstream modules consume repository
ports introduced by the storage slice. Ordinary connections deny schema DDL.
The separately constructed T02 Alembic authority is never returned to ordinary
callers: it checkpoints and validates exact supported version-1 through version-16 fixtures, reserves the
writer, creates and verifies an online backup, and only then replaces the
affected controls in one transaction. `sqlite-migration-recovery.schema.json`
binds the immutable backup manifest to exact backup bytes, the reviewed revision,
and both schema fingerprints. The exact predecessor
`sqlite-migration-recovery.v16.snapshot.json` remains available to validate
already written target-v16 backup manifests; choose the reader by the
manifest's target schema version rather than reinterpreting old recovery
history under the v17 target contract. The frozen
`sqlite-migration-recovery-v17.snapshot.json` likewise validates target-v17
manifests after the current contract advances to v18.

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

Version 11 adds protected import-preview identity, ordered encrypted-source chunk
references and seals, durable parse-attempt records/completion, immutable draft
revisions/decisions, and content-free audit events. Sealing closes chunk membership;
parse completion closes record membership. Draft revision predecessors cannot be
NULL after revision one. Preview references participate in object deletion and
storage accounting, including cancelled previews; cancellation is not deletion
authority. Migration creates no source observations, drafts or scholarly records.
An intake seal binds declared source identity; actual parser EOF and the exact
successful durable attempt remain prerequisites for exposing a complete preview.

Version 12 adds append-only draft-summary attempts, compact ordinal metadata,
indexed duplicate groups and completion receipts. It retains no extra raw source
copies, invents no prior summaries and leaves canonical scholarly records alone.
Results require current draft/rights checks and accepted durable worker output;
the presence of projection rows is not completion or permission.

Version 13 adds immutable import-commit preparation, source records, manifests,
ordered members and completion seals. Version 14 adds exact scholarly source
assertions, canonical Work revision links, indexed identifier hashes and command
receipts. Source records and accepted decisions remain unchanged. Reconciliation
reuses canonical revisions and atomic provenance/outbox/dependency publication;
the lookup index is not independent identity or access authority. See the
[scholarly contract](../scholarly-records/README.md) for current-source checks,
bounded matching and public handoff. The populated exact v13 predecessor fixture
is retained with a digest, including source and audit rows, for migration proof.

Version 15 adds sealed current Work membership and aliases, immutable human
review decisions, and bounded feature/candidate-set/explanation documents.
Exact commands and review outcomes bind dependency runs to their owners. Sealed
run snapshots, append-only continuation links and checkpoint-bound cancellation
permit recovery after material graph growth without changing previous impact
items or stale causes. The existing graph validator remains authoritative.
Populated plaintext and encrypted v14 predecessors exercise backup, additive
migration, interruption rollback and unchanged historical receipts.

Version 16 adds immutable Work manifestation, relation, preference and decision
history. Version 17 preserves every v16 row while a backed-up, forward-only
transaction rebuilds the common aggregate identity/revision constraints to
admit `corpus-item` at contract `2.0.0`; the six prior kinds remain `1.0.0`.
Append-only corpus states, discovery paths, decisions and command receipts
attach to those revisions. Migration creates no historical corpus item or
researcher decision, and interruption retains the verified v16 backup.

Version 18 adds protected, append-only source/copy rights-policy revisions and
exact corpus recheck scopes. Its immutable policy snapshot keeps reported
license/access observations separate from researcher-confirmed action grants;
neither old rows nor the migration acquire new permission. Rights changes
publish provenance, outbox and recheck authority atomically. A pending scope
blocks use, survives restart, and closes only after bounded recheck work has a
verified completion receipt. Populated v17 import and connector fixtures prove
backup, row preservation, reopen, and interruption recovery.
The v17-to-v18 migration also appends an exact `rights_legacy_output_rechecks`
marker for every existing corpus output/path membership. Where a retained
SourceAssertion matches uniquely, the marker binds its revision; otherwise it
records that the historical source is unresolved. Every marker remains
`requires-review`: migration neither grants rights nor clears the marker.
Bounded per-output inspection and Canvas presentation are T03 follow-on work.

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
