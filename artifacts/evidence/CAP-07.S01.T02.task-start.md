# CAP-07.S01.T02 — model registry acceptance closure

## Authority and baseline

- Objective: installed/available model discovery, licenses, capabilities, context,
  modalities, hardware, quality and allowed data classes; versioned, visible
  changes and no eligibility without capability and permission.
- W1 approval: `c5bbd97c0cdc665eecb973f5862478ef7be97752`; CAP-07 decisions
  D01 and D06–D08; CAP-07.S01 sections 5–8 and the T02 criteria; ADR-0021.
- Dependency CAP-07.S01.T01 is complete. Its model-task schema, immutable
  decoders, reference-only inputs and exact reproducibility pins remain intact.
- Original claim base: `949f8a37ec9a5cb48b9f0e4ea9c2cc1a30e4e4a5` (verified
  ancestor). Resume predecessor: `f5f4bf24008ebd57d08e194e1c700ee83cbd8552`.
  The controller retains claim history. Evidence must distinguish the full
  claim-base inventory from this implementation increment and intervening
  independently reviewed work; do not silently rebase the claim.
- Current Core is `services/core-api/src/research_observatory_core`, not the
  illustrative location in the slice. Lifecycle-gated protected project storage,
  typed repository ports, stable Core actor, provenance and outbox already exist.
  No model registry or production runtime inventory is implemented.
- Frozen capability-campaign/proposed boilerplate in the approved slice does not
  supersede the actual approved W1 packet. The later approved Academic Minimal
  1.6 reference supersedes the slice's older visual reference; preserve existing
  semantic bridges rather than rewriting frozen plans.

## Bounded implementation decisions

Separate Core-owned host inventory/observations from project-local immutable
catalog history. A saved declaration, copied project or renderer value cannot
establish installed status, current readiness, evaluation qualification or
permission. Availability observations bind exact manifest/runtime identities
and freshness; missing or expired witnesses deny eligibility after restart.
Production has an honest empty inventory until an actual runtime adapter exists.
Synthetic positive models belong only in test fixtures.

Use a typed project repository and lifecycle action seam for versioned catalog
snapshots, expected-revision/idempotency checks and atomic audit/outbox facts.
Actor identity comes from Core composition, never request metadata. Read-only
inspection must not create a revision. Trusted discovery can refresh the
catalog; the renderer cannot submit installed/qualified/allowed flags.

Matching intersects capabilities, modalities, context/resource envelopes, exact
pins, current host/evaluation observations and a current trusted policy/rights
witness. Four data classes are not a substitute for source licensing. Return
stable rejections and identity-bound eligible candidates, not execution or a
continuing permission grant. Reauthorize before eventual T03 dispatch.

Non-goals: model downloads/installation, provider SDKs or credentials, live
inference, remote egress, evaluation runs, W3 runtime persistence, T03 fallback,
timeouts/circuit breakers, and unrelated styling. Do not fabricate those features
or derive their authority from illustrative reference controls.

## Material acceptance map

| Surface | Required outcome / failure | Planned proof |
|---|---|---|
| Portable manifest | Strict, bounded, owned metadata and exact identities; unknown fields/invalid revisions/unsafe numbers rejected; T01 unchanged | Schema/client generation checks, positive/negative manifest fixtures, T01 regression |
| Eligibility | Reject missing task kind/features/modalities/context, unqualified evaluation, insufficient hardware, disallowed class/license, stale policy/rights and pin substitutions | Parameterized matcher tests; deterministic candidate ordering; 1,000-manifest timing |
| Availability | Catalog presence never means installed/ready; stale/restarted observation denies; fresh exact fixture observation permits | Separate inventory-port fixtures; default production inventory empty |
| Durable catalog | Monotonic immutable revisions; no-op retry idempotent; changed-payload key reuse/conflict/corruption fail closed | Actual protected fixture database reconstruction, history and hash checks |
| Atomicity / principal | Project identity, open session, write compatibility and Core actor required; catalog, audit and outbox commit together | Lifecycle integration; wrong project/actor/closed/read-only denials; injected transaction failure and concurrent CAS |
| User visibility | Catalog revision/history, declared vs observed availability, capabilities, evaluation and policy reasons visible; empty/unavailable distinct | Real Core API + generated client contract; Model Center component tests |
| Approved experience | Reuse shared primitives/tokens; supporting-tool context/return; light/dark, keyboard, responsive, loading/empty/error/read-only states | Academic Minimal 1.6 model-center contract mapping, affected renderer/conformance checks |
| Evidence truth | Exact committed inputs; distinguish mocks, real persistence/API/renderer and native proof | Criterion-linked check manifest and independent high-risk task review |

First tests precede production code: manifest ownership/validation, capability
and pin denials, empty/stale observation, permission denial and deterministic
ranking. Persistence and UI tests follow their contract before adapters/views.

Advisory preflight by `agent:/root/registry_persistence_preflight` incorporated:
host/project authority separation, separate source-rights check, stable actor,
freshness, atomicity and no invented production availability. This is not an
approval or new gate. No mandatory gate discovered.

Task checks are the affected unit/contract, protected persistence, authenticated
API/client, build/type/lint and focused UI paths. Slice review adds integrated
routing/adversarial proof with CAP-07.S01.T03. Native application, packaging,
cross-capability and full-profile qualification remain required at W1 exit;
no mock or browser check will be relabeled as native proof.

## Implementation closure notes

The task adds an opt-in shared wrapping utility after a long-identifier reflow
failure; it preserves complete metadata without new page-specific spacing.
The existing desktop verifier now observes the shared Notification primitive,
ninth tool, additional context-bound requests and honest empty catalog state.
No previous required workspace/primitive or negative assertion is removed.
Native/benchmark capability inventories and generated product identity include
the two new catalog operations.

Quality scope registers all ten new Python files. The existing build-input
inventory gains the new manifest schema and the already-existing, previously
omitted `enabler-change-request.v4.1.schema.json`. This is a mechanical inventory
correction against predecessor `b643ecbd`, not a schema or approval change; its
only intended delta is complete schema coverage, checked against discovery and
included in the independent review.

Draft checks exposed stale generated build inputs, outdated eight-tool/request
expectations and omitted shared Notification measurement; these were corrected
before commit-bound qualification. A broader exploratory mypy invocation also
reported an unchanged typing error at `selective_recalculation.py:834`; this task
does not alter it or claim full-service type qualification. Fresh affected checks
and the later Wave matrix remain separate obligations.

The unchanged commit guard rejected a new generated public schema digest and a
literal synthetic test token as possible credentials. The digest was verified
against exact OpenAPI bytes; generation now names the public digest explicitly
and preserves the existing exported constant as an alias. The new and affected
Core API tests use ephemeral tokens instead of committed token literals. Scanner rules,
sealed admissions, hook inputs and the privacy baseline remain unchanged.
