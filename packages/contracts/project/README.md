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

`fixtures/` supplies one valid relocatable manifest and one intentionally
invalid path-bearing manifest for downstream readers and compatibility tests.

`project-profile.schema.json`, `project-lock.schema.json`, and
`project-lifecycle-event.schema.json` bind the implemented local lifecycle.
The profile owns the display name and template selection inside the package;
the lock owns exclusive local session identity; lifecycle events contain only
bounded event/state/trace/time metadata. None permits project content, absolute
paths, credentials, or arbitrary extension fields.
