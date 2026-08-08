---
plan_schema_version: '1.1'
document_type: capability-decision-plan
baseline: '1.3'
supplemental_release: 1.3.4
capability_id: CAP-07
title: Provider-neutral model gateway and governed AI execution
status: proposed
execution_mode: long-running-capability-campaign
decision_completion: complete
open_blocking_decisions: []
slice_ids:
- CAP-07.S01
- CAP-07.S02
- CAP-07.S03
- CAP-07.S04
- CAP-07.S05
decisions:
- id: CAP-07-D01
  title: Gateway domain boundary
  candidates:
  - Provider-neutral task/result envelopes and model manifests owned by the core; provider SDK types remain inside adapters
  - Expose one provider SDK directly to application modules
  recommendation: Provider-neutral task/result envelopes and model manifests owned by the core; provider SDK types remain inside adapters
  recommendation_basis: Stable task contracts let local, university and cloud deployments change models without rewriting scholarly workflows.
  selected_option: Provider-neutral task/result envelopes and model manifests owned by the core; provider SDK types remain inside adapters
  status: accepted
  required_adr: null
- id: CAP-07-D02
  title: Local generative runtime
  candidates:
  - Supervised llama.cpp sidecar with pinned GGUF model manifests; ONNX Runtime for suitable encoders/classifiers
  - Embed a single Python transformers runtime for every model class; require Docker locally
  recommendation: Supervised llama.cpp sidecar with pinned GGUF model manifests; ONNX Runtime for suitable encoders/classifiers
  recommendation_basis: The split uses cross-platform runtimes according to model workload while preserving offline desktop operation.
  selected_option: Supervised llama.cpp sidecar with pinned GGUF model manifests; ONNX Runtime for suitable encoders/classifiers
  status: accepted
  required_adr: null
- id: CAP-07-D03
  title: Structured output authority
  candidates:
  - JSON Schema post-validation is authoritative; provider grammar/tool constraints are optimization only
  - Trust provider “structured output” success without local validation
  recommendation: JSON Schema post-validation is authoritative; provider grammar/tool constraints are optimization only
  recommendation_basis: Provider constraints can differ or fail open; deterministic local validation and repair/retry policy must fail closed.
  selected_option: JSON Schema post-validation is authoritative; provider grammar/tool constraints are optimization only
  status: accepted
  required_adr: null
- id: CAP-07-D04
  title: Remote provider release baseline
  candidates:
  - Two adapters selected by capability/privacy/cost evidence, with OpenAI- and Anthropic-compatible contracts first and Gemini-ready port
  - Build separate workflow logic for each provider
  recommendation: Two adapters selected by capability/privacy/cost evidence, with OpenAI- and Anthropic-compatible contracts first and Gemini-ready port
  recommendation_basis: Two adapters prove portability; later providers enter through the same gateway and egress policy.
  selected_option: Two adapters selected by capability/privacy/cost evidence, with OpenAI- and Anthropic-compatible contracts first and Gemini-ready port
  status: accepted
  required_adr: null
- id: CAP-07-D05
  title: AI telemetry
  candidates:
  - OpenTelemetry GenAI conventions with content redaction by default and separate durable scholarly provenance
  - Store complete prompts and outputs in ordinary logs
  recommendation: OpenTelemetry GenAI conventions with content redaction by default and separate durable scholarly provenance
  recommendation_basis: Operational observability must not leak confidential research content and is distinct from auditable project evidence.
  selected_option: OpenTelemetry GenAI conventions with content redaction by default and separate durable scholarly provenance
  status: accepted
  required_adr: null
- id: CAP-07-D06
  title: Task taxonomy
  candidates:
  - Use explicit task kinds—generation, structured extraction, embedding, reranking, classification/NLI, moderation and tool call—with task-specific input/result envelopes.
  - One generic chat-completions DTO.
  recommendation: Use explicit task kinds—generation, structured extraction, embedding, reranking, classification/NLI, moderation and tool call—with task-specific input/result envelopes.
  recommendation_basis: Different tasks have different determinism, batching, evidence and failure semantics; a chat envelope would leak provider assumptions.
  selected_option: Use explicit task kinds—generation, structured extraction, embedding, reranking, classification/NLI, moderation and tool call—with task-specific input/result envelopes.
  status: accepted
  required_adr: null
