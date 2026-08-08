---
plan_schema_version: '1.1'
document_type: slice-implementation-plan
baseline: '1.3'
supplemental_release: 1.3.4
capability_id: CAP-06
capability_plan: planning/capability-plans/CAP-06.md
planning_gate: capability-decision-complete
slice_id: CAP-06.S02
title: Semantic representations and vector retrieval
status: proposed
wave: W3
priority: P0
deployment_profiles:
- LOC
- LAB
- ALL
platform_targets:
- windows-x64
task_ids:
- CAP-06.S02.T01
- CAP-06.S02.T02
- CAP-06.S02.T03
ui_reference: RO-UI-ACADEMIC-MINIMAL-1.3
approval:
  status: pending
  approved_by: null
  approved_at: null
  approved_commit: null
---
# CAP-06.S02 — Semantic representations and vector retrieval

> **Implementation gate — proposed plan.** This slice may not begin until `planning/capability-plans/CAP-06.md` is decision-complete and approved, this plan is approved, all required ADRs are accepted or explicitly waived, and both plan validators pass in approval mode. Once the capability campaign starts, the agent should execute continuously through its slices and pause only for an allowed infeasibility, external dependency, unavailable required hardware, explicit human decision, or approved design gate.

<div class="visual-flow"><span>Capability decisions approved</span><b>→</b><span>Slice plan approved</span><b>→</b><span>Tasks executed</span><b>→</b><span>Slice integration</span><b>→</b><span>Independent review</span></div>

## 0. Plan control

| Field | Value |
|---|---|
| Capability | `CAP-06` — Local search, discovery, corpus diagnostics, and screening |
| Capability objective | Deliver transparent lexical, semantic, citation, and active-learning workflows that can construct high-recall corpora without turning retrieval into an opaque chat session. |
| Slice | `CAP-06.S02` — Semantic representations and vector retrieval |
| Slice outcome | Conceptually related literature is retrievable through a replaceable, versioned local embedding interface. |
| Wave / priority | `W3` / `P0` |
| Deployment profiles | `LOC`, `LAB`, `ALL` |
| Platform targets | `windows-x64` |
| Backlog tasks | `CAP-06.S02.T01`, `CAP-06.S02.T02`, `CAP-06.S02.T03` |
| Slice dependencies | `CAP-06.S01.T02`, `CAP-07.S01.T03` |
| Capability decision packet | `planning/capability-plans/CAP-06.md` — must be approved and decision-complete |
| Approved experience | `RO-UI-ACADEMIC-MINIMAL-1.3`; relevant pages: search-studio.html, corpus-canvas.html, screening.html |
| Approval state | `PROPOSED` / human approval pending |

## 1. Purpose and contribution to the larger vision

Conceptually related literature is retrievable through a replaceable, versioned local embedding interface.

This slice advances the capability objective: **Deliver transparent lexical, semantic, citation, and active-learning workflows that can construct high-recall corpora without turning retrieval into an opaque chat session.** It is designed as one production vertical inside a long-running capability campaign, not as an isolated technical experiment. The implementation must preserve the platform’s evidence-before-prose rule, source and decision provenance, bounded uncertainty, researcher authority, local-first privacy, cross-platform ports, and the distinction between canonical scholarly state and rebuildable analytical derivatives.

**Implementation thesis.** Create source-grounded scientific embeddings through a model- and engine-neutral contract, benchmark the leading local adapter on Windows, and preserve exact-search and full-rebuild paths when semantic infrastructure is unavailable.

The containing capability is complete only when all of its slices satisfy these exit conditions:

- Lexical and semantic indexes are versioned, explainable, rebuildable, and usable offline for project content.
- Search evolution is stored as a visible tree of exact queries, transformations, results, and discovery paths.
- Screening supports human inclusion decisions, uncertainty/random audits, stopping evidence, and reproducible exports.

## 2. Scope

### 2.1 In scope

- Embedding/chunk/model manifest contracts and compatibility checks.
- Local scientific embedding baseline with offline install, batching and cancellation.
- Filtered vector indexing, health, rebuild, migration and exact-cosine fallback.
- Benchmark/ADR evidence for the selected local adapter.

