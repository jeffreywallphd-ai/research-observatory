---
id: ADR-0034
title: Introduce a versioned corpus-item core aggregate
status: Accepted
date: 2026-09-30
deciders:
  - CAP-04.S04.T01 implementation architecture decision by codex-w2-implementation under repository-owner W2 packet approval at c85a59f3a293f8e3f2eaf6454682c9a14b1efa55; independent review recorded in artifacts/evidence/CAP-04.S04.T01.architecture-review.md
linked_tasks:
  - CAP-04.S04.T01
decision_scope: Versioned v2 portable CoreAggregate for corpus-item, source-retaining v1 read bridge, and forward-only v17 protected Core persistence under approved CAP-04.S04.T01; mixed v1/v2 process advertisements fail closed until separately authorized v2 process negotiation.
affected_paths:
  - packages/contracts/domain/**
  - packages/contracts/corpus/**
  - packages/contracts/storage/**
  - packages/contracts/package.json
  - packaging/build-inputs.json
  - quality-scope.json
  - services/core-api/src/research_observatory_core/domain_contracts_v2.py
  - services/core-api/src/research_observatory_core/provenance.py
  - services/core-api/src/research_observatory_core/storage.py
  - services/core-api/src/research_observatory_core/repositories.py
  - services/core-api/src/research_observatory_core/migrations/**
  - services/core-api/src/research_observatory_core/ports/repositories.py
  - services/core-api/src/research_observatory_core/ports/corpus.py
  - services/core-api/src/research_observatory_core/corpus/**
  - services/core-api/src/research_observatory_core/corpus_repository.py
  - services/core-api/src/research_observatory_core/corpus_service.py
  - services/core-api/src/research_observatory_core/corpus_query.py
  - services/core-api/src/research_observatory_core/corpus_contracts.py
  - tests/contracts/test_corpus_contracts.py
  - tests/contracts/test_domain_contracts_v2.py
  - tests/reconciliation/test_corpus_migration.py
  - tests/corpus/**
  - tests/service/test_corpus_provenance_type.py
  - docs/architecture/local-sqlite-storage.md
supersedes: []
superseded_by: null
---

# ADR-0034: Introduce a versioned corpus-item core aggregate

## Context

The approved W2 `CAP-04.S04.T01` task requires a project-scoped corpus item with
durable identity, discovery provenance, and reversible, reasoned membership
decisions. ADR-0013 makes `domain-core.schema.json` the strict v1 portable
aggregate authority. Its closed `AggregateKind` omits `corpus-item`, even though
the separately governed v1 lifecycle profile already has a `corpus-item`
subject. The v1 core schema, lifecycle, compatibility policy, release fixtures,
generated decoders, and accepted-authority catalog are hash-bound predecessor
bytes. Adding the enum member in place would make an old reader reject new
records while representing both as the same contract release.

The frozen W2 slice plan names candidate, included, excluded, pending,
duplicate, unavailable, and withdrawn outcomes. The accepted v1 lifecycle has
candidate, included, excluded, and withdrawn states. Pending review, duplicate
relationships, and access unavailability describe separate dimensions; making
each an exclusive membership state would erase simultaneous facts (for example,
an included item can have an unavailable copy). Source-specific evidence and
researcher decisions must remain visible and cannot be inferred from a status
label.

## Candidates

1. Add `corpus-item` to the v1 closed enum and regenerate its readers. This is
   small in code, but breaks the exact v1 release/catalog binding and permits
   old and new readers to disagree while both advertise `1.0.0`.
2. Encode corpus items as v1 `record` or `decision` aggregates. This preserves
   v1 bytes, but misstates the aggregate kind and invites downstream consumers
   to interpret membership as source-record or decision authority.
3. Introduce a separate v2 core schema and generated readers, retaining all v1
   bytes. Admit exact v1 records through a visibly tagged, source-preserving
   candidate read bridge. This adds versioned contract maintenance and a later
   acceptance/negotiation step, but keeps old readers honest.

## Decision

Select candidate 3. The
`domain-core.v2.schema.json` retains the v1 UUIDv7, revision, source anchor,
epistemic, confidence, rights, and semantic rules; its envelope requires
`schemaVersion: "2.0"` and `contractVersion: "2.0.0"`, and its closed aggregate
kind adds `corpus-item`. The opt-in `generate.mjs --v2` path emits strict
TypeScript and Python decoders with a SHA-256 of the v2 schema. The default v1
generator must continue to emit byte-identical v1 readers.

The read bridge accepts only an exact `1.0.0` v1 envelope validated
by the unchanged v1 decoder or an exact `2.0.0` envelope validated by v2. It
returns an immutable, source-version-tagged snapshot, never fabricates a corpus
identity, upgrades a v1 kind, or changes the original identity/revision/rights.
The bridge's witness pins both schema digests and this ADR identity;
substituted witness fields and unknown versions deny. The witness is a local
reader check, **not** authorization to negotiate v2 across processes. The
generated `domain-compatibility-authorities.v2.json` catalog binds the exact
v1/v2 core and corpus schema bytes, immutable v1 fixture, bridge test, and this
ADR's status and scope. It becomes an accepted authority only with an Accepted ADR and
passing compatibility evidence; it does not rewrite the v1 catalog or its
historical releases.

The v17 Core migration transactionally rebuilds the common identity and
revision tables to admit `corpus-item` as a first-class aggregate kind and
accepts the exact v2 envelope for that kind only. Existing aggregate kinds
and rows remain v1 with unchanged identities and values. Corpus state, discovery paths, decisions, and command
replay are append-only, project-scoped subtype records attached to the generic
aggregate revision. A protected writer transaction verifies the exact Work,
source, actor, Intent, and evidence authorities before publishing the revision,
provenance, outbox, and dependency effects together. An interruption must leave
the v16 predecessor recoverable from a verified backup; a successful migration
must retain every predecessor identity and revision and pass restart checks.

Membership decisions continue to use the existing `corpus-item` lifecycle's
candidate/included/excluded/withdrawn states. Pending review, duplicate
relationships, and unavailable access remain orthogonal, versioned facts in
the strict `corpus-membership.schema.json` portable contract and generated
TypeScript/Python validators. The corpus schema pins the unchanged v1 lifecycle
source and transitions. Each discovery path records its root context, source,
direction, canonical time, and prior item revision (null only at entry). Paths
bind an exact import member, protected query/page/record, or human-attested
citing Work and retained source assertion;
a citation path does not claim machine verification of a citation relationship.
Each state decision retains actor, reason, governing Intent revision, prior value,
evidence, time, and supersession. A denied or unknown right grants no use.
Entry creates only the fixed candidate/pending/unknown/no-duplicate condition;
it is a discovery fact, not a human inclusion judgment. Every later condition
change requires a reasoned decision over the exact prior revision.
Neither the common aggregate `status` epistemic field nor a renderer label is
canonical corpus membership.

The pre-acceptance independent architecture review is recorded in
`artifacts/evidence/CAP-04.S04.T01.architecture-review.md`. The existing
compatibility policy classifies a closed-enum addition as breaking. Before v2
becomes persisted canonical authority, the source-retaining bridge, fixture,
and generated accepted-authority catalog entry must pass. A v1-only component
must fail closed on v2. The existing
schema-set equality and exact-version overlap checks deny mixed v1/v2 process
advertisements; this task must test that denial with the exact generated v2
schema identity. Advertising v2 to a desktop, sidecar, or server requires a
separately reviewed process-negotiation authority and is outside this decision.

## Consequences

The explicit v2 kind prevents semantic aliasing and lets downstream clients
distinguish corpus membership from source records and decisions. Versioned
readers preserve existing v1 source/revision/rights facts. The cost is a second
generated schema and a gated compatibility transition, not a change to the v1
lifecycle or current process-negotiation behavior.

The accepted decision will authorize a forward-only protected database migration,
but no network path. Core persistence, atomic provenance/outbox publication,
restart, and rollback require the `CAP-04.S04.T01` service/migration evidence;
this record does not declare them complete. Action-specific rights policy
remains `CAP-04.S04.T02`. Local Windows x64 LOC/LAB is the W2 target.
Unsupported or tampered schema identity denies without copying private source
content into diagnostics. Rollback before v2 publication is removal of the
candidate reader; after publication it requires an explicit v1-compatible
reader or retained source migration, not relabeling v2 bytes as v1.

## Verification

`packages/contracts/domain/domain-v2.test.ts` and
`tests/contracts/test_domain_contracts_v2.py` cover v1 rejection of v2,
v2 acceptance of the corpus kind, v2 rejection of v1, source-preserving exact
v1 read behavior, generated schema SHA-256 binding, and substituted witness
and catalog denial. Exact v1/v2 advertisements must deny mixed-version process
negotiation; the v2 schema identity must be generated from the catalog, not
caller-supplied. A literal populated v16 fixture, protected v17 migration,
backup/retry/reopen, and Core writer rollback tests cover storage authority.
The corpus contract generator and tests reject malformed or substituted
membership, decision, and discovery documents and verify the exact frozen
lifecycle source hash across TypeScript and Python. The protected Core writer
validates these portable documents before publication.
`generate.mjs --check`, `generate.mjs --v2
--check`, and `generate-v2-authority.mjs --check` detect drift.
The existing v1 contract, lifecycle, and compatibility tests remain required
to demonstrate byte-preserving predecessor behavior. Independent review must
inspect the acceptance and mixed-version boundary before any status change.

## Task links

- `CAP-04.S04.T01`