- id: CAP-07-D07
  title: Capability matching
  candidates:
  - Route on declared task capabilities, data policy, context limits, structured-output support, deployment, evaluation status and resource/cost envelope.
  - Route by model name string from each feature.
  recommendation: Route on declared task capabilities, data policy, context limits, structured-output support, deployment, evaluation status and resource/cost envelope.
  recommendation_basis: A policy decision belongs in one auditable gateway and can be evaluated centrally.
  selected_option: Route on declared task capabilities, data policy, context limits, structured-output support, deployment, evaluation status and resource/cost envelope.
  status: accepted
  required_adr: null
- id: CAP-07-D08
  title: Fallback
  candidates:
  - Ordered policy with deadline budget, retry classification and explicit degraded result; no silent provider/model substitution for pinned reproducible runs.
  - Retry every error indefinitely or silently switch models.
  recommendation: Ordered policy with deadline budget, retry classification and explicit degraded result; no silent provider/model substitution for pinned reproducible runs.
  recommendation_basis: Fallback improves availability only when the scholarly meaning and disclosure remain clear.
  selected_option: Ordered policy with deadline budget, retry classification and explicit degraded result; no silent provider/model substitution for pinned reproducible runs.
  status: accepted
  required_adr: null
- id: CAP-07-D09
  title: Runtime split
  candidates:
  - llama.cpp/GGUF for local generative LLMs; ONNX Runtime or evaluated native library for encoders/rerankers/classifiers; both supervised as replaceable sidecars/workers.
  - One monolithic Python transformers service for every workload.
  recommendation: llama.cpp/GGUF for local generative LLMs; ONNX Runtime or evaluated native library for encoders/rerankers/classifiers; both supervised as replaceable sidecars/workers.
  recommendation_basis: The split improves cross-platform packaging and resource efficiency while the gateway hides runtime details.
  selected_option: llama.cpp/GGUF for local generative LLMs; ONNX Runtime or evaluated native library for encoders/rerankers/classifiers; both supervised as replaceable sidecars/workers.
  status: accepted
  required_adr: null
- id: CAP-07-D10
  title: Artifact acceptance
  candidates:
  - Pinned revision, cryptographic hash, license/use metadata, architecture, tokenizer and runtime compatibility required before activation.
  - Download latest by mutable model name.
  recommendation: Pinned revision, cryptographic hash, license/use metadata, architecture, tokenizer and runtime compatibility required before activation.
  recommendation_basis: Reproducibility, security and legal use require immutable artifacts and explicit consent.
  selected_option: Pinned revision, cryptographic hash, license/use metadata, architecture, tokenizer and runtime compatibility required before activation.
  status: accepted
  required_adr: null
- id: CAP-07-D11
  title: Hardware profiles
  candidates:
  - Detect CPU/RAM/GPU/VRAM/driver and choose conservative approved profiles with user override; no automatic remote fallback.
  - Optimistically allocate all GPU/RAM.
  recommendation: Detect CPU/RAM/GPU/VRAM/driver and choose conservative approved profiles with user override; no automatic remote fallback.
  recommendation_basis: Research desktops and DGX-class lab machines vary widely; adaptive limits prevent instability.
  selected_option: Detect CPU/RAM/GPU/VRAM/driver and choose conservative approved profiles with user override; no automatic remote fallback.
  status: accepted
  required_adr: null
- id: CAP-07-D12
  title: Initial adapters
  candidates:
  - Implement OpenAI-compatible and Anthropic Messages/tool-use adapters first; retain a Gemini adapter contract and add only after conformance/evaluation.
  - Implement every provider at once.
  recommendation: Implement OpenAI-compatible and Anthropic Messages/tool-use adapters first; retain a Gemini adapter contract and add only after conformance/evaluation.
  recommendation_basis: Two materially different APIs validate the gateway without diluting security and evaluation work.
  selected_option: Implement OpenAI-compatible and Anthropic Messages/tool-use adapters first; retain a Gemini adapter contract and add only after conformance/evaluation.
  status: accepted
  required_adr: null
