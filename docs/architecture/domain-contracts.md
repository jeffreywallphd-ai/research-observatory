# Portable core domain contracts

The portable core contract is the shared, framework-neutral vocabulary for
durable scholarly aggregates. It is governed by
[ADR-0013](../adr/ADR-0013-adopt-uuidv7-aggregate-identities-and-schema-generated-domain-contracts.md)
and implemented in [`packages/contracts/domain/`](../../packages/contracts/domain/).

## Identity and revision

- `aggregateId` is the stable canonical lower-case UUIDv7 identity of the
  scholarly aggregate.
- `revisionId` is a distinct immutable UUIDv7 identity for one serialized
  revision.
- `revision` is a non-negative JavaScript-safe integer used for optimistic
  concurrency, never a substitute for revision identity.
- `createdAt` and `modifiedAt` are canonical UTC instants. UUID timestamp order
  is useful for locality but does not replace recorded scholarly chronology.
- The trusted Core boundary mints IDs with operating-system cryptographic
  randomness. Desktop and worker consumers validate IDs but do not mint
  canonical authority.

UUIDs identify objects; they are neither secrets nor permissions. They contain
no user identity, local path, project title, provider, or research content.

## Scholarly meaning

The contract covers the principal project, record, document, evidence,
decision, workflow, ontology, graph, opportunity, and monitoring-event kinds.
Each envelope carries:

- exact observed display wording plus an optional normalization;
- independently sourced candidate, disputed, accepted, or rejected
  alternatives—the original is never overwritten;
- explicit epistemic status, including distinct unknown, not-reported,
  not-applicable, ambiguous, disputed, and unavailable states;
- quantified, qualitative, unknown, or not-applicable confidence;
- allowed, denied, unknown, or not-applicable rights, with unknown granting no
  action and consequential decisions bound to source references; and
- typed source anchors and external identifiers with no filesystem path.

External-identifier validation is scheme-aware: DOI, arXiv, Handle, and HTTP(S)
forms may retain their governed separator syntax, while bare Windows or POSIX
path forms are rejected. Decoders validate an owned snapshot rather than a
caller-owned object. TypeScript returns deeply frozen null-prototype records;
Python returns a read-only `Mapping`/tuple graph and exposes
`core_aggregate_snapshot_json` for canonical serialization. These boundaries
prevent both post-validation mutation and mutable base-class bypasses.

Aggregate-specific fields and lifecycle transitions are intentionally not in
this common envelope. CAP-03.S01.T02 owns lifecycle invariants; T03 owns
compatibility, deprecation, and migration rules.

The T02 lifecycle profile, deterministic validators, persistence-boundary
contract, and diagrams are documented in [Domain lifecycles](domain-lifecycles.md).

## Authority and generation

`domain-core.schema.json` is the Draft 2020-12 wire authority. The schema also
declares the small language-neutral cross-field rule set for timestamp order and
distinct aggregate/revision identity. `generate.mjs` emits strict TypeScript and
Python types/decoders and binds each artifact to the raw schema SHA-256.

Run the focused contract checks with:

```powershell
.local\toolchains\node-v24.19.0-win-x64\node.exe packages/contracts/domain/generate.mjs --check
.local\toolchains\node-v24.19.0-win-x64\corepack.cmd pnpm --dir packages/contracts verify
.venv\Scripts\python.exe -m unittest tests.contracts.test_domain_contracts
```

The project manifest in ADR-0012 remains a documented version-1 UUIDv4 bridge.
It is accepted only by that project-package contract and must not be passed as a
canonical aggregate ID. T03 owns the explicit compatibility bridge or migration;
no reader may silently relabel an existing UUIDv4 value as UUIDv7.
