---
id: ADR-0021
title: Adopt provider-neutral model task and result contracts
status: Accepted
date: 2026-08-28
deciders:
  - W1 repository-owner pre-Wave approval at 594e63be501711d67d17a4aef176bb9b6a8748be
linked_tasks:
  - CAP-07.S01.T01
decision_scope: Provider-neutral model task kinds, content-reference inputs, execution constraints, result provenance, validation, usage, confidence, citations, and explicit unsupported-feature behavior.
affected_paths:
  - packages/contracts/model-gateway/**
  - packages/contracts/package.json
  - packages/contracts/tsconfig.json
  - packages/contracts/README.md
  - services/core-api/src/research_observatory_core/model_gateway_contracts.py
  - services/core-api/README.md
  - tests/ai/**
  - packaging/build-inputs.json
  - quality-scope.json
  - docs/architecture/model-gateway-contracts.md
  - docs/architecture/README.md
supersedes: []
superseded_by: null
---

# ADR-0021: Adopt provider-neutral model task and result contracts

## Context

The W1 model-gateway contribution must establish a durable boundary before a
local runtime, remote adapter, routing engine, or prompt registry is introduced.
Research tasks differ materially: an embedding request, an NLI judgment, a
structured extraction, and a tool call do not share one safe input or output
shape. Provider SDK request types also expose transport and vendor assumptions
that cannot become the application contract.

Every result must remain attributable to the exact request, policy decision,
route, provider, model, runtime, configuration, evaluation baseline, latency,
usage, validation, confidence, and citations. A required capability that is not
available must fail explicitly; silent model substitution would invalidate
reproducibility and could cross a policy or data boundary.

## Candidates

1. Standardize on one provider SDK and expose its request/result types.
2. Use one generic chat message DTO for every AI operation.
3. Define provider-neutral, task-specific envelopes with a common execution and
   result-provenance boundary; keep provider translation inside adapters.

## Decision

Adopt candidate 3. The portable contract defines explicit task kinds for
embedding, reranking, classification, NLI, structured extraction, generation,
moderation, and tool call. Each kind has a distinct input envelope. Inputs carry
versioned aggregate/revision/content hashes rather than raw research text,
filesystem paths, provider objects, or credentials.

A task declares data class, citation requirement, deadline, token bounds,
required features, and either dynamic or exact pinned execution. A pinned task
names provider, model, runtime, configuration, and evaluation identities and
versions. Any selected result route must match those values exactly; a router
may not silently substitute another model for a reproducible request.

Every result has one common envelope containing task and request identity,
status, selected or explicitly absent route, policy decision, queue/execution/
total latency, token-reporting state, validation outcome, confidence,
citation state, output or null, and stable content-free diagnostics. Successful
and degraded results require an allowed policy decision, selected route,
accepted validation, and an output matching the task kind. Other statuses carry
no output. Reported usage cannot exceed the task token bounds, and a successful
result cannot exceed its declared deadline. Accepted artifact output is bound
to validation by the same content hash; rejected and not-run validation states
carry state-consistent output hashes and error codes. Every supplied citation,
whether required or optional, must close over an immutable task input.
Reranking, classification, NLI, and moderation scores also close over the
corresponding input indices, labels, and cardinality.

Feature matching is fail-closed. A valid task with unsupported required
features produces `model-task-feature-unsupported`; an unsupported result has
no route or output, a denied policy projection, validation `not-run`, and the
same stable diagnostic. Invalid tasks use `model-task-invalid`. Neither path
copies research content into diagnostics.

The Draft 2020-12 schema is the language-neutral authority. A deterministic,
newline-portable generator embeds its exact canonical hash and emits checked-in
TypeScript and Python decoders. Both decoders reject unknown fields, unsafe
object keys, non-finite or unsafe numeric values, and semantic inconsistencies,
then return owned deeply immutable snapshots.

## Consequences

Provider adapters, routing, fallback policy, local model lifecycle, prompt
registries, and remote egress remain later tasks. They must consume this
contract and may not introduce provider SDK types into the application or
contract packages. Dynamic routing can be implemented later, but pinned tasks
remain exact and unsupported requirements remain explicit.

The first contract version intentionally transports content identity rather
than content bytes. A future task that needs a different reference type or task
kind must follow the domain compatibility and ADR process; it cannot repurpose
an existing field or overload the generation envelope.

## Verification

- Draft 2020-12 validation of complete task and result fixtures;
- deterministic Python/TypeScript generation and exact schema-hash checks;
- all eight task-specific input envelopes;
- complete pinned route and result provenance;
- explicit content-free unsupported-feature behavior;
- rejection of raw-content injection, unknown fields, request mismatch,
  over-budget or inconsistent usage, deadline overrun, validation-hash drift,
  citation drift, indexed-output drift, and pinned-route substitution; and
- owned immutable snapshots in both generated runtimes.

## Task links

- `CAP-07.S01.T01`