- id: CAP-07-D13
  title: Egress unit
  candidates:
  - Resolve and display the exact minimized payload after prompt assembly, including attachments, before first use or policy-sensitive changes.
  - Consent to “AI usage” generically.
  recommendation: Resolve and display the exact minimized payload after prompt assembly, including attachments, before first use or policy-sensitive changes.
  recommendation_basis: Researchers need concrete control over confidential literature, reports and manuscripts.
  selected_option: Resolve and display the exact minimized payload after prompt assembly, including attachments, before first use or policy-sensitive changes.
  status: accepted
  required_adr: null
- id: CAP-07-D14
  title: Offline enforcement
  candidates:
  - Central network policy plus adapter deny-by-default; no automatic remote fallback from a local task unless project policy explicitly permits it.
  - Let connection failure determine offline behavior.
  recommendation: Central network policy plus adapter deny-by-default; no automatic remote fallback from a local task unless project policy explicitly permits it.
  recommendation_basis: Offline/privacy intent must be enforced before network activity.
  selected_option: Central network policy plus adapter deny-by-default; no automatic remote fallback from a local task unless project policy explicitly permits it.
  status: accepted
  required_adr: null
- id: CAP-07-D15
  title: Canonical schema
  candidates:
  - JSON Schema Draft 2020-12 with versioned domain schemas; provider subsets compiled at adapter boundary.
  - Provider-specific schema dialect as canonical.
  recommendation: JSON Schema Draft 2020-12 with versioned domain schemas; provider subsets compiled at adapter boundary.
  recommendation_basis: The common standard supports local validation and portable contracts.
  selected_option: JSON Schema Draft 2020-12 with versioned domain schemas; provider subsets compiled at adapter boundary.
  status: accepted
  required_adr: null
- id: CAP-07-D16
  title: Validation pipeline
  candidates:
  - Provider constraint -> parse -> canonical schema validation -> semantic invariants -> evidence/anchor validation -> accepted or typed failure.
  - Accept syntactically valid JSON.
  recommendation: Provider constraint -> parse -> canonical schema validation -> semantic invariants -> evidence/anchor validation -> accepted or typed failure.
  recommendation_basis: Scholarly records require domain and provenance invariants beyond syntax.
  selected_option: Provider constraint -> parse -> canonical schema validation -> semantic invariants -> evidence/anchor validation -> accepted or typed failure.
  status: accepted
  required_adr: null
- id: CAP-07-D17
  title: Repair policy
  candidates:
  - At most bounded deterministic normalization plus one or configured model repair attempt; never invent missing required evidence.
  - Repeatedly reprompt until something validates.
  recommendation: At most bounded deterministic normalization plus one or configured model repair attempt; never invent missing required evidence.
  recommendation_basis: Bounded repair controls cost and avoids laundering unsupported output into valid shape.
  selected_option: At most bounded deterministic normalization plus one or configured model repair attempt; never invent missing required evidence.
  status: accepted
  required_adr: null
- id: CAP-07-D18
  title: Telemetry/content boundary
  candidates:
  - Operational spans store hashes, sizes, task/model/version, timing, usage and validation status; raw content only in project-governed artifacts when explicitly required.
  - Full prompt/response logging in telemetry.
  recommendation: Operational spans store hashes, sizes, task/model/version, timing, usage and validation status; raw content only in project-governed artifacts when explicitly required.
  recommendation_basis: Diagnostics must remain useful without leaking private research.
  selected_option: Operational spans store hashes, sizes, task/model/version, timing, usage and validation status; raw content only in project-governed artifacts when explicitly required.
  status: accepted
  required_adr: null
- id: CAP-07-D19
  title: Cache
  candidates:
  - Cache only deterministic/idempotent tasks by full manifest hash and data policy; never reuse across projects unless content-free/public and explicitly approved.
  - Global semantic prompt cache.
  recommendation: Cache only deterministic/idempotent tasks by full manifest hash and data policy; never reuse across projects unless content-free/public and explicitly approved.
  recommendation_basis: Cross-project reuse risks confidentiality and false equivalence.
  selected_option: Cache only deterministic/idempotent tasks by full manifest hash and data policy; never reuse across projects unless content-free/public and explicitly approved.
  status: accepted
  required_adr: null
