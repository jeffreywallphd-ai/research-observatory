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
lifecycles remain a separate governed contract: `domain-lifecycle.schema.json`
and `domain-lifecycle.v1.json` define eight deterministic state machines whose
generated Python and TypeScript validators derive the destination, require
actor/reason and optimistic revision identity, reject unknown commands before
persistence, and make terminal/reopen rules explicit. The compatibility schema,
exact policy, accepted-authority catalog, event catalog, current/prior release
fixtures, and generated TypeScript/Python runtimes classify additive,
deprecated, and breaking evolution. Breaking changes must match hash-bound
accepted ADR, migration fixture, and compatibility-test evidence. The boundary
preserves the legacy UUIDv4 reader bridge, rejects unknown event payload fields,
publishes exactly one bounded content-free audit fact for an unknown
event/version, and selects only the highest exact common contract and event
versions advertised by desktop, sidecar, and optional server roles.

`storage/` defines the exact portable `sqlite-wal-v1` profile: application and
schema identity, UUID/timestamp representation, scalar-only STRICT table
inventory, connection controls, checkpoint authority, and integrity checks.
The profile is not a SQL or filesystem API; only Core's governed storage
adapter opens the project database.
The companion `sqlcipher-4.12-community-wal-v1` protection profile fixes the
Windows W1 production encryption, vault-key, plaintext-denial, migration,
backup/restore, rekey, integrity, licensing, and residual OS-protection boundary
without exposing database handles or secret material.
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
adapter state. It also defines the current three-mode native-supervisor
application sign-in policy and the immutable password-profile migration
predecessor: explicit no-login default, optional local display identity,
bounded idle policy, native Windows-password or Windows Hello proof,
confirmation-bound compare-and-swap transitions, protected-action invalidation,
Core capability clearing, and the explicit non-isolation residual threat.

`privacy/` fixes project-scoped offline and telemetry-off defaults, informed
consent before non-offline preferences, per-task egress preview enforcement,
non-automatic document retention review, and exact-preview-bound logical cache
removal with explicit physical-erasure limitations.

`model-gateway/` defines the provider-neutral model task and result boundary.
Eight task-specific input envelopes carry immutable content references rather
than raw research text; every result records exact route, policy, latency,
usage, validation, confidence, and citation state. Pinned tasks deny silent
substitution, and unsupported required features fail explicitly before provider
execution. The Draft 2020-12 schema deterministically generates matching
TypeScript and Python immutable decoders.

`intent/` defines the versioned Research Intent revision and downstream
governing-reference boundary. Revisions retain immediate predecessor identity
and content hash, explicit rationale and decision state, seven mode-specific
requirement branches, source/evidence/novelty/autonomy/stopping/egress policy,
and distinct unknown/not-applicable states. Only a complete human-accepted
revision can yield a governing reference. Its Draft 2020-12 schema generates
matching TypeScript and Python immutable decoders. The contract uses a closed,
level-bounded autonomy-action vocabulary, mode-closed stopping sets, and
destination-plus-human-gate consistency for any approved egress declaration.

`provenance/` defines the minimized CloudEvents-compatible scholarly event
envelope and W3C PROV-aligned Entity, Activity, Agent, and relation boundary.
Events require exact project/actor/input/output/configuration/time/trace
identity, sensitivity and retention declarations, and content-reference-only
payloads. Matching generated TypeScript/Python decoders own immutable snapshots,
retain structurally valid future types without interpreting them, and produce
deterministic RFC 8785-compatible canonical records for hash/checkpoint use.
Subjects and relations bind exact entity revisions; stable identity retains one
entity kind; and project, event, activity, agent, correlation, causation,
relation, revision, and entity identities cannot collide within an event. The
shared semantic matrix rejects duplicate or wrong-role relations, completed
PROV facts or outputs for failed/cancelled/denied outcomes, and missing
generation or attribution for any succeeded output, including future types.

`workflow/` defines executor-neutral, versioned workflow definitions and
restart-reconstructable execution snapshots. Separate workflow-run, step-run,
logical-job, physical-attempt, checkpoint, immutable-artifact, and human-task
identities use explicit state machines and append-only transition history.
Runs bind exact definition, Research Intent, policy, configuration, input/output
schema, and content hashes; stable idempotency keys bind canonical command
fingerprints across at-least-once retries. Matching generated TypeScript/Python
decoders reject illegal transitions, broken references, decreasing progress,
duplicate committed outputs, substituted human decisions, inline executor
implementation details, and security-lock auto-resume. The legacy `op-*`
record is an exact compatibility projection onto a UUIDv7 workflow run, never
canonical workflow authority. SQLite persistence and real worker restart are
owned by `CAP-03.S04.T02`.
