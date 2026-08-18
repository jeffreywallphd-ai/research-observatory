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
uses create-if-absent publication before committing metadata. A crash before the
metadata commit can leave at most an unreferenced complete file; it is not visible
through the port. Partial staging files are reconciled on restart. Duplicate puts
with identical immutable metadata return the existing projection; metadata reuse
with a different meaning conflicts.

Open first verifies the entire held file, exact length, digest, single-link
identity, and readable rights state. Only then does it return a controlled stream
over that same read-only handle. It never returns a path. Missing, redirected,
hardlinked, length-mismatched, or digest-mismatched content is unavailable and the
metadata advances to `quarantined`. Delete is denied while any immutable document
revision references the object.

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
- denied/unknown rights states cannot be opened;
- immutable document references drive counts and prevent deletion;
- port-only import remains dependency-neutral and concrete adapter imports are
  rejected outside the composition/data boundary.
