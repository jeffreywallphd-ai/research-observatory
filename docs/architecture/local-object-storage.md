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

## T02 authenticated-encryption boundary

`project-encrypted-v1` is the ordinary adapter profile. Put hashes plaintext while
feeding bounded memory chunks directly into libsodium secretstream
XChaCha20-Poly1305; the project temporary directory therefore contains only an
authenticated encrypted envelope, never a plaintext staging file. Each object has
a random 256-bit data key. SQLite schema v3 introduced the secretstream envelope
version, ciphertext length, master-key version, random wrapping nonce, and the data
key wrapped with XChaCha20-Poly1305 under the versioned project master-key port.
Neither key bytes nor plaintext paths enter SQLite, logs, or returned metadata.

Open obtains the exact recorded key version, unwraps the data key, authenticates
the complete held envelope, and rechecks the plaintext length and SHA-256 identity
before returning a controlled decrypting stream. Malformed magic, header, framing,
final-tag, trailing-content, or structurally invalid metadata is corrupt and is
quarantined before first-byte use. A missing key version/provider or authenticated
unwrap failure for otherwise well-formed wrapped-key metadata instead returns the
bounded `RO-CORE-OBJECT-KEY-UNAVAILABLE` failure and preserves the object for key
recovery. Wrong retained master-key bytes and a modified valid-shape wrapped key are
intentionally indistinguishable at that boundary. Rotation changes the active key
version for new objects while older objects remain readable through their recorded
version.

Schema v4 preserves the committed v3 history and adds
`object_envelope_upgrades`, the durable pre-open journal required by ADR-0016.
Prior plaintext rows are never relabeled as release-compatible fixtures. Project
open holds the exclusive session lock while each legacy source is verified, streamed
directly into an encrypted same-volume replacement, authenticated, journaled before
the guarded swap, committed with encrypted metadata, and opened through the ordinary
production reader. The original becomes a bounded rollback sibling in the objects
class—not a plaintext temporary file—and is removed only after production-open
verification. Restart reconciles the journal plus stable file identities at every
phase; it never guesses from filenames alone. Missing keys, corrupt sources,
interruption, rename failure, and SQLite failure leave either the original canonical
file or its verified rollback authority intact and keep ordinary access closed.

The normal Core composition always supplies this pre-open coordinator; it is not
an optional lifecycle behavior. Until CAP-02.S04 supplies the release credential-
store adapter, a legacy project whose master key is unavailable returns the explicit
recoverable key-unavailable state with its verified plaintext authority retained.
Deterministic hooks bracket every journal commit, replacement fsync, guarded rename,
source/replacement/production verification, metadata commit, partial/rollback cleanup,
and cancellation acknowledgement. Cancellation is accepted only at a journaled safe
phase and restart finishes or restores that exact state.

`plaintext-fixture-v1` remains available only when the adapter is constructed with
the explicit test-fixture flag. Constructing an ordinary store without a key
provider fails closed. CAP-02.S03.T03 still owns the broader reference graph,
leases, quotas, garbage collection, and cache eviction.

The exact portable policy is
[`object-store-profile.v1.json`](../../packages/contracts/storage/object-store-profile.v1.json),
governed by ADR-0015.

## Verification

- streaming, restart, duplicate, project-scope, and opaque-name fixtures;
- interrupted source and expected-hash mismatch leave no visible object or row;
- corruption and hardlink aliases are denied before a byte reaches a caller;
- v2 and committed-v3 upgrade through default Core composition, pre/post journal,
  fsync, rename, verification, metadata-commit, partial/rollback cleanup, cancellation,
  missing-key, corrupt-source, and project-open lock restart fixtures;
- magic, header, frame, final-tag, trailing-content, wrapped-key, wrap-nonce, and
  key-version adversarial classification fixtures;
- explicit plaintext fixture gating and no plaintext bytes in encrypted staging or object files;
- denied/unknown rights states and concurrent rights transitions cannot overtake
  an authorized held stream;
- crash recovery distinguishes pre-commit delete restoration from post-commit
  delete cleanup;
- immutable document references drive counts and prevent deletion;
- port-only import remains dependency-neutral and concrete adapter imports are
  rejected outside the composition/data boundary.