### 2.2 Explicit non-goals

- Hybrid fusion and reranking policy (S03).
- Remote-only embeddings or hidden provider-managed indexes.
- Treating embedding proximity as evidence of relevance, similarity of claims or novelty.
- Do not implement downstream capability behavior beyond narrow ports, fixtures and handoffs explicitly named here.
- Do not introduce university-hosted or managed-cloud infrastructure during the local Windows waves; preserve deployment-neutral contracts only.
- Do not bypass the Core API, canonical repositories, provenance ledger, durable workflow fabric, rights policy, model gateway or approved experience reference.
- Do not declare completion from happy-path task tests alone; slice-wide failure, cancellation, restart, migration, security, accessibility and handoff evidence is required.

### 2.3 Slice boundary

- **Consumes:** `CAP-06.S01.T02`, `CAP-07.S01.T03` and the handoffs in Section 13.
- **Produces:** Conceptually related literature is retrievable through a replaceable, versioned local embedding interface.
- **Owns:** The portable domain contracts, adapter boundaries, workflows, fixtures, decisions and evidence explicitly listed in this plan.
- **Does not own:** Product purpose, unrelated capabilities, user-authoritative scholarly judgments, source rights, or provider/database/UI framework internals.

## 3. Authority, dependencies, and campaign stop conditions

### 3.1 Governing authority

1. Vision and non-goals in `docs/product/vision.md`.
2. Accepted ADRs, then `docs/architecture/source/systems-design.md`.
3. `planning/backlog.yaml` for IDs, dependencies, waves, status and evidence.
4. Approved capability decision packet `planning/capability-plans/CAP-06.md`.
5. This approved slice plan.
6. Approved UI reference, workflow/page contracts and style guide for user-facing work.
7. Automation and task-control rules.

### 3.2 Required upstream state

- All slice dependencies are approved or an explicitly approved integration stub exists: `CAP-06.S01.T02`, `CAP-07.S01.T03`.
- The capability decision packet contains all material cross-slice choices, candidate options, recommendation, accepted selection, migration boundary and approval.
- Every slice plan in the capability exists and is structurally valid before capability approval; all plans are approved before campaign start.
- Required fixtures, benchmark corpora, credentials, model/source licenses, platform resources and human authority are available or represented by approved deterministic stubs.

### 3.3 Decision-complete capability rule

Planning by capability is the default. Before `capability start`, the planning agent inspects all slices and adjacent contracts, researches credible options, and records the strongest best-in-class recommendation as the selected and accepted option for every material decision in the capability packet. Those selections count as completed decisions. The static review site is a confirmation-and-override surface plus the one-time capability approval gate; implementation agents must not repeatedly ask for choices already settled by the packet. After approval, execution proceeds continuously slice by slice through a production-ready end-to-end capability.

### 3.4 Allowed pauses after execution begins

The long-running campaign should continue task-by-task and slice-by-slice. It may pause only when classified as one of the following and recorded by `taskctl`:

- **Infeasible:** validated evidence disproves the selected design and no compatible fallback exists within the approved boundary.
- **External dependency:** a required source/provider/license/credential/approval controlled outside the repository is unavailable.
- **Hardware unavailable:** a required qualification target cannot be simulated and is not accessible.
- **Human decision:** a newly discovered consequential product, architecture, security, rights, ethics or scholarly-authority choice was not reasonably knowable during planning.
- **Approved design gate:** the implementation requires an intentional change to the governed style guide/workflow/page reference.

Ordinary implementation uncertainty, test failure, debugging, refactoring, model fallback, recoverable performance work, or a choice already covered by the packet is not a pause condition.

## 4. Selected implementation decisions

The capability packet's researched best-in-class recommendations are already selected, accepted, and decision-complete. This section projects the applicable decisions into the slice implementation contract. Capability approval authorizes those defaults; a reviewer may override a selection before approval only with explicit rationale. During execution, no implementation agent may silently choose a different candidate.


These selections are recommendations until the capability packet and ADRs are approved. Approval turns them into the execution contract for the campaign.