- id: CAP-07-D20
  title: Evaluation gate
  candidates:
  - Task-specific gold/held-out sets with objective checks, expert sampling, calibration and cost/latency; promotion requires non-regression thresholds and approval.
  - One aggregate quality score or vendor benchmark.
  recommendation: Task-specific gold/held-out sets with objective checks, expert sampling, calibration and cost/latency; promotion requires non-regression thresholds and approval.
  recommendation_basis: Scholarly tasks fail differently and need direct citation/evidence/schema evaluation.
  selected_option: Task-specific gold/held-out sets with objective checks, expert sampling, calibration and cost/latency; promotion requires non-regression thresholds and approval.
  status: accepted
  required_adr: null
approval:
  status: pending
  approved_by: null
  approved_at: null
  approved_commit: null
---
# CAP-07 — Capability decision and execution plan

> **Capability approval gate — proposed, recommendations resolved.** The planning agent has researched the credible alternatives and preselected the documented best-in-class recommendation for every material decision. Those choices are complete decisions. Reviewers may confirm the defaults or override a choice with explicit rationale; one approval then authorizes this packet and all contained slice plans at an immutable commit. No separate decision-selection stop is required.

<div class="visual-flow"><span>Review all slices</span><b>→</b><span>Confirm or override resolved defaults</span><b>→</b><span>Approve once</span><b>→</b><span>Run long capability campaign</span><b>→</b><span>Production readiness review</span></div>

## 0. Control and authority

| Field | Value |
|---|---|
| Capability | `CAP-07` — Provider-neutral model gateway and governed AI execution |
| Objective | Make embeddings, rerankers, NLI models, extractors, and LLMs replaceable, policy-controlled, reproducible, and usable locally or through approved providers. |
| Execution mode | Capability campaign; slices complete in dependency order |
| Decision status | `COMPLETE` — best-in-class recommendations preselected and accepted; capability approval pending |
| Slice plans | `CAP-07.S01`, `CAP-07.S02`, `CAP-07.S03`, `CAP-07.S04`, `CAP-07.S05` |
| Approved UI reference | `RO-UI-ACADEMIC-MINIMAL-1.3` for all listed user-facing pages |
| Default interruption policy | Continue without routine stops; only classified infeasibility/external/hardware/human/design gates may pause |

## 1. Capability outcome and production-ready exit

The campaign must deliver: **Make embeddings, rerankers, NLI models, extractors, and LLMs replaceable, policy-controlled, reproducible, and usable locally or through approved providers.**

Production-ready exit criteria:

- All model calls pass through typed task contracts and produce versioned, observable result envelopes.
- Local inference supports the complete basic PC/lab workflow; remote egress is optional and explicitly authorized.
- Prompts, schemas, repair, evaluation, costs, and model upgrades are controlled as durable system assets.

Completion also requires all slices and tasks independently approved, capability-wide end-to-end evidence, failure/denial/cancel/restart/recovery/security/accessibility/platform coverage, accepted handoffs and no concealed production blockers.

## 2. Slice map and end-to-end dependency logic

| Slice | Responsibility | Production outcome | Upstream dependencies |
|---|---|---|---|
| `CAP-07.S01` | Model task, provider, and routing contracts | AI capabilities are invoked by scholarly task type rather than hard-coded vendor API. | `CAP-03.S01.T03`, `CAP-00.S03.T03` |
| `CAP-07.S02` | Local model runtime and model management | PC/lab users can run supported models through llama.cpp-class runtimes without manually administering a model server. | `CAP-07.S01.T03`, `CAP-01.S03.T03` |
| `CAP-07.S03` | Approved remote model providers | Remote inference is available through explicit opt-in adapters with redaction, data-class, and reproducibility controls. | `CAP-07.S01.T03`, `CAP-02.S04.T01` |
| `CAP-07.S04` | Prompt, schema, and structured-output registry | AI behavior is reproducible and testable as versioned configuration rather than hidden prompt strings. | `CAP-07.S01.T01`, `CAP-00.S05.T02` |
| `CAP-07.S05` | AI observability, budgets, and evaluation operations | Model use is measurable by scholarly task, project, provider, quality, latency, and cost without exposing research content. | `CAP-07.S04.T03`, `CAP-03.S03.T03` |

The planning reviewer must test the complete vertical: inputs from previous capabilities, each slice handoff, researcher workflow, durable/provenance behavior, degraded/recovery path and downstream contract. Slice-level optimization may not break the capability-wide path.

