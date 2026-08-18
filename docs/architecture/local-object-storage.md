# Local object storage

The W1 local object store is a project-scoped adapter behind the dependency-neutral
`ObjectStore` port. It stores no binary content in SQLite and returns no filesystem
path. SQLite `object_records` remains metadata authority; immutable document
revisions are the first canonical reference authority, so reference counts are
derived rather than maintained as drift-prone counters.

## T01 content and publication boundary

Plaintext SHA-256 is the immutable content identity inside one project. A physical
name is derived with HMAC-SHA-256 using the project identity, so a directory listing
does not directly disclose the plaintext digest and identical content in different
projects does not share a physical identity. Cross-project deduplication is
deliberately absent.

Put streams into an exclusive project `.tmp/object-store` file, hashes while
writing, fsyncs, verifies stable single-link identity and complete content, then
uses create-if-absent publication while retaining the verified file handle through
the definitive metadata commit. Commit-acknowledgement ambiguity is reconciled
against the canonical row before any newly published file can be removed. Partial
put staging is removed on restart. Delete recovery staging is instead named by the
project-scoped opaque object identity: restart restores exact bytes when metadata
did not commit the delete and removes the recovery copy only when metadata is
already `deleted`.

Open reserves the canonical metadata transaction, verifies current readable rights
and `available` state, then verifies the entire held file, exact length, digest,
and single-link identity. The reserved transaction and same read-only file handle
remain owned by the controlled stream until close, so a rights/state transition or
delete cannot overtake plaintext use. A concurrent delete receives bounded busy
retry semantics rather than corrupting metadata. Missing, redirected, hardlinked,
length-mismatched, or digest-mismatched content is unavailable and advances to
`quarantined`. Repository transactions may link a document only to a currently
`available` object, while delete is denied when any immutable document revision
already references it.

An unreferenced byte put does not invent a scholarly provenance claim. The
canonical document-repository transaction that links an object to an immutable
revision also appends its provenance and outbox facts; that linkage is the first
auditable reference authority. T03 later adds audited garbage-collection and
cache decisions.

## Deliberate staged boundary

`plaintext-fixture-v1` is an intermediate T01 adapter profile, not release-qualified
protection for sensitive research. CAP-02.S03.T02 replaces the byte adapter with
authenticated streaming encryption, versioned wrapped data keys, and protected
temporary-memory handling without changing plaintext content identity or the port.
CAP-02.S03.T03 extends the canonical reference graph, leases, quotas, garbage
collection, and cache eviction. Neither later responsibility is claimed by T01.

The exact portable policy is
[`object-store-profile.v1.json`](../../packages/contracts/storage/object-store-profile.v1.json),
governed by ADR-0015.

## Verification

- streaming, restart, duplicate, project-scope, and opaque-name fixtures;
- interrupted source and expected-hash mismatch leave no visible object or row;
- corruption and hardlink aliases are denied before a byte reaches a caller;
- denied/unknown rights states and concurrent rights transitions cannot overtake
  an authorized held stream;
- crash recovery distinguishes pre-commit delete restoration from post-commit
  delete cleanup;
- immutable document references drive counts and prevent deletion;
- port-only import remains dependency-neutral and concrete adapter imports are
  rejected outside the composition/data boundary.