| Decision | Recommended selection | Alternative not selected | Rationale and replaceability | Basis |
|---|---|---|---|---|
| **Representation unit** | Create separate work-level title/abstract vectors and passage-level vectors; every vector stores source revision and chunk selector. | One vector per PDF or unanchored fixed-token chunks. | Work vectors support discovery while passage vectors support evidence retrieval; provenance remains exact. | [Web Annotation Data Model](https://www.w3.org/TR/annotation-model/) |
| **Baseline model** | Benchmark SPECTER2 retrieval and adhoc-query adapters as the initial scientific baseline; pin revision/license and allow ONNX or Transformers execution. | Use a general-purpose embedding model without scientific evaluation. | SPECTER2 supplies scientific training and task adapters, but the gateway contract keeps it replaceable. | [AllenAI SPECTER2 Model Card](https://huggingface.co/allenai/specter2) |
| **Index adapter** | Approve Qdrant sidecar only if Windows install, filtering, recovery, portability and latency tests pass; retain exact NumPy/SQLite candidate fallback for small corpora. | Use Qdrant local mode as if it had service snapshot parity; store vectors in canonical relational rows for every query. | A supervised service gives production health/filtering, while fallback protects correctness and offline continuity. | [Qdrant Snapshots](https://qdrant.tech/documentation/concepts/snapshots/) |

## 5. Architecture and implementation design

### 5.1 Components and recommended repository locations

| Component / location | Responsibility |
|---|---|
| `packages/contracts/representation` | EmbeddingRequest, VectorRecord, model/index manifests and compatibility rules. |
| `services/core/research_observatory/ports/vector_index.py` | Stable filtered upsert/delete/search/snapshot/rebuild interface. |
| `services/workers/embedding` | Batching, model lifecycle, cancellation and resource profiles. |
| `services/core/research_observatory/adapters/vector/qdrant` | Leading local/service adapter behind ADR. |
| `services/core/research_observatory/adapters/vector/exact` | Portable exact cosine fallback for fixtures and bounded corpora. |
| `tests/benchmarks/retrieval` | Known-neighbor, recall, latency, recovery and rights fixtures. |

The paths are recommendations within the approved modular-monolith/package structure. Exact filenames may change without a new decision if module ownership, portable contracts and dependency directions remain intact.

### 5.2 Data model and durable state

| Entity / value object | Required semantics |
|---|---|
| `EmbeddingModelManifest` | model ID/revision/hash/license, task adapter, dimensions, normalization, runtime and hardware profile |
| `ChunkManifest` | document revision, selectors, text hash, language and chunking version |
| `VectorCollectionManifest` | engine, schema, model compatibility, filters, build snapshot, status and checkpoint |
| `VectorSearchHit` | target/source anchor, distance/similarity signal, model and collection lineage |

**Cross-cutting invariants**

- Canonical records, accepted evidence, rights decisions, human adjudications and provenance are authoritative; indexes, graph projections, rankings, generated drafts and detector signals are versioned derivatives.
- Unknown, not reported, not applicable, denied, unavailable, ambiguous, inferred, disputed, stale and failed remain distinct where relevant.
- Every long-running operation has stable identity, status, inputs/manifests, progress, cancellation, checkpoint, restart and evidence records.
- State transitions are authorized in core services and committed atomically with outbox/dependency facts or through an idempotent staged protocol.

### 5.3 Interfaces and contracts

- `EmbeddingPort.embed(batch, model_manifest, cancel_token)` produces deterministic records within documented tolerance.
- `VectorIndex.upsert/delete` are idempotent by vector ID and source revision.
- `VectorIndex.search(query_vector, filters, limit, exact)` returns model-compatible hits only.
- `VectorIndex.snapshot/restore/health/rebuild` expose engine-neutral operational state.

All contracts use stable canonical IDs, explicit revisions/status, typed errors and version metadata. Provider SDK objects, SQLite rows, model tensors, graph library objects and UI component state may not cross the owning adapter boundary.

### 5.4 Cross-capability and platform compatibility

- Windows x64 is the current implementation target, but paths, process control, credential storage, accelerators and packaging stay behind adapters required by CAP-14 macOS/Linux qualification.
- Local and hosted deployments use the same domain/API/workflow semantics; storage, process, authentication and scaling adapters differ later.
- Downstream CAP-11–19 consume immutable IDs, evidence/provenance, manifests and ports rather than internal tables or framework classes.
- Model, embedding, reranker, parser, graph and vector choices are pinned and replaceable; changing one marks exact dependents stale and requires evaluation rather than silent regeneration.

## 6. User experience and approved reference

- Model Center guides download/consent and reports disk, memory and expected time.
- Search Studio identifies semantic model/index version and allows exact fallback when semantic search is unavailable.
- Rebuild and model upgrade are explicit, cancelable operations with old index retained until activation.

- Workflow navigation must show the project’s selected use case, current numbered stage, completed/upcoming states, expected output and next/previous actions.
- Supporting tools remain accessible, but opening one explains its relationship to the primary path and offers return to the current stage.
- All semantic states use text/icon in addition to color, meet WCAG 2.2 AA targets, support keyboard operation, and have light/dark parity.
- Loading, empty, offline, partial, denied, stale, cancellation, failure, retry and recovery states are designed—not left as generic alerts.

**Reference-first rule.** If the planned experience materially differs from `RO-UI-ACADEMIC-MINIMAL-1.3`, update the style guide, workflow catalog, page contract and HTML prototype; run reference validators; obtain explicit approval and a new reference ID; only then implement application code. Restoring a defect to the approved reference does not require a new reference.

## 7. Security, privacy, rights and research integrity

- Verify model hashes and licenses before activation; default to safetensors/GGUF or other inspected formats.
- No document text leaves the device for local embedding; model/runtime cannot read outside approved project/cache paths.
- Vector metadata carries rights/access tags; deletion is required on rights/access change.

Additional mandatory controls:

- Treat source content, metadata, model files, provider responses, reports, URLs, archives and rich text as untrusted.
- Apply least privilege, schema/input validation, destination/path controls, bounded resources, output encoding and redacted diagnostics at trusted boundaries.
- Private projects and unpublished ideas remain local by default; egress requires project policy, rights decision and visible payload/provider preview.
- Never fabricate evidence, citations, availability, permissions, method details, model certainty, benchmark success or completion evidence.
- AI output is candidate state until the domain-specific verifier/human gate promotes it.

## 8. Failure, cancellation, restart and recovery

| Material scenario | Required durable and user-visible behavior |
|---|---|
| Model absent or incompatible | Return guided setup and keep lexical search operational. |
| Runtime OOM | Reduce batch size, unload model, record failure and offer CPU or smaller model profile. |
| Index service unavailable | Use bounded exact fallback where feasible; otherwise show unavailable state without corrupting corpus. |
| Model upgrade | Mark incompatible collection stale, build shadow collection and activate only after validation. |

Every scenario receives a deterministic fixture where feasible, expected canonical state, expected derivative state, user message/action, retry/cancel rule, cleanup/repair rule, provenance event and automated test. A restart test must execute from persisted state rather than from an in-memory mock alone.

## 9. Task-by-task implementation plan

### CAP-06.S02.T01 — Define embedding, chunking, vector-index, and compatibility contracts

**Objective.** Interfaces for document/passage representations, model manifests, dimensions, normalization, chunk provenance, filters, and rebuild state.

| Control | Value |
|---|---|
| Dependencies | `CAP-06.S01.T02`, `CAP-07.S01.T03` |
| Estimate / risk | `L` / `high` |
| Review gate | `agent-review` |
| Verification profiles | `search`, `ai` |

**Expected deliverables**

- Interfaces for document/passage representations, model manifests, dimensions, normalization, chunk provenance, filters, and rebuild state.

**Ordered implementation sequence**

1. Confirm the approved capability decision packet, this approved slice plan, dependencies, portable contracts, and criterion-to-evidence IDs for `CAP-06.S02.T01`. Add a failing success-path test and at least one material denial/failure/restart case before production code.
2. Define the versioned portable schema and invariants first. Validate examples and negative fixtures; keep provider, database, model, graph, and UI framework types behind adapters.
3. Implement the domain/core path behind the selected port, with explicit transaction or idempotency boundaries, bounded resources, durable checkpoints, cancellation, and restart semantics.
4. Implement the approved Academic Minimal route and workflow state using shared components. Cover keyboard/focus, screen reader names, light/dark, loading, empty, offline, denied, stale, error and recovery states; update and approve the reference before any intentional UX divergence.
5. Pin model, prompt/schema, runtime/provider and evaluation manifests. Enforce local schema validation, source/evidence closure, egress policy and deterministic fallback; treat model output as untrusted candidate state.
6. Exercise security, privacy, rights and research-integrity boundaries with malformed/untrusted inputs, authorization denial, confidential-content redaction and unsupported-state fixtures. Failure must leave canonical state unchanged or exactly recoverable.
7. Run the task verification profiles plus targeted unit, contract, integration and end-to-end tests. Capture named reports, manifests, performance evidence and changed-contract hashes against the reviewed commit.
8. Request independent review focused on acceptance coverage, architecture compatibility, test validity, portability and concealed production blockers. Do not self-approve or advance the slice until review is approved.

**Acceptance criteria from the authoritative backlog**

- Indexes reject incompatible vectors; every vector resolves to source text and model version; contract supports embedded and server engines.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Criterion-linked evidence required**

- Reviewed commit SHA, changed-file inventory, and explanation for any change outside the expected task boundary.
- Named automated tests and report paths mapped to every acceptance criterion.
- Durable failure, denial, cancellation, restart and recovery evidence appropriate to the task.
- Architecture, security, rights, accessibility, model-evaluation and approved-reference evidence when applicable.
- Updated schemas, client/adapter contracts, migrations, fixtures, model/index manifests and documentation hashes.
- Independent reviewer result. The implementation agent may not self-approve.

**Backlog verification commands**

```text
python tools/verify.py --profile search
python tools/verify.py --profile ai
```


### CAP-06.S02.T02 — Integrate a local scientific embedding baseline

**Objective.** Packaged or user-installed local embedding option with model-license metadata, resource profile, batching, cancellation, and deterministic fixture behavior.

| Control | Value |
|---|---|
| Dependencies | `CAP-06.S02.T01` |
| Estimate / risk | `L` / `high` |
| Review gate | `agent-review` |
| Verification profiles | `search`, `ai`, `e2e-local` |

**Expected deliverables**

- Packaged or user-installed local embedding option with model-license metadata, resource profile, batching, cancellation, and deterministic fixture behavior.

**Ordered implementation sequence**

1. Confirm the approved capability decision packet, this approved slice plan, dependencies, portable contracts, and criterion-to-evidence IDs for `CAP-06.S02.T02`. Add a failing success-path test and at least one material denial/failure/restart case before production code.
2. Define the versioned portable schema and invariants first. Validate examples and negative fixtures; keep provider, database, model, graph, and UI framework types behind adapters.
3. Pin model, prompt/schema, runtime/provider and evaluation manifests. Enforce local schema validation, source/evidence closure, egress policy and deterministic fallback; treat model output as untrusted candidate state.
4. Build from an immutable snapshot into a staging destination; apply rights filters, produce checksums/manifests, verify independently, then atomically finalize. Test cancellation, disk failure and round trip.
5. Exercise security, privacy, rights and research-integrity boundaries with malformed/untrusted inputs, authorization denial, confidential-content redaction and unsupported-state fixtures. Failure must leave canonical state unchanged or exactly recoverable.
6. Run the task verification profiles plus targeted unit, contract, integration and end-to-end tests. Capture named reports, manifests, performance evidence and changed-contract hashes against the reviewed commit.
7. Request independent review focused on acceptance coverage, architecture compatibility, test validity, portability and concealed production blockers. Do not self-approve or advance the slice until review is approved.

**Acceptance criteria from the authoritative backlog**

- A supported CPU-only machine can index the fixture corpus offline; unavailable model produces guided setup rather than failing the project; output provenance is complete.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Criterion-linked evidence required**

- Reviewed commit SHA, changed-file inventory, and explanation for any change outside the expected task boundary.
- Named automated tests and report paths mapped to every acceptance criterion.
- Durable failure, denial, cancellation, restart and recovery evidence appropriate to the task.
- Architecture, security, rights, accessibility, model-evaluation and approved-reference evidence when applicable.
- Updated schemas, client/adapter contracts, migrations, fixtures, model/index manifests and documentation hashes.
- Independent reviewer result. The implementation agent may not self-approve.

**Backlog verification commands**

```text
python tools/verify.py --profile search
python tools/verify.py --profile ai
python tools/verify.py --profile e2e-local
```


### CAP-06.S02.T03 — Implement local vector indexing, filtered similarity search, and rebuild

**Objective.** Benchmark, select through ADR, and implement a replaceable local vector adapter with incremental updates, metadata filtering, nearest-neighbor query, health checks, exact-search fallback, and model-change migration.

| Control | Value |
|---|---|
| Dependencies | `CAP-06.S02.T02` |
| Estimate / risk | `L` / `high` |
| Review gate | `agent-review` |
| Verification profiles | `search`, `data` |

**Expected deliverables**

- Benchmark, select through ADR, and implement a replaceable local vector adapter with incremental updates, metadata filtering, nearest-neighbor query, health checks, exact-search fallback, and model-change migration.

**Ordered implementation sequence**

1. Confirm the approved capability decision packet, this approved slice plan, dependencies, portable contracts, and criterion-to-evidence IDs for `CAP-06.S02.T03`. Add a failing success-path test and at least one material denial/failure/restart case before production code.
2. Define the versioned portable schema and invariants first. Validate examples and negative fixtures; keep provider, database, model, graph, and UI framework types behind adapters.
3. Implement the domain/core path behind the selected port, with explicit transaction or idempotency boundaries, bounded resources, durable checkpoints, cancellation, and restart semantics.
4. Implement the approved Academic Minimal route and workflow state using shared components. Cover keyboard/focus, screen reader names, light/dark, loading, empty, offline, denied, stale, error and recovery states; update and approve the reference before any intentional UX divergence.
5. Pin model, prompt/schema, runtime/provider and evaluation manifests. Enforce local schema validation, source/evidence closure, egress policy and deterministic fallback; treat model output as untrusted candidate state.
6. Use the declared representative corpus and gold queries to measure recall, ranking quality, bias/coverage and latency. Record ablations and make degraded/fallback behavior user-visible.
7. Exercise security, privacy, rights and research-integrity boundaries with malformed/untrusted inputs, authorization denial, confidential-content redaction and unsupported-state fixtures. Failure must leave canonical state unchanged or exactly recoverable.
8. Run the task verification profiles plus targeted unit, contract, integration and end-to-end tests. Capture named reports, manifests, performance evidence and changed-contract hashes against the reviewed commit.
9. Request independent review focused on acceptance coverage, architecture compatibility, test validity, portability and concealed production blockers. Do not self-approve or advance the slice until review is approved.

**Acceptance criteria from the authoritative backlog**

- Windows install, recovery, filtering, portability, corpus-size, latency, and rebuild benchmarks support the selected adapter and ADR; semantic known-neighbor tests meet baseline; deletion and rights changes remove or quarantine vectors; model upgrade marks the index stale and requires explicit rebuild.
- Automated tests cover the expected path and at least one material failure or boundary condition.
- Relevant contracts, migrations, fixtures, documentation, and audit behavior are updated without unrelated scope expansion.

**Criterion-linked evidence required**

- Reviewed commit SHA, changed-file inventory, and explanation for any change outside the expected task boundary.
- Named automated tests and report paths mapped to every acceptance criterion.
- Durable failure, denial, cancellation, restart and recovery evidence appropriate to the task.
- Architecture, security, rights, accessibility, model-evaluation and approved-reference evidence when applicable.
- Updated schemas, client/adapter contracts, migrations, fixtures, model/index manifests and documentation hashes.
- Independent reviewer result. The implementation agent may not self-approve.

**Backlog verification commands**

```text
python tools/verify.py --profile search
python tools/verify.py --profile data
```


## 10. Slice-wide verification matrix

| Verification family | Required slice evidence |
|---|---|
| Domain and schema | Contract examples/negative cases; invariants and state transitions; stable IDs/revisions; property tests where valuable. |
| Adapter and integration | Real local adapters with deterministic fixtures; idempotency; concurrency; transaction/outbox/dependency behavior; replaceability test double. |
| End-to-end | Approved workflow from entry point through durable result, source inspection, user decision and restart. |
| Failure and recovery | At least the Section 8 cases, cancellation acknowledgement, process restart, corrupted/partial derivative repair and no canonical loss. |
| Security, privacy and rights | Authorization denial, prompt/source injection, malformed files/payloads, secret/content redaction, egress and export policy. |
| Accessibility and UI reference | Route/page contract, shared tokens, light/dark, keyboard, focus, screen reader, zoom/reflow and visual-baseline checks. |
| Performance and capacity | Declared fixtures, warm/cold measurements, p50/p95, memory/disk/model footprint, cancellation and regression threshold. |
| Cross-capability | Upstream fixture compatibility, downstream contract fixture, staleness propagation and no forbidden module dependency. |
| Independent review | Reviewer maps every criterion to evidence, challenges tests and confirms no concealed production blocker. |

Task verification commands are authoritative minimums. The slice review must also run a clean-state combined profile and any benchmark/security/reference checks described here.

## 11. Performance and resource budgets

| Measure | Initial production budget / qualification target |
|---|---|
| Query embedding | p95 < 2 s CPU and < 500 ms supported GPU after warm-up for baseline query size. |
| Vector search | p95 < 500 ms for top-100 filtered search at 100,000 work vectors on reference adapter. |
| Fixture indexing | 1,000 title/abstract records complete offline within 10 min on reference CPU-only machine. |
| Recovery | Health failure detected < 10 s; exact fallback or guided recovery available without project corruption. |

Budgets are evaluated on documented reference hardware and corpus fixtures. A regression exceeding 20% or violating a hard interaction/resource limit blocks approval unless a reviewed explanation and revised target are accepted before implementation proceeds.

## 12. Observability and provenance

Required metrics and diagnostics:

- embedding throughput and batch size
- model load time/memory
- vector search latency/recall
- fallback use
- collection stale/build state
- rights deletions
- benchmark results by model/engine/hardware

- One trace/correlation ID links desktop action, core command, workflow job, adapter/model call, provenance activity and evidence artifact.
- Operational telemetry is content-redacted by default. Durable scholarly provenance records source IDs/passages/hashes, schema/policy/model versions, decisions and derivation—not secret-bearing logs.
- Support bundles require user preview and classification-aware exclusion of source text, research ideas, prompts and unpublished results.
- Every promoted output records dependencies so CAP-03 can mark it stale precisely.

## 13. Adjacent-slice handoffs

- Consumes CAP-07 model task/runtime contracts and CAP-05 anchored passages.
- Provides semantic retriever and manifests to CAP-06.S03, CAP-09 synthesis and CAP-10 novelty.
- Supplies benchmark evidence for W6 cross-platform qualification.

Handoffs must include portable schemas, accepted/rejected examples, failure fixtures, manifest/version rules, performance baselines and evidence IDs. An informal README-only handoff is insufficient.

## 14. Migration and backward compatibility

- Version every durable schema, policy, model/index/graph manifest and export profile. Use forward migrations with preflight, backup, rollback/repair evidence and test fixtures from the prior supported release.
- Rebuilding a derivative does not mutate canonical evidence/decisions. Old and new derivative versions remain distinguishable until promotion and dependent staleness are resolved.
- Project moves and later Windows/macOS/Linux qualification cannot rely on absolute paths or machine-specific IDs in portable records.
- Deprecations include reader compatibility, warnings, migration telemetry and a declared removal release. Unsupported old projects open read-only with repair/export options rather than silent partial upgrade.

## 15. Required slice evidence bundle

- Approved capability decision packet and this approved slice plan at immutable commits.
- Reviewed commits/diffs for all tasks and criterion-to-evidence records.
- Unit, contract, integration, end-to-end, failure, cancellation, restart, recovery, migration and performance reports.
- Security/privacy/rights/research-integrity review and accessibility/UI conformance evidence where applicable.
- Schemas, migrations, API/client fixtures, model/index/graph manifests, benchmark datasets and hashes.
- Architecture dependency report, staleness/provenance traces and adjacent-slice handoff fixture.
- Independent slice review with approved/changes-requested/blocked outcome.

## 16. Definition of Ready

- Capability packet is decision-complete and approved; each decision lists options, recommendation, accepted selection and migration boundary.
- This plan and all other capability slice plans exist, pass structural checks and are approved.
- Required ADRs/experience changes are approved before the campaign starts.
- Dependencies, fixtures, credentials/licenses, platform resources and human authorities are available or explicitly stubbed.
- The first task is `READY`, no conflicting lease exists, and the campaign can plausibly run to production-ready capability completion without routine stop points.

## 17. Definition of Done

- Every task is `DONE` and independently approved.
- Slice-wide verification passes from a clean state on the required platform/profile.
- Failure, denial, cancellation, restart, migration, recovery, security, accessibility and performance paths satisfy this plan.
- No concealed TODO, placeholder, skipped mandatory test, unreviewed architecture divergence or production blocker remains.
- Handoff contracts/fixtures and dependency/staleness behavior are accepted by the next slice.
- The capability campaign automatically advances to its next dependency-ready slice.

## 18. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Scientific-domain mismatch | Evaluate multiple disciplines and query types; do not promote the baseline without gold-set evidence. |
| Native sidecar fragility | Supervise health, pin versions and retain exact fallback. |
| Embedding drift | Model/chunk manifests mark dependent indexes and outputs stale. |

## 19. Required ADRs and human decisions

- ADR-CAP06-EMBEDDING: baseline model/runtime and distribution.
- ADR-CAP06-VECTOR: local adapter selection from Windows benchmark.

All material choices in Sections 4–5 must appear in the capability packet. Before approval, reviewers may accept the recommendation, select a documented alternative, or require more evidence. After capability start, these choices are not reopened for preference; they are reopened only when implementation evidence demonstrates infeasibility or a newly discovered consequential issue outside the approved decision envelope.

## 20. Research and standards basis

- **SciRepEval: A Multi-Format Benchmark for Scientific Document Representations** — Scientific document embedding baseline and task-specific adapters.  
  https://aclanthology.org/2023.emnlp-main.338/
- **AllenAI SPECTER2 Model Card** — Model files, adapters, licensing, dimensions and integration notes.  
  https://huggingface.co/allenai/specter2
- **Qdrant Filtering** — Metadata-filtered vector retrieval.  
  https://qdrant.tech/documentation/concepts/filtering/
- **Qdrant Snapshots** — Vector index backup, recovery and portability constraints.  
  https://qdrant.tech/documentation/concepts/snapshots/
- **ONNX Runtime Execution Providers** — Portable CPU/CUDA/DirectML/CoreML inference for embedding, reranking and classification models.  
  https://onnxruntime.ai/docs/execution-providers/
- **Safetensors Documentation** — Safer tensor serialization and model artifact inspection.  
  https://huggingface.co/docs/safetensors/index
- **Hugging Face Hub Cache Management** — Content-addressed model cache, revisions, cleanup and offline behavior.  
  https://huggingface.co/docs/huggingface_hub/guides/manage-cache

These sources support implementation choices, not universal truth claims. Production selection remains conditional on project-specific benchmarks, licenses, privacy/rights constraints and the accepted capability decision packet.

## 21. AI implementation runbook

1. Run `python tools/planctl.py ready CAP-06 --require-approved` and `python tools/taskctl.py validate`.
2. Confirm the active campaign is `CAP-06`, this is the current slice, and the approved packet/plan commits match the campaign record.
3. Load only the governing context, capability packet, this slice plan, task record, affected code and tests.
4. Execute all tasks in dependency order. Debug, refactor and use approved fallbacks without routine human pauses.
5. After each task, run focused verification, attach criterion-linked evidence and obtain independent task review.
6. After the last task, run the complete Section 10 matrix from a clean/restarted state and assemble the slice evidence bundle.
7. Request independent slice review. On approval, let `taskctl` advance the campaign automatically to the next slice.
8. Pause only with an allowed category from Section 3.4 and exact evidence/next action. Do not self-approve, weaken tests, alter approved UX after implementation, or declare production readiness from narrative evidence.