## 3. Decision-making protocol

1. Read every slice plan, backlog task, architecture boundary, workflow/page contract and relevant benchmark/source.
2. For each material choice, compare credible candidates using functionality, security, privacy/rights, portability, maintainability, licensing, local resource use, recovery, evaluation quality and downstream compatibility.
3. Present the leading candidates and an explicit recommendation. Avoid asking an open-ended question when evidence supports a best direction.
4. Record the accepted selection, rejected alternatives, evidence and replaceability/migration boundary in this packet and any required ADR.
5. Validate that the selected set is internally compatible and can complete all slices end to end.
6. Resolve all reasonably foreseeable decisions before campaign start. Implementation should not repeatedly interrupt the human for ordinary engineering choices.

## 4. Decision register

| ID | Decision | Recommended selection | Credible alternative | Why recommended / replacement boundary | Basis |
|---|---|---|---|---|---|
| `CAP-07-D01` | **Gateway domain boundary** | Provider-neutral task/result envelopes and model manifests owned by the core; provider SDK types remain inside adapters | Expose one provider SDK directly to application modules | Stable task contracts let local, university and cloud deployments change models without rewriting scholarly workflows. | [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12) |
| `CAP-07-D02` | **Local generative runtime** | Supervised llama.cpp sidecar with pinned GGUF model manifests; ONNX Runtime for suitable encoders/classifiers | Embed a single Python transformers runtime for every model class; require Docker locally | The split uses cross-platform runtimes according to model workload while preserving offline desktop operation. | [llama.cpp](https://github.com/ggml-org/llama.cpp) |
| `CAP-07-D03` | **Structured output authority** | JSON Schema post-validation is authoritative; provider grammar/tool constraints are optimization only | Trust provider “structured output” success without local validation | Provider constraints can differ or fail open; deterministic local validation and repair/retry policy must fail closed. | [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12) |
| `CAP-07-D04` | **Remote provider release baseline** | Two adapters selected by capability/privacy/cost evidence, with OpenAI- and Anthropic-compatible contracts first and Gemini-ready port | Build separate workflow logic for each provider | Two adapters prove portability; later providers enter through the same gateway and egress policy. | [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs) |
| `CAP-07-D05` | **AI telemetry** | OpenTelemetry GenAI conventions with content redaction by default and separate durable scholarly provenance | Store complete prompts and outputs in ordinary logs | Operational observability must not leak confidential research content and is distinct from auditable project evidence. | [OpenTelemetry Generative AI Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/) |
| `CAP-07-D06` | **Task taxonomy** | Use explicit task kinds—generation, structured extraction, embedding, reranking, classification/NLI, moderation and tool call—with task-specific input/result envelopes. | One generic chat-completions DTO. | Different tasks have different determinism, batching, evidence and failure semantics; a chat envelope would leak provider assumptions. | [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12) |
| `CAP-07-D07` | **Capability matching** | Route on declared task capabilities, data policy, context limits, structured-output support, deployment, evaluation status and resource/cost envelope. | Route by model name string from each feature. | A policy decision belongs in one auditable gateway and can be evaluated centrally. | [OpenTelemetry Generative AI Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/) |
| `CAP-07-D08` | **Fallback** | Ordered policy with deadline budget, retry classification and explicit degraded result; no silent provider/model substitution for pinned reproducible runs. | Retry every error indefinitely or silently switch models. | Fallback improves availability only when the scholarly meaning and disclosure remain clear. | [OpenTelemetry Generative AI Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/) |
| `CAP-07-D09` | **Runtime split** | llama.cpp/GGUF for local generative LLMs; ONNX Runtime or evaluated native library for encoders/rerankers/classifiers; both supervised as replaceable sidecars/workers. | One monolithic Python transformers service for every workload. | The split improves cross-platform packaging and resource efficiency while the gateway hides runtime details. | [llama.cpp](https://github.com/ggml-org/llama.cpp) |
| `CAP-07-D10` | **Artifact acceptance** | Pinned revision, cryptographic hash, license/use metadata, architecture, tokenizer and runtime compatibility required before activation. | Download latest by mutable model name. | Reproducibility, security and legal use require immutable artifacts and explicit consent. | [Safetensors Documentation](https://huggingface.co/docs/safetensors/index) |
| `CAP-07-D11` | **Hardware profiles** | Detect CPU/RAM/GPU/VRAM/driver and choose conservative approved profiles with user override; no automatic remote fallback. | Optimistically allocate all GPU/RAM. | Research desktops and DGX-class lab machines vary widely; adaptive limits prevent instability. | [ONNX Runtime Execution Providers](https://onnxruntime.ai/docs/execution-providers/) |
| `CAP-07-D12` | **Initial adapters** | Implement OpenAI-compatible and Anthropic Messages/tool-use adapters first; retain a Gemini adapter contract and add only after conformance/evaluation. | Implement every provider at once. | Two materially different APIs validate the gateway without diluting security and evaluation work. | [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs) |
| `CAP-07-D13` | **Egress unit** | Resolve and display the exact minimized payload after prompt assembly, including attachments, before first use or policy-sensitive changes. | Consent to “AI usage” generically. | Researchers need concrete control over confidential literature, reports and manuscripts. | [Tool Use with Claude](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview) |
| `CAP-07-D14` | **Offline enforcement** | Central network policy plus adapter deny-by-default; no automatic remote fallback from a local task unless project policy explicitly permits it. | Let connection failure determine offline behavior. | Offline/privacy intent must be enforced before network activity. | [OpenTelemetry Generative AI Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/) |
| `CAP-07-D15` | **Canonical schema** | JSON Schema Draft 2020-12 with versioned domain schemas; provider subsets compiled at adapter boundary. | Provider-specific schema dialect as canonical. | The common standard supports local validation and portable contracts. | [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12) |
| `CAP-07-D16` | **Validation pipeline** | Provider constraint -> parse -> canonical schema validation -> semantic invariants -> evidence/anchor validation -> accepted or typed failure. | Accept syntactically valid JSON. | Scholarly records require domain and provenance invariants beyond syntax. | [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs) |
| `CAP-07-D17` | **Repair policy** | At most bounded deterministic normalization plus one or configured model repair attempt; never invent missing required evidence. | Repeatedly reprompt until something validates. | Bounded repair controls cost and avoids laundering unsupported output into valid shape. | [Structured Outputs](https://ai.google.dev/gemini-api/docs/structured-output) |
| `CAP-07-D18` | **Telemetry/content boundary** | Operational spans store hashes, sizes, task/model/version, timing, usage and validation status; raw content only in project-governed artifacts when explicitly required. | Full prompt/response logging in telemetry. | Diagnostics must remain useful without leaking private research. | [OpenTelemetry Generative AI Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/) |
| `CAP-07-D19` | **Cache** | Cache only deterministic/idempotent tasks by full manifest hash and data policy; never reuse across projects unless content-free/public and explicitly approved. | Global semantic prompt cache. | Cross-project reuse risks confidentiality and false equivalence. | [OpenTelemetry Generative AI Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/) |
| `CAP-07-D20` | **Evaluation gate** | Task-specific gold/held-out sets with objective checks, expert sampling, calibration and cost/latency; promotion requires non-regression thresholds and approval. | One aggregate quality score or vendor benchmark. | Scholarly tasks fail differently and need direct citation/evidence/schema evaluation. | [Synthesizing Scientific Literature with Retrieval-Augmented Language Models](https://doi.org/10.1038/s41586-025-10072-4) |

### Review and approval

The best-in-class recommendation in every row is already the selected, accepted decision. Reviewers may confirm the complete set without editing individual choices, or replace a recommendation with another documented candidate and record an explicit rationale. The only remaining routine human gate is approval of this capability packet and all slice plans at one immutable commit.


## 5. Cross-slice architecture contract

- Preserve the authority order: canonical relational/provenance records and human decisions first; indexes, caches, graph projections, model outputs, rankings and generated artifacts remain versioned derivatives unless the Systems Design explicitly states otherwise.
- Stable ports isolate platform, storage, source, parser, model/provider, vector, graph, renderer and deployment adapters.
- Every durable output records source snapshot, schema/policy/model/tool versions, rights/privacy decisions, human decisions and dependency links.
- All long-running jobs are durable, idempotent where appropriate, cancellable, checkpointed, restartable and independently reviewable.
- The campaign remains local/Windows-first for the current waves while producing portable contracts and fixtures needed by CAP-14 macOS/Linux qualification.
- No later capability is implemented early except its documented interface/fixture seam.

## 6. Experience and workflow contract

Relevant approved pages: `model-center.html`, `audit-lineage.html`, `project-settings.html`

- The project use case determines the primary ordered workflow. Each page shows current stage, prior/next stage, expected output and completion/checkpoint state.
- All tools remain accessible as supporting tools with a clear route back to the primary workflow.
- Intentional changes require the style guide/workflow/page prototype to be updated, validated and human-approved before implementation.
- Accessibility, light/dark parity, offline/partial/error/recovery states and source/provenance inspection are capability exit requirements, not post-release polish.

## 7. Security, privacy, rights and research-integrity decisions

The reviewer must confirm the entire capability’s trust boundaries, data classes, authorization roles, secret/egress rules, rights/license handling, untrusted-content controls, logging/redaction, export behavior, model licenses and human scholarly authority. Where one slice’s output changes another slice’s rights or confidentiality exposure, the stricter policy travels with the object.

## 8. Capability-wide verification strategy

- **Contract:** all portable schemas, negative fixtures and adapter conformance.
- **Integration:** real local components, deterministic provider/source/model fixtures, transaction/outbox/dependency behavior.
- **End to end:** representative workflow across every slice with source inspection and human decision.
- **Recovery:** cancellation, process/application restart, corrupted derivative, migration, rollback/repair and project relocation.
- **Security/rights:** denial, malicious content, prompt injection, path/archive abuse, egress and export filters, redacted diagnostics.
- **Quality/evaluation:** capability-specific gold sets, ablations, calibration/error analysis and independent human samples.
- **Experience:** approved reference, adaptive navigation, keyboard/screen reader/zoom/reflow and light/dark visual checks.
- **Performance:** reference hardware/corpus budgets plus 20% regression threshold.
- **Independent review:** tests must demonstrate semantics, not merely execute code.

## 9. Long-running execution contract

Once approved and started, the agent should execute the whole capability slice by slice. It may make ordinary low-risk implementation choices within the accepted architecture, debug tests, refactor within module boundaries, select documented fallbacks and rerun evaluations without asking for confirmation. Progress is recorded through task/slice evidence and periodic concise updates rather than approval stops.

### Allowed pause classifications

- A model license is incompatible with distribution or intended use.
- An egress policy decision is unresolved for confidential data.
- A provider contract cannot be normalized without leaking provider-specific semantics.
- A model upgrade fails the approved evaluation gate.
- A governed UI/design change that requires a new approved reference.

Every pause records category, evidence, exact blocked task/slice, attempted alternatives, recommended next action and conditions for resume. Test failures and routine uncertainty are not pause reasons.

## 10. Plan and approval checklist

- [ ] All slice plans exist and pass `slice_plan_check.py` structurally.
- [ ] Every material decision has credible candidates, recommendation and accepted status.
- [ ] Required ADRs and design-reference changes are approved.
- [ ] Capability-wide architecture and end-to-end path are coherent.
- [ ] Fixtures, benchmarks, credentials/licenses, hardware and human authorities are available or approved stubs exist.
- [ ] Security/privacy/rights/research-integrity review is complete.
- [ ] All slice plans are approved at immutable commits.
- [ ] `python tools/planctl.py ready CAP-07 --require-approved` passes.
- [ ] The first dependency-ready task can start and the campaign can continue without routine decision stops.

## 11. Research and technical basis

- [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12) — Canonical structured-output and schema-pack validation.
- [llama.cpp](https://github.com/ggml-org/llama.cpp) — Cross-platform local generative inference, embeddings, reranking, grammar constraints and OpenAI-compatible service.
- [ONNX Runtime Execution Providers](https://onnxruntime.ai/docs/execution-providers/) — Portable CPU/CUDA/DirectML/CoreML inference for embedding, reranking and classification models.
- [OpenTelemetry Generative AI Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/) — Portable redacted telemetry for model requests, responses, usage and agents.

## 12. Approval record

The packet remains **proposed**. Approval requires:

- `decision_completion: complete`;
- every front-matter decision `status: accepted`;
- `approval.status: approved`, named approver, timestamp and approved commit;
- approved slice plans and any required ADRs/reference versions;
- passing approval-mode plan validation.
