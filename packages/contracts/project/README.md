# Local project package contract

`project.ro.json` is the only plaintext project-root manifest. It carries only
canonical identity, format, compatibility, lifecycle, and storage-profile
metadata. It deliberately contains no project title, research content, path,
credential, key, endpoint, or provider field.

`project-layout.v1.json` is the executable layout authority. Every location is
project-relative and uses `/` as a contract separator; Core resolves it beneath
the selected project home. Callers must not concatenate untrusted paths or infer
authority from directory names.

The portable inventory is the manifest plus entries marked `include`. Indexes,
caches, model working data, logs, locks, and temporary work are excluded. Shared
model binaries are application-level resources outside this package and are
never deleted as a consequence of deleting one project.

Breaking manifest or layout changes require a new version, reader, migration or
bridge, pre-migration backup, and a superseding ADR. Unknown top-level fields
fail closed; future extensibility is introduced through a versioned contract,
not by accepting arbitrary fields.

Manifest validation always applies both `project-manifest.schema.json` and its
bound `project-manifest.semantic-rules.json`. The schema owns constraints it can
express; the two exact semantic operators enforce ascending application
compatibility and `createdAt <= modifiedAt`. The compatibility rule also fixes
every release-version component to the shared `0..9007199254740991` numeric
domain so language runtimes cannot disagree through numeric precision. Treating
schema-only validation as successful validation is a contract violation.

`fixtures/` supplies a valid relocatable current manifest, an intentionally
invalid path-bearing manifest, and exact older/newer safe-open fixtures. The
older/newer fixtures deliberately fall outside the current writable manifest
schema. Core may inspect their stable identity envelope, but it must never
claim that they satisfy the current writable contract.

Safe-open has three machine states: `compatible`, `migration-required`, and
`newer-unsupported`. Only `compatible` may become `read-write`. A structurally
sound older or newer envelope may become `read-only` without changing any
project-package byte. A malformed current envelope is `damaged`; a missing
required package entry is `incomplete`. Both fail before lock or audit writes
and return backup-first recovery guidance. Migration and repair operate only
on a verified working copy; CAP-02.S02 and CAP-02.S05 own the later migration
and backup implementations.

`project-profile.schema.json`, `project-lock.schema.json`, and
`project-lifecycle-event.schema.json` bind the implemented local lifecycle.
The profile owns the display name and template selection inside the package;
the lock owns exclusive local session identity; lifecycle events contain only
bounded event/state/trace/time metadata. None permits project content, absolute
paths, credentials, or arbitrary extension fields.

Explicit Windows recovery uses four authenticated Core API commands for preview,
confirm, status and cancel. The portable lock retains its exact seven fields.
Native-owned process/principal proof and immutable dual-DPAPI witnesses live in
the private application profile, outside the project/export contract. Missing,
changed or terminal proof and any live, reused or unknown owner deny recovery;
heartbeat age never grants authority.

Confirmation verifies a new staging copy, including complete canonical facts and
encrypted object inventory, while preserving all original bytes and the old
lock. Its staged old lock is archived as operational evidence. A successful copy
adds only the existing five-field lifecycle record with event
`project.recovery-copy-verified`, then publishes into an absent destination.
Normal explicit open supplies new ownership; verification alone leaves the copy
closed. See ADR-0054 and `docs/architecture/project-package.md` for the private
authority, cancellation and operation-owned quarantine boundaries.
