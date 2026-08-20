# Portable contracts

Owner: Research Observatory maintainers
Boundary: Schemas, API definitions, events, and generated client sources shared across processes.

Contracts must not expose operating-system paths, database connection objects,
framework components, provider SDK types, or other deployment-specific details.

`core-api/` contains the hand-authored runtime/handshake schemas plus the exact,
deterministically generated OpenAPI document and transport-neutral TypeScript
client for the local Core process. `python tools/core_api_contract.py --repo .
--check` regenerates both artifacts in memory and rejects any committed drift.

The package is source-only and side-effect-free. Application code imports
`@research-observatory/contracts/core-api`; it never imports Core implementation
modules or reconstructs private launch state.

`support-bundle/support-bundle.schema.json` is the portable, strict schema for
the CAP-01.S04 redacted support document. The native host and renderer own the
preview/export envelope because local output paths are privileged host state;
the path never appears in the portable support document. Schema version `1.0`
caps recent code-only diagnostics and defines the exact included and excluded
categories without admitting research content, credentials, raw logs, process
identifiers, or absolute storage paths.

`project/` defines the versioned, relocatable local project manifest and exact
classified storage layout. Its runtime decoder fails closed on unknown or
path-bearing manifest fields, and its portable inventory excludes every cache,
index, model-working, log, lock, and temporary entry.

`domain/` defines the common UUIDv7 aggregate/revision envelope and strict
value objects for observed wording, alternatives, source anchors, epistemic
status, confidence, rights, and external identifiers. The Draft 2020-12 schema
is language-neutral authority; `node domain/generate.mjs --check` proves the
checked-in TypeScript and Python contracts match its exact bytes. Aggregate
lifecycles and compatibility evolution remain separate governed contracts.

`storage/` defines the exact portable `sqlite-wal-v1` profile: application and
schema identity, UUID/timestamp representation, scalar-only STRICT table
inventory, connection controls, checkpoint authority, and integrity checks.
The profile is not a SQL or filesystem API; only Core's governed storage
adapter opens the project database.
It also defines the `project-object-store-v1` policy: project-scoped plaintext
content identity, opaque physical identity, complete-file publication,
metadata/reference authority, verified controlled streams, rights states, and
the explicit T01-to-T02 encryption handoff. The contract exposes no filesystem
path or database handle.

`security/` defines the portable `windows-dpapi-profile-vault-v1` policy record
for local secrets. It fixes current-user rather than machine DPAPI scope, an
application-authenticated opaque record envelope, compare-and-swap updates,
callback-scoped delivery, redacted audit projection, and the exact destinations
that can never contain secret material. OS paths and DPAPI types remain private
adapter state.
