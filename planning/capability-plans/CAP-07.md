---
plan_schema_version: '1.1'
document_type: capability-decision-plan
baseline: '1.3'
supplemental_release: 1.3.4
capability_id: CAP-07
title: Provider-neutral model gateway and governed AI execution
status: proposed
execution_mode: wave-scoped-capability-increments
decision_completion: pending
open_blocking_decisions: []
slice_ids:
- CAP-07.S01
- CAP-07.S04
- CAP-07.S02
- CAP-07.S05
- CAP-07.S03
decisions:
- id: CAP-07-D01
  title: Gateway domain boundary
  candidates:
  - Provider-neutral task/result envelopes and model manifests owned by the core; provider SDK types remain inside adapters
  - Expose one provider SDK directly to application modules
  recommendation: Provider-neutral task/result envelopes and model manifests owned by the core; provider SDK types remain
    inside adapters
  recommendation_basis: Stable task contracts let local, university and cloud deployments change models without rewriting
    scholarly workflows.
  selected_option: Provider-neutral task/result envelopes and model manifests owned by the core; provider SDK types remain
    inside adapters
  status: accepted
  required_adr: null
  binding_waves:
  - W1
- id: CAP-07-D02
  title: Local generative runtime
  candidates:
  - Signed supervised no-network model-purpose native worker with llama.cpp generation and evaluated ONNX C CPU decoder/encoder
    adapters; tiny SmolLM2 GQA/KV driver compatibility must qualify, with no Python-wheel/custom-op-DLL assumption.
  - Signed supervised model-specific no-network native worker, llama.cpp generation and ONNX CPU encoder drivers, behind unchanged
    ADR21 envelopes.
  - Supervised llama.cpp sidecar with pinned GGUF model manifests; ONNX Runtime for suitable encoders/classifiers
  - Embed a single Python transformers runtime for every model class; require Docker locally
  recommendation: Signed supervised no-network model-purpose native worker with llama.cpp generation and evaluated ONNX C
    CPU decoder/encoder adapters; tiny SmolLM2 GQA/KV driver compatibility must qualify, with no Python-wheel/custom-op-DLL
    assumption.
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: Signed supervised no-network model-purpose native worker with llama.cpp generation and evaluated ONNX C
    CPU decoder/encoder adapters; tiny SmolLM2 GQA/KV driver compatibility must qualify, with no Python-wheel/custom-op-DLL
    assumption.
  status: accepted
  required_adr: null
  binding_waves:
  - W3
- id: CAP-07-D03
  title: Structured output authority
  candidates:
  - JSON Schema post-validation is authoritative; provider grammar/tool constraints are optimization only
  - Trust provider “structured output” success without local validation
  recommendation: JSON Schema post-validation is authoritative; provider grammar/tool constraints are optimization only
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: JSON Schema post-validation is authoritative; provider grammar/tool constraints are optimization only
  status: accepted
  required_adr: null
  binding_waves:
  - W3
- id: CAP-07-D04
  title: Remote provider release baseline
  candidates:
  - Two optional disabled-by-default OpenAI-compatible/Anthropic adapters qualified by safe protocol fixtures; live-provider
    qualification/activation only with real consent/rights/credentials/budget, not G3 mandatory.
  - Two adapters selected by capability/privacy/cost evidence, with OpenAI- and Anthropic-compatible contracts first and Gemini-ready
    port
  - Build separate workflow logic for each provider
  recommendation: Two optional disabled-by-default OpenAI-compatible/Anthropic adapters qualified by safe protocol fixtures;
    live-provider qualification/activation only with real consent/rights/credentials/budget, not G3 mandatory.
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: Two optional disabled-by-default OpenAI-compatible/Anthropic adapters qualified by safe protocol fixtures;
    live-provider qualification/activation only with real consent/rights/credentials/budget, not G3 mandatory.
  status: accepted
  required_adr: null
  binding_waves:
  - W3
- id: CAP-07-D05
  title: AI telemetry
  candidates:
  - OpenTelemetry GenAI conventions with content redaction by default and separate durable scholarly provenance
  - Store complete prompts and outputs in ordinary logs
  recommendation: OpenTelemetry GenAI conventions with content redaction by default and separate durable scholarly provenance
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: OpenTelemetry GenAI conventions with content redaction by default and separate durable scholarly provenance
  status: accepted
  required_adr: null
  binding_waves:
  - W3
- id: CAP-07-D06
  title: Task taxonomy
  candidates:
  - Use explicit task kinds—generation, structured extraction, embedding, reranking, classification/NLI, moderation and tool
    call—with task-specific input/result envelopes.
  - One generic chat-completions DTO.
  recommendation: Use explicit task kinds—generation, structured extraction, embedding, reranking, classification/NLI, moderation
    and tool call—with task-specific input/result envelopes.
  recommendation_basis: Different tasks have different determinism, batching, evidence and failure semantics; a chat envelope
    would leak provider assumptions.
  selected_option: Use explicit task kinds—generation, structured extraction, embedding, reranking, classification/NLI, moderation
    and tool call—with task-specific input/result envelopes.
  status: accepted
  required_adr: null
  binding_waves:
  - W1
- id: CAP-07-D07
  title: Capability matching
  candidates:
  - Route on declared task capabilities, data policy, context limits, structured-output support, deployment, evaluation status
    and resource/cost envelope.
  - Route by model name string from each feature.
  recommendation: Route on declared task capabilities, data policy, context limits, structured-output support, deployment,
    evaluation status and resource/cost envelope.
  recommendation_basis: A policy decision belongs in one auditable gateway and can be evaluated centrally.
  selected_option: Route on declared task capabilities, data policy, context limits, structured-output support, deployment,
    evaluation status and resource/cost envelope.
  status: accepted
  required_adr: null
  binding_waves:
  - W1
- id: CAP-07-D08
  title: Fallback
  candidates:
  - Ordered policy with deadline budget, retry classification and explicit degraded result; no silent provider/model substitution
    for pinned reproducible runs.
  - Retry every error indefinitely or silently switch models.
  recommendation: Ordered policy with deadline budget, retry classification and explicit degraded result; no silent provider/model
    substitution for pinned reproducible runs.
  recommendation_basis: Fallback improves availability only when the scholarly meaning and disclosure remain clear.
  selected_option: Ordered policy with deadline budget, retry classification and explicit degraded result; no silent provider/model
    substitution for pinned reproducible runs.
  status: accepted
  required_adr: null
  binding_waves:
  - W1
- id: CAP-07-D09
  title: Runtime split
  candidates:
  - Signed supervised no-network model-purpose native worker with llama.cpp generation and evaluated ONNX C CPU decoder/encoder
    adapters; tiny SmolLM2 GQA/KV driver compatibility must qualify, with no Python-wheel/custom-op-DLL assumption.
  - llama.cpp native library and ONNX C API CPU drivers in model-purpose isolated workers; no assumption of Python3.14 ML
    wheel availability, arbitrary custom code or model HTTP network authority.
  - llama.cpp/GGUF for local generative LLMs; ONNX Runtime or evaluated native library for encoders/rerankers/classifiers;
    both supervised as replaceable sidecars/workers.
  - One monolithic Python transformers service for every workload.
  recommendation: Signed supervised no-network model-purpose native worker with llama.cpp generation and evaluated ONNX C
    CPU decoder/encoder adapters; tiny SmolLM2 GQA/KV driver compatibility must qualify, with no Python-wheel/custom-op-DLL
    assumption.
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: Signed supervised no-network model-purpose native worker with llama.cpp generation and evaluated ONNX C
    CPU decoder/encoder adapters; tiny SmolLM2 GQA/KV driver compatibility must qualify, with no Python-wheel/custom-op-DLL
    assumption.
  status: accepted
  required_adr: ADR-0056
  binding_waves:
  - W3
- id: CAP-07-D10
  title: Artifact acceptance
  candidates:
  - Pinned revision, cryptographic hash, license/use metadata, architecture, tokenizer and runtime compatibility required
    before activation.
  - Download latest by mutable model name.
  recommendation: Pinned revision, cryptographic hash, license/use metadata, architecture, tokenizer and runtime compatibility
    required before activation.
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: Pinned revision, cryptographic hash, license/use metadata, architecture, tokenizer and runtime compatibility
    required before activation.
  status: accepted
  required_adr: null
  binding_waves:
  - W3
- id: CAP-07-D11
  title: Hardware profiles
  candidates:
  - 'Per-role tiny/small qualified tiers inside TOTAL application2GiB preferred/3GiB upper, one model job, modest incremental
    availability/commit-pressure reserve; Job enforces private commit only, not RSS/mapped-page cap. Exact profiles and permitted
    auto-best-fit in aggregate-resource-and-selection-policy-02.json; all measurements pending. Explicit installed qualified
    auto-smallest/auto-best-fit allowed; pinned routes remain exact. Apply exact parserModelAdmission03 through existing LocalWorkerAdmission/LocalAdmissionController
    shared by project supervisors under one Core authority: reserve the whole demand before claim, serialize expensive protected
    parsing and local inference, retain live reservations through cancellation/crash/unknown cleanup until actual owned drain
    and model unload, then reobserve pressure/rights and reauthorize the newcomer. Unknown/insufficient growth or remaining2048MiB
    preferred/explicit3072MiB aggregate max(A,B) queues/denies; retain interactive/incremental reserves. Preserve parser principal,
    quality, cancellation/recovery, parser-only logon-session mutex and4096MiB private-commit ceiling; that ceiling is not
    measured consumption, a4GiB RAM requirement, proof of fit or a silently reduced limit. This cooperative ledger is not
    machine-wide enforcement; no new scheduler or concurrency promise.'
  - Explicit per-role user model/profile selection, serial whole-process memory/headroom admission, CPU-only default and hard
    caps; no automatic remote fallback or unsafe override.
  - Detect CPU/RAM/GPU/VRAM/driver and choose conservative approved profiles with user override; no automatic remote fallback.
  - Optimistically allocate all GPU/RAM.
  recommendation: 'Per-role tiny/small qualified tiers inside TOTAL application2GiB preferred/3GiB upper, one model job, modest
    incremental availability/commit-pressure reserve; Job enforces private commit only, not RSS/mapped-page cap. Exact profiles
    and permitted auto-best-fit in aggregate-resource-and-selection-policy-02.json; all measurements pending. Explicit installed
    qualified auto-smallest/auto-best-fit allowed; pinned routes remain exact. Apply exact parserModelAdmission03 through
    existing LocalWorkerAdmission/LocalAdmissionController shared by project supervisors under one Core authority: reserve
    the whole demand before claim, serialize expensive protected parsing and local inference, retain live reservations through
    cancellation/crash/unknown cleanup until actual owned drain and model unload, then reobserve pressure/rights and reauthorize
    the newcomer. Unknown/insufficient growth or remaining2048MiB preferred/explicit3072MiB aggregate max(A,B) queues/denies;
    retain interactive/incremental reserves. Preserve parser principal, quality, cancellation/recovery, parser-only logon-session
    mutex and4096MiB private-commit ceiling; that ceiling is not measured consumption, a4GiB RAM requirement, proof of fit
    or a silently reduced limit. This cooperative ledger is not machine-wide enforcement; no new scheduler or concurrency
    promise.'
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: 'Per-role tiny/small qualified tiers inside TOTAL application2GiB preferred/3GiB upper, one model job,
    modest incremental availability/commit-pressure reserve; Job enforces private commit only, not RSS/mapped-page cap. Exact
    profiles and permitted auto-best-fit in aggregate-resource-and-selection-policy-02.json; all measurements pending. Explicit
    installed qualified auto-smallest/auto-best-fit allowed; pinned routes remain exact. Apply exact parserModelAdmission03
    through existing LocalWorkerAdmission/LocalAdmissionController shared by project supervisors under one Core authority:
    reserve the whole demand before claim, serialize expensive protected parsing and local inference, retain live reservations
    through cancellation/crash/unknown cleanup until actual owned drain and model unload, then reobserve pressure/rights and
    reauthorize the newcomer. Unknown/insufficient growth or remaining2048MiB preferred/explicit3072MiB aggregate max(A,B)
    queues/denies; retain interactive/incremental reserves. Preserve parser principal, quality, cancellation/recovery, parser-only
    logon-session mutex and4096MiB private-commit ceiling; that ceiling is not measured consumption, a4GiB RAM requirement,
    proof of fit or a silently reduced limit. This cooperative ledger is not machine-wide enforcement; no new scheduler or
    concurrency promise.'
  status: accepted
  required_adr: ADR-0056
  binding_waves:
  - W3
- id: CAP-07-D12
  title: Initial adapters
  candidates:
  - OpenAI-compatible and Anthropic protocol adapters, recorded transport tests and optional separately qualified live activation;
    no Gemini implementation or implicit account/spend.
  - Implement OpenAI-compatible and Anthropic Messages/tool-use adapters first; retain a Gemini adapter contract and add only
    after conformance/evaluation.
  - Implement every provider at once.
  recommendation: OpenAI-compatible and Anthropic protocol adapters, recorded transport tests and optional separately qualified
    live activation; no Gemini implementation or implicit account/spend.
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: OpenAI-compatible and Anthropic protocol adapters, recorded transport tests and optional separately qualified
    live activation; no Gemini implementation or implicit account/spend.
  status: accepted
  required_adr: null
  binding_waves:
  - W3
- id: CAP-07-D13
  title: Egress unit
  candidates:
  - Resolve and display the exact minimized payload after prompt assembly, including attachments, before first use or policy-sensitive
    changes.
  - Consent to “AI usage” generically.
  recommendation: Resolve and display the exact minimized payload after prompt assembly, including attachments, before first
    use or policy-sensitive changes.
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: Resolve and display the exact minimized payload after prompt assembly, including attachments, before first
    use or policy-sensitive changes.
  status: accepted
  required_adr: null
  binding_waves:
  - W3
- id: CAP-07-D14
  title: Offline enforcement
  candidates:
  - Central network policy plus adapter deny-by-default; no automatic remote fallback from a local task unless project policy
    explicitly permits it.
  - Let connection failure determine offline behavior.
  recommendation: Central network policy plus adapter deny-by-default; no automatic remote fallback from a local task unless
    project policy explicitly permits it.
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: Central network policy plus adapter deny-by-default; no automatic remote fallback from a local task unless
    project policy explicitly permits it.
  status: accepted
  required_adr: null
  binding_waves:
  - W3
- id: CAP-07-D15
  title: Canonical schema
  candidates:
  - JSON Schema Draft 2020-12 with versioned domain schemas; provider subsets compiled at adapter boundary.
  - Provider-specific schema dialect as canonical.
  recommendation: JSON Schema Draft 2020-12 with versioned domain schemas; provider subsets compiled at adapter boundary.
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: JSON Schema Draft 2020-12 with versioned domain schemas; provider subsets compiled at adapter boundary.
  status: accepted
  required_adr: null
  binding_waves:
  - W3
- id: CAP-07-D16
  title: Validation pipeline
  candidates:
  - Provider constraint -> parse -> canonical schema validation -> semantic invariants -> evidence/anchor validation -> accepted
    or typed failure.
  - Accept syntactically valid JSON.
  recommendation: Provider constraint -> parse -> canonical schema validation -> semantic invariants -> evidence/anchor validation
    -> accepted or typed failure.
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: Provider constraint -> parse -> canonical schema validation -> semantic invariants -> evidence/anchor validation
    -> accepted or typed failure.
  status: accepted
  required_adr: null
  binding_waves:
  - W3
- id: CAP-07-D17
  title: Repair policy
  candidates:
  - Default zero model repair; configurable maximum one within the same reserved deadline/tokens/resource budget; no invented
    missing evidence.
  - At most bounded deterministic normalization plus one or configured model repair attempt; never invent missing required
    evidence.
  - Repeatedly reprompt until something validates.
  recommendation: Default zero model repair; configurable maximum one within the same reserved deadline/tokens/resource budget;
    no invented missing evidence.
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: Default zero model repair; configurable maximum one within the same reserved deadline/tokens/resource budget;
    no invented missing evidence.
  status: accepted
  required_adr: null
  binding_waves:
  - W3
- id: CAP-07-D18
  title: Telemetry/content boundary
  candidates:
  - Operational spans store hashes, sizes, task/model/version, timing, usage and validation status; raw content only in project-governed
    artifacts when explicitly required.
  - Full prompt/response logging in telemetry.
  recommendation: Operational spans store hashes, sizes, task/model/version, timing, usage and validation status; raw content
    only in project-governed artifacts when explicitly required.
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: Operational spans store hashes, sizes, task/model/version, timing, usage and validation status; raw content
    only in project-governed artifacts when explicitly required.
  status: accepted
  required_adr: null
  binding_waves:
  - W3
- id: CAP-07-D19
  title: Cache
  candidates:
  - Cache only deterministic/idempotent tasks by full manifest hash and data policy; never reuse across projects unless content-free/public
    and explicitly approved.
  - Global semantic prompt cache.
  recommendation: Cache only deterministic/idempotent tasks by full manifest hash and data policy; never reuse across projects
    unless content-free/public and explicitly approved.
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: Cache only deterministic/idempotent tasks by full manifest hash and data policy; never reuse across projects
    unless content-free/public and explicitly approved.
  status: accepted
  required_adr: null
  binding_waves:
  - W3
- id: CAP-07-D20
  title: Evaluation gate
  candidates:
  - 'Reuse concrete SciFact claim/evidence and QASPER answer/evidence annotations with exact release rights/splits and finite30-case
    human mapping bridge. No blanket120-document new annotation; task-specific quality/rights/unsupported-domain limits in
    gold-source-and-annotation-strategy-02.json. Existing role-domain targets remain proposed and actual results null. Apply
    the exact selected metricPolicy03 before any comparison: frozen eligible question/field and whole acceptable human references;
    NFC/newline/casefold tokenization \w+|[^\w\s], retained punctuation/multiplicity, multiset overlap, best F1 then precision
    then stable annotation order; answerable empty/abstention P=R=0; equal-field macro precision>=0.90 and recall>=0.80, with
    every consequential field failure visible. Verifier SUPPORTS/REFUTES macro precision>=0.90 plus each actionable-label
    recall>=0.80 and answered coverage>=0.80 over the complete frozen eligible frame; zero/undefined prediction denominator
    or missing required gold class cannot pass. NEI, ABSTAIN and technical failure remain distinct; publish exact Ns/confusion/coverage/uncertainty
    and retain all source/rights/human constraints.'
  - Rights-cleared dev/heldout role/domain gold with deterministic checks and actual human annotations; task-specific limits
    and no model-only approval; product stores attestation, never imports evaluation/.
  - Task-specific gold/held-out sets with objective checks, expert sampling, calibration and cost/latency; promotion requires
    non-regression thresholds and approval.
  - One aggregate quality score or vendor benchmark.
  recommendation: 'Reuse concrete SciFact claim/evidence and QASPER answer/evidence annotations with exact release rights/splits
    and finite30-case human mapping bridge. No blanket120-document new annotation; task-specific quality/rights/unsupported-domain
    limits in gold-source-and-annotation-strategy-02.json. Existing role-domain targets remain proposed and actual results
    null. Apply the exact selected metricPolicy03 before any comparison: frozen eligible question/field and whole acceptable
    human references; NFC/newline/casefold tokenization \w+|[^\w\s], retained punctuation/multiplicity, multiset overlap,
    best F1 then precision then stable annotation order; answerable empty/abstention P=R=0; equal-field macro precision>=0.90
    and recall>=0.80, with every consequential field failure visible. Verifier SUPPORTS/REFUTES macro precision>=0.90 plus
    each actionable-label recall>=0.80 and answered coverage>=0.80 over the complete frozen eligible frame; zero/undefined
    prediction denominator or missing required gold class cannot pass. NEI, ABSTAIN and technical failure remain distinct;
    publish exact Ns/confusion/coverage/uncertainty and retain all source/rights/human constraints.'
  recommendation_basis: 'Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json
    and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs.
    Preserve engine/provider ports and actual unmeasured limits.'
  selected_option: 'Reuse concrete SciFact claim/evidence and QASPER answer/evidence annotations with exact release rights/splits
    and finite30-case human mapping bridge. No blanket120-document new annotation; task-specific quality/rights/unsupported-domain
    limits in gold-source-and-annotation-strategy-02.json. Existing role-domain targets remain proposed and actual results
    null. Apply the exact selected metricPolicy03 before any comparison: frozen eligible question/field and whole acceptable
    human references; NFC/newline/casefold tokenization \w+|[^\w\s], retained punctuation/multiplicity, multiset overlap,
    best F1 then precision then stable annotation order; answerable empty/abstention P=R=0; equal-field macro precision>=0.90
    and recall>=0.80, with every consequential field failure visible. Verifier SUPPORTS/REFUTES macro precision>=0.90 plus
    each actionable-label recall>=0.80 and answered coverage>=0.80 over the complete frozen eligible frame; zero/undefined
    prediction denominator or missing required gold class cannot pass. NEI, ABSTAIN and technical failure remain distinct;
    publish exact Ns/confusion/coverage/uncertainty and retain all source/rights/human constraints.'
  status: accepted
  required_adr: ADR-0058
  binding_waves:
  - W3
approval:
  status: pending
  approved_by: null
  approved_at: null
  approved_commit: null
planning_policy_version: initiation-assessment-2.0
initiation_assessment:
  policy_version: '2.0'
  assessed_at: '2026-10-15T21:24:29.166422+00:00'
  estimation_unit: engineering-effort-hours
  implementation_baseline: 'Genuine905b assessment; deliberate current deny model policy, protected schema28/anchors/lifecycle
    and accepted ADR21/25/26 are reused. W2 exit pending.


    Canonical post-G2 reconciliation: Actual W2/G2 initial completion is recorded at1cc8131d8b74cf6c536d48ce4badc25933981bbb;
    the current planning predecessor and committed post-exit roadmap is2e2f1a9d042c3dd8db3f8f31b648a36ad004c505. See artifacts/evidence/W2.initial-exit-recording-receipt-20261016-01.json
    and the independent Wave/S06/CP10 records. Historical3541 product,1b377 build/reference/Native,fc694 full90 and ownerf86
    identities remain distinct. Initial1000 functional commit is qualified, but100k publication/fullmanifest/replay/reopen
    and continuous performance remain UNQUALIFIED; no1000 productcap or W3metadata/vector100k import-throughput inference.
    All failed/UNKNOWN/UNTESTED evidence, parser-only2.5333542s acceptance, source-search median7s/all24raws, strictClippyFAIL,409UNKNOWN,
    security expiry and platform/installer gaps remain. Owner933b moves optional cosmetics and optimization/performance intake
    to newW10; functional/security qualification residuals remain separately trackedW9, and larger-computing product workW5.
    Before W3 approval, suggested soft median timing overage strictly<7s may be accepted with W10 debt; completed comparable
    trials/allraws retained, failed/timeouts and hard functional/security/resource/cancellation bounds unchanged. Hosted university/cloud
    labels areW11/W12. All48IDs/16slices/924hours including28once, ordered proof ownership, policy03 metrics/token semantics
    and serial admission are retained. ADR0056–58/reference1.10 remain Proposed, active1.9 unchanged and W3approvalPENDING;
    no implementation is authorized.'
  vision_architecture_best_practice_fit: Local small configurable CPU model/resource tier, protected exact retrieval, human
    research authority, explicit optional egress; proposed material architecture/reference adoption still required.
  planned_items:
  - work_id: CAP-07.S04.T01
    effort: 12
  - work_id: CAP-07.S04.T02
    effort: 20
  - work_id: CAP-07.S04.T03
    effort: 16
  - work_id: CAP-07.S02.T01
    effort: 32
  - work_id: CAP-07.S02.T02
    effort: 24
  - work_id: CAP-07.S02.T03
    effort: 22
  - work_id: CAP-07.S05.T01
    effort: 12
  - work_id: CAP-07.S05.T02
    effort: 20
  - work_id: CAP-07.S05.T03
    effort: 22
  - work_id: CAP-07.S03.T01
    effort: 20
  - work_id: CAP-07.S03.T02
    effort: 24
  - work_id: CAP-07.S03.T03
    effort: 16
  refactoring_items:
  - work_id: CAP-07.S02.T01
    effort: 8
    reason: Bounded extension of current shared policy/projection/evidence/reader authority included within this task, not
      an additional task or double-counted estimate.
    id: CAP-07.S02.T01
    introduced_in_wave: W3
    changes_existing_implementation: true
    major_refactor: false
    disposition: included
    description: "Bounded extension of current shared policy/projection/evidence/reader authority included within this task, not an additional task or double-counted estimate."
  - work_id: CAP-07.S05.T02
    effort: 4
    reason: Bounded extension of current shared policy/projection/evidence/reader authority included within this task, not
      an additional task or double-counted estimate.
    id: CAP-07.S05.T02
    introduced_in_wave: W3
    changes_existing_implementation: true
    major_refactor: false
    disposition: included
    description: "Bounded extension of current shared policy/projection/evidence/reader authority included within this task, not an additional task or double-counted estimate."
  major_refactor_disposition: No blanket replacement of approved W1/W2 contracts. The new model-purpose worker/protected projection
    decisions are planned W3 architecture with acceptance required before approval; inherited decisions remain unchanged.
  wave_refreshes:
  - wave: W3
    assessed_at: '2026-10-16T11:23:10.387985+00:00'
    material_changes: 'Current W2 schema28/protected anchors, UI1.9 and deliberate no-model permission baseline replace stale
      paths/assumptions.


      Canonical post-G2 reconciliation: Actual W2/G2 initial completion is recorded at1cc8131d8b74cf6c536d48ce4badc25933981bbb;
      the current planning predecessor and committed post-exit roadmap is2e2f1a9d042c3dd8db3f8f31b648a36ad004c505. See artifacts/evidence/W2.initial-exit-recording-receipt-20261016-01.json
      and the independent Wave/S06/CP10 records. Historical3541 product,1b377 build/reference/Native,fc694 full90 and ownerf86
      identities remain distinct. Initial1000 functional commit is qualified, but100k publication/fullmanifest/replay/reopen
      and continuous performance remain UNQUALIFIED; no1000 productcap or W3metadata/vector100k import-throughput inference.
      All failed/UNKNOWN/UNTESTED evidence, parser-only2.5333542s acceptance, source-search median7s/all24raws, strictClippyFAIL,409UNKNOWN,
      security expiry and platform/installer gaps remain. Owner933b moves optional cosmetics and optimization/performance
      intake to newW10; functional/security qualification residuals remain separately trackedW9, and larger-computing product
      workW5. Before W3 approval, suggested soft median timing overage strictly<7s may be accepted with W10 debt; completed
      comparable trials/allraws retained, failed/timeouts and hard functional/security/resource/cancellation bounds unchanged.
      Hosted university/cloud labels areW11/W12. All48IDs/16slices/924hours including28once, ordered proof ownership, policy03
      metrics/token semantics and serial admission are retained. ADR0056–58/reference1.10 remain Proposed, active1.9 unchanged
      and W3approvalPENDING; no implementation is authorized.'
    plan_adaptations: All proposed choices are itemized in this private packet; no capability campaign, unsafe memory override,
      implicit egress or unprotected service index. Successor05 includes actual ordered-slice approval gates, executable slice
      order and retained staged registry/runtime/evaluation proof; no framework or policy weakening.
    support_improvements: Canonical rights/classification/budget and resource admission, protected rebuild, honest evaluation/identity
      states.
    major_refactor_disposition: Included in named atomic task estimates; no supplemental budget spent.
---

# CAP-07 — Provider-neutral model gateway and governed AI execution

PRIVATE PROPOSED W3 CONTRIBUTION. Approval, accepted status and execution remain pending. Original source: `planning/capability-plans/CAP-07.md` / `b95fdb594bd4bbe52f66cdedae7f5642e15b5f0b300fa17498ae7e551cd0e80f`. Preserve inherited W1 selections; recommended W3 values are resolved draft choices subject to one complete Wave review, not existing approvals. `required_adr: null` here does not waive the three material architecture topics; unassigned historical ADR-CAP placeholders are replaced by the explicit topic register.

## 0. Control and authority

The Wave owns execution/integration/qualification and G3 handoff. Capability is an outcome map, not a lease. Immutable IDs and prior approvals stay unchanged; all proposed decisions are classified by Wave in front matter.

## 0A. Initiation assessment and planning adaptation

Reuse genuine905b source assessment and the baseline/source inventory. Full48 atomic estimates are in task-register-01.json; no slice+task double count. See contracts-01.md for baseline fit, exact resource/rights model and deferred work.

## 1. Capability outcome and production-ready exit

Make embeddings, rerankers, NLI models, extractors, and LLMs replaceable, policy-controlled, reproducible, and usable locally or through approved providers. W3 exit covers only these contributing slices, actual benchmark limits, real authority and human review, not unimplemented future capabilities.

## 2. Slice map and end-to-end dependency logic

- CAP-07.S04: Prompt, schema, and structured-output registry — Immutable prompt/tool/schema assets in product configuration use Draft2020-12 and bounded data-only validators. Provider grammar is an aid; canonical parsing, shape, semantics and anchors own acceptance.
- CAP-07.S02: Local model runtime and model management — A supervised signed native model worker hosts pinned llama.cpp generation or ONNX CPU encoders behind ADR21. Canonical purpose-specific rights, classification and budget authority precede any allow; model selection is explicit and per role.
- CAP-07.S05: AI observability, budgets, and evaluation operations — Content-free operational telemetry and durable scholarly call provenance are separate. Cumulative local/remote reservations, exact-policy cache keys and evaluation records control eligibility and visible upgrades.
- CAP-07.S03: Approved remote model providers — OpenAI-compatible and Anthropic transport adapters behind the gateway, optional and disabled by default. No account is required for the local G3 journey and no credentials, live calls or spend are assumed in the W3 plan.

This is the actual proposed capability.slices execution order, not numeric ID order. Every earlier slice needs genuine APPROVED completion before later tasks; exact external dependency unions apply to every task. See ordered-slice-feasibility-witness-05.json. Inherited/future slice objects and identities are unchanged.

## 3. Decision-making protocol

Every W3 decision has at least two candidates and a concrete recommended selection. The authored proposed plan selects the reviewed options using the existing capability-plan status `accepted`; this records plan-option completeness only. Proposed ADRs, the proposed reference1.10 and Wave approval remain pending and grant no implementation authority. Record independent review/any override rationale and material ADR/reference decisions in the ordinary single Wave packet.

## 4. Decision register

Selections below are the recorded proposed-plan choices; the capability/Wave approval remains PENDING. Inherited accepted authority retains its original scope. Full metadata and alternatives remain in the front matter.

| Decision | Alternatives | Recorded choice | Rationale | Required ADR |
|---|---|---|---|---|
| `CAP-07-D01` — Gateway domain boundary | Provider-neutral task/result envelopes and model manifests owned by the core; provider SDK types remain inside adapters<br>Expose one provider SDK directly to application modules | Provider-neutral task/result envelopes and model manifests owned by the core; provider SDK types remain inside adapters | Stable task contracts let local, university and cloud deployments change models without rewriting scholarly workflows. | None |
| `CAP-07-D02` — Local generative runtime | Signed supervised no-network model-purpose native worker with llama.cpp generation and evaluated ONNX C CPU decoder/encoder adapters; tiny SmolLM2 GQA/KV driver compatibility must qualify, with no Python-wheel/custom-op-DLL assumption.<br>Signed supervised model-specific no-network native worker, llama.cpp generation and ONNX CPU encoder drivers, behind unchanged ADR21 envelopes.<br>Supervised llama.cpp sidecar with pinned GGUF model manifests; ONNX Runtime for suitable encoders/classifiers<br>Embed a single Python transformers runtime for every model class; require Docker locally | Signed supervised no-network model-purpose native worker with llama.cpp generation and evaluated ONNX C CPU decoder/encoder adapters; tiny SmolLM2 GQA/KV driver compatibility must qualify, with no Python-wheel/custom-op-DLL assumption. | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | None |
| `CAP-07-D03` — Structured output authority | JSON Schema post-validation is authoritative; provider grammar/tool constraints are optimization only<br>Trust provider “structured output” success without local validation | JSON Schema post-validation is authoritative; provider grammar/tool constraints are optimization only | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | None |
| `CAP-07-D04` — Remote provider release baseline | Two optional disabled-by-default OpenAI-compatible/Anthropic adapters qualified by safe protocol fixtures; live-provider qualification/activation only with real consent/rights/credentials/budget, not G3 mandatory.<br>Two adapters selected by capability/privacy/cost evidence, with OpenAI- and Anthropic-compatible contracts first and Gemini-ready port<br>Build separate workflow logic for each provider | Two optional disabled-by-default OpenAI-compatible/Anthropic adapters qualified by safe protocol fixtures; live-provider qualification/activation only with real consent/rights/credentials/budget, not G3 mandatory. | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | None |
| `CAP-07-D05` — AI telemetry | OpenTelemetry GenAI conventions with content redaction by default and separate durable scholarly provenance<br>Store complete prompts and outputs in ordinary logs | OpenTelemetry GenAI conventions with content redaction by default and separate durable scholarly provenance | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | None |
| `CAP-07-D06` — Task taxonomy | Use explicit task kinds—generation, structured extraction, embedding, reranking, classification/NLI, moderation and tool call—with task-specific input/result envelopes.<br>One generic chat-completions DTO. | Use explicit task kinds—generation, structured extraction, embedding, reranking, classification/NLI, moderation and tool call—with task-specific input/result envelopes. | Different tasks have different determinism, batching, evidence and failure semantics; a chat envelope would leak provider assumptions. | None |
| `CAP-07-D07` — Capability matching | Route on declared task capabilities, data policy, context limits, structured-output support, deployment, evaluation status and resource/cost envelope.<br>Route by model name string from each feature. | Route on declared task capabilities, data policy, context limits, structured-output support, deployment, evaluation status and resource/cost envelope. | A policy decision belongs in one auditable gateway and can be evaluated centrally. | None |
| `CAP-07-D08` — Fallback | Ordered policy with deadline budget, retry classification and explicit degraded result; no silent provider/model substitution for pinned reproducible runs.<br>Retry every error indefinitely or silently switch models. | Ordered policy with deadline budget, retry classification and explicit degraded result; no silent provider/model substitution for pinned reproducible runs. | Fallback improves availability only when the scholarly meaning and disclosure remain clear. | None |
| `CAP-07-D09` — Runtime split | Signed supervised no-network model-purpose native worker with llama.cpp generation and evaluated ONNX C CPU decoder/encoder adapters; tiny SmolLM2 GQA/KV driver compatibility must qualify, with no Python-wheel/custom-op-DLL assumption.<br>llama.cpp native library and ONNX C API CPU drivers in model-purpose isolated workers; no assumption of Python3.14 ML wheel availability, arbitrary custom code or model HTTP network authority.<br>llama.cpp/GGUF for local generative LLMs; ONNX Runtime or evaluated native library for encoders/rerankers/classifiers; both supervised as replaceable sidecars/workers.<br>One monolithic Python transformers service for every workload. | Signed supervised no-network model-purpose native worker with llama.cpp generation and evaluated ONNX C CPU decoder/encoder adapters; tiny SmolLM2 GQA/KV driver compatibility must qualify, with no Python-wheel/custom-op-DLL assumption. | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | ADR-0056 |
| `CAP-07-D10` — Artifact acceptance | Pinned revision, cryptographic hash, license/use metadata, architecture, tokenizer and runtime compatibility required before activation.<br>Download latest by mutable model name. | Pinned revision, cryptographic hash, license/use metadata, architecture, tokenizer and runtime compatibility required before activation. | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | None |
| `CAP-07-D11` — Hardware profiles | Per-role tiny/small qualified tiers inside TOTAL application2GiB preferred/3GiB upper, one model job, modest incremental availability/commit-pressure reserve; Job enforces private commit only, not RSS/mapped-page cap. Exact profiles and permitted auto-best-fit in aggregate-resource-and-selection-policy-02.json; all measurements pending. Explicit installed qualified auto-smallest/auto-best-fit allowed; pinned routes remain exact. Apply exact parserModelAdmission03 through existing LocalWorkerAdmission/LocalAdmissionController shared by project supervisors under one Core authority: reserve the whole demand before claim, serialize expensive protected parsing and local inference, retain live reservations through cancellation/crash/unknown cleanup until actual owned drain and model unload, then reobserve pressure/rights and reauthorize the newcomer. Unknown/insufficient growth or remaining2048MiB preferred/explicit3072MiB aggregate max(A,B) queues/denies; retain interactive/incremental reserves. Preserve parser principal, quality, cancellation/recovery, parser-only logon-session mutex and4096MiB private-commit ceiling; that ceiling is not measured consumption, a4GiB RAM requirement, proof of fit or a silently reduced limit. This cooperative ledger is not machine-wide enforcement; no new scheduler or concurrency promise.<br>Explicit per-role user model/profile selection, serial whole-process memory/headroom admission, CPU-only default and hard caps; no automatic remote fallback or unsafe override.<br>Detect CPU/RAM/GPU/VRAM/driver and choose conservative approved profiles with user override; no automatic remote fallback.<br>Optimistically allocate all GPU/RAM. | Per-role tiny/small qualified tiers inside TOTAL application2GiB preferred/3GiB upper, one model job, modest incremental availability/commit-pressure reserve; Job enforces private commit only, not RSS/mapped-page cap. Exact profiles and permitted auto-best-fit in aggregate-resource-and-selection-policy-02.json; all measurements pending. Explicit installed qualified auto-smallest/auto-best-fit allowed; pinned routes remain exact. Apply exact parserModelAdmission03 through existing LocalWorkerAdmission/LocalAdmissionController shared by project supervisors under one Core authority: reserve the whole demand before claim, serialize expensive protected parsing and local inference, retain live reservations through cancellation/crash/unknown cleanup until actual owned drain and model unload, then reobserve pressure/rights and reauthorize the newcomer. Unknown/insufficient growth or remaining2048MiB preferred/explicit3072MiB aggregate max(A,B) queues/denies; retain interactive/incremental reserves. Preserve parser principal, quality, cancellation/recovery, parser-only logon-session mutex and4096MiB private-commit ceiling; that ceiling is not measured consumption, a4GiB RAM requirement, proof of fit or a silently reduced limit. This cooperative ledger is not machine-wide enforcement; no new scheduler or concurrency promise. | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | ADR-0056 |
| `CAP-07-D12` — Initial adapters | OpenAI-compatible and Anthropic protocol adapters, recorded transport tests and optional separately qualified live activation; no Gemini implementation or implicit account/spend.<br>Implement OpenAI-compatible and Anthropic Messages/tool-use adapters first; retain a Gemini adapter contract and add only after conformance/evaluation.<br>Implement every provider at once. | OpenAI-compatible and Anthropic protocol adapters, recorded transport tests and optional separately qualified live activation; no Gemini implementation or implicit account/spend. | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | None |
| `CAP-07-D13` — Egress unit | Resolve and display the exact minimized payload after prompt assembly, including attachments, before first use or policy-sensitive changes.<br>Consent to “AI usage” generically. | Resolve and display the exact minimized payload after prompt assembly, including attachments, before first use or policy-sensitive changes. | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | None |
| `CAP-07-D14` — Offline enforcement | Central network policy plus adapter deny-by-default; no automatic remote fallback from a local task unless project policy explicitly permits it.<br>Let connection failure determine offline behavior. | Central network policy plus adapter deny-by-default; no automatic remote fallback from a local task unless project policy explicitly permits it. | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | None |
| `CAP-07-D15` — Canonical schema | JSON Schema Draft 2020-12 with versioned domain schemas; provider subsets compiled at adapter boundary.<br>Provider-specific schema dialect as canonical. | JSON Schema Draft 2020-12 with versioned domain schemas; provider subsets compiled at adapter boundary. | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | None |
| `CAP-07-D16` — Validation pipeline | Provider constraint -> parse -> canonical schema validation -> semantic invariants -> evidence/anchor validation -> accepted or typed failure.<br>Accept syntactically valid JSON. | Provider constraint -> parse -> canonical schema validation -> semantic invariants -> evidence/anchor validation -> accepted or typed failure. | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | None |
| `CAP-07-D17` — Repair policy | Default zero model repair; configurable maximum one within the same reserved deadline/tokens/resource budget; no invented missing evidence.<br>At most bounded deterministic normalization plus one or configured model repair attempt; never invent missing required evidence.<br>Repeatedly reprompt until something validates. | Default zero model repair; configurable maximum one within the same reserved deadline/tokens/resource budget; no invented missing evidence. | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | None |
| `CAP-07-D18` — Telemetry/content boundary | Operational spans store hashes, sizes, task/model/version, timing, usage and validation status; raw content only in project-governed artifacts when explicitly required.<br>Full prompt/response logging in telemetry. | Operational spans store hashes, sizes, task/model/version, timing, usage and validation status; raw content only in project-governed artifacts when explicitly required. | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | None |
| `CAP-07-D19` — Cache | Cache only deterministic/idempotent tasks by full manifest hash and data policy; never reuse across projects unless content-free/public and explicitly approved.<br>Global semantic prompt cache. | Cache only deterministic/idempotent tasks by full manifest hash and data policy; never reuse across projects unless content-free/public and explicitly approved. | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | None |
| `CAP-07-D20` — Evaluation gate | Reuse concrete SciFact claim/evidence and QASPER answer/evidence annotations with exact release rights/splits and finite30-case human mapping bridge. No blanket120-document new annotation; task-specific quality/rights/unsupported-domain limits in gold-source-and-annotation-strategy-02.json. Existing role-domain targets remain proposed and actual results null. Apply the exact selected metricPolicy03 before any comparison: frozen eligible question/field and whole acceptable human references; NFC/newline/casefold tokenization \w+\|[^\w\s], retained punctuation/multiplicity, multiset overlap, best F1 then precision then stable annotation order; answerable empty/abstention P=R=0; equal-field macro precision>=0.90 and recall>=0.80, with every consequential field failure visible. Verifier SUPPORTS/REFUTES macro precision>=0.90 plus each actionable-label recall>=0.80 and answered coverage>=0.80 over the complete frozen eligible frame; zero/undefined prediction denominator or missing required gold class cannot pass. NEI, ABSTAIN and technical failure remain distinct; publish exact Ns/confusion/coverage/uncertainty and retain all source/rights/human constraints.<br>Rights-cleared dev/heldout role/domain gold with deterministic checks and actual human annotations; task-specific limits and no model-only approval; product stores attestation, never imports evaluation/.<br>Task-specific gold/held-out sets with objective checks, expert sampling, calibration and cost/latency; promotion requires non-regression thresholds and approval.<br>One aggregate quality score or vendor benchmark. | Reuse concrete SciFact claim/evidence and QASPER answer/evidence annotations with exact release rights/splits and finite30-case human mapping bridge. No blanket120-document new annotation; task-specific quality/rights/unsupported-domain limits in gold-source-and-annotation-strategy-02.json. Existing role-domain targets remain proposed and actual results null. Apply the exact selected metricPolicy03 before any comparison: frozen eligible question/field and whole acceptable human references; NFC/newline/casefold tokenization \w+\|[^\w\s], retained punctuation/multiplicity, multiset overlap, best F1 then precision then stable annotation order; answerable empty/abstention P=R=0; equal-field macro precision>=0.90 and recall>=0.80, with every consequential field failure visible. Verifier SUPPORTS/REFUTES macro precision>=0.90 plus each actionable-label recall>=0.80 and answered coverage>=0.80 over the complete frozen eligible frame; zero/undefined prediction denominator or missing required gold class cannot pass. NEI, ABSTAIN and technical failure remain distinct; publish exact Ns/confusion/coverage/uncertainty and retain all source/rights/human constraints. | Proposed W3 choice, not accepted authority: see contracts-01.md, architecture-decision-proposals-01.json and primary-evidence-01.json for functionality, protection/rights, portability, resource/recovery/evaluation tradeoffs. Preserve engine/provider ports and actual unmeasured limits. | ADR-0058 |

## 5. Cross-slice architecture contract

Use current Core/worker/generated ports and protected state; contracts-01.md owns content refs, policy before allow, no product->evaluation dependency, migrations and resources. Task DAG includes explicit runtime and canonical persistence prerequisites.

## 6. Experience and workflow contract

Base reference1.9 and semantic catalog1.5 are inherited, illustrative values are not measured/configuration authority. Proposed material additions in ux-reference-proposal-01.md need ordinary accepted reference publication before implementation.

## 7. Security, privacy, rights and research-integrity decisions

Purpose-specific source model-use/classification/budget, current Windows session/principal, encrypted derivative storage and no implicit egress/spend. Human interpretation/inclusion/verification/final claims; local coder limits are explicit.

## 8. Capability-wide verification strategy

Task selected checks, integrated real slice journey, then fresh full affected Wave qualification. Include rights revoke, cancellation/late output, resource OOM, crash/restart, stale inputs, backup-first migration, actual no-network/no-vault principal and accessibility. Gold methodology/targets and actual-evidence limits in shared contracts.

## 9. Long-running execution contract

After W2 exit/G2, canonicalize reviewed plan/reference/ADRs and obtain one immutable W3 approval; normal taskctl claims dependency-eligible READY tasks in the same campaign. Ordinary debugging adds no owner question; real scope/authority/release conflicts use existing routes.

## 10. Plan and approval checklist

16 slices/48 tasks, exact decision inventory and estimates/DAG; no unapproved future scope accepted by implication. Unresolved-decision-list-01.json names only actual remaining acceptance/factual dependencies, not invented implementation gates.

## 11. Research and technical basis

See primary-evidence-01.json and original/source inventory; model-card/runtime capability is not actual role quality or RAM guarantee. No runtime/model/benchmark execution in this proposal.

## 12. Approval record

Pending/null. The complete ordinary Wave approval later binds accepted decisions/reference/ADRs/peer slices/estimates at one immutable commit. No release or implementation authority is created by this private draft.


## Selected policy03 and complete proposal incorporation

The exact selected policy03 is incorporated in this private successor, not adopted or measured: root-selected-policy-refinement-03.json SHA2561c40fcbe2ed959479e74305986b4b2cc7efed18d2fa7895c0a148cf07dc76d81. The genuine prior review5ced assesses the selected choices only. This complete packet still requires independent incremental review and ordinary actual authority before one immutableW3 approval.

### Existing shared parser/model admission03

**findingId**: W3-PLANNING-RESOURCE-02

**choice**: Initially serialize expensive protected document parsing and new local model inference through the existing shared product resource authority, including across projects supervised by that Core authority.

**existingSeam**: services/core-api/src/research_observatory_core/workflow_executor.py: LocalWorkerAdmission and LocalAdmissionController registration/reservation before claim. Extend the existing product composition; do not create a second generic scheduler or import planning/evaluation controls into runtime.

**reservationRule**: Reserve the whole declared resource demand before claim/dispatch. An active expensive parser reservation excludes model inference and vice versa. Queue the newcomer until the prior owned work is drained and any model is unloaded; only then reobserve pressure, reauthorize and admit. Preserve manual/metadata responsiveness and the interactive reserve. Cancellation, crash and unknown cleanup cannot release a still-live reservation.

**capacityRule**: Retain preferred total application 2048MiB / explicitly selected upper 3072MiB, conservative max(A,B) accounting and incremental physical/commit checks. Unknown or insufficient current parser/model growth or remaining aggregate budget denies or queues the work; do not assume it fits because a process has started or model weights are small. Any later concurrent profile requires actual joint-profile evidence and the existing policy route.

**inheritedParser**: Preserve current parser principal, quality, cancellation, recovery, parser-only logon-session mutex and launcher/package/config 4096MiB private-commit ceiling. That ceiling is neither measured consumption nor a 4GiB RAM requirement and is not silently reduced or qualified by this W3 plan. The new aggregate admission decision may deny an unqualified workload without changing or falsely passing the old parser contract.

**authorityLimit**: The current in-process ledger does not enforce reservations against unrelated Core processes. Keep the real existing Native/project exclusivity and parser mutex boundaries, and qualify the actual claimed composition. Do not infer machine-wide enforcement from a Python lock or disable another process.

**appliesToTasks**: ["CAP-07.S02.T01", "CAP-07.S02.T03"]

**implementationAcceptance**: Prove actual parser/model contention queues or denies the newcomer, no overlapping expensive execution, normal drain/unload followed by fresh authorized re-admission, cancellation/crash/lock and no release of a live reservation. Bind actual aggregate/resource observations; no current model load or larger hardware test is requested by this planning selection.

**incorporationRequired**: Carry this choice into aggregate-resource policy, shared contracts, CAP-07.S02 task acceptance and the existing runtime-policy checkpoint in the complete successor packet. Independent incremental review still required; this file alone does not close the finding.

### Exact selected extraction policy03

**evaluationUnit**: One frozen eligible (QASPER question ID, declared simple extractive field ID) with existing human answer annotations and authenticated source-anchor mapping. Missing, unanswerable, unsupported and free-form strata remain separately reported; never silently relabel them positive extractive units.

**normalization**: For this custom adapter score only: Unicode NFC and CRLF/CR to LF, then Unicode casefold. Tokenize with Unicode regular expression \w+|[^\w\s], retaining punctuation tokens and duplicate token multiplicities. No stemming, article deletion, synonym/model judging or source-text rewriting. Keep original strings and exact source offsets separately.

**matching**: Each retained acceptable human answer annotation is one reference. Concatenate its ordered extractive spans with one space for token scoring, preserving the original individual spans and anchors. Match token multisets by sum of minimum token counts. Compute precision=overlap/predictionTokens and recall=overlap/referenceTokens. Choose the reference with greatest token F1, then precision, then stable original annotation order. Freeze acceptable-reference membership before comparison; do not assemble one reference from incompatible annotators or invent a missing reference.

**emptyPrediction**: On an answerable eligible unit, absent output, explicit abstention or an empty token sequence gives precision=0 and recall=0. An empty/undefined positive reference is not an eligible answerable unit and requires a visible mapping correction before comparison. Failed/timed-out execution is still a failed run, not a scored abstention.

**aggregation**: Average per-unit precision and recall within each declared eligible field, then give each field equal weight in the field macro. Publish each field's N, metrics and all unit outcomes. No consequential field that fails its declared threshold is hidden by the macro. Pooled micro/token-F1 and exact-span match are separate diagnostics, not alternative passing rules.

**promotionTargets**: {"macroPrecisionMinimum": 0.9, "macroRecallMinimum": 0.8}

**answerKindAndMissingness**: Keep fixed per-kind confusion, absent/unsupported counts, packet evidence coverage/truncation and hallucinated outputs on actual unanswerable cases. Missing gold or an unsupported stratum is not a free correct answer. Anchor/schema/rights denials remain deterministic hard checks.

**scope**: This is the selected custom initial QASPER adapter metric, not a claim of official leaderboard equivalence, universal scientific extraction or measured quality. Preserve source annotations, annotator disagreement and bounded domain claims.

### Exact selected verifier policy03

**labels**: ["SUPPORTS", "REFUTES", "NOT_ENOUGH_EVIDENCE", "ABSTAIN"]

**evaluationFrame**: The complete frozen eligible SciFact development frame with actual source labels and rationale mappings, including declared no-evidence cases. Report exact class Ns, exclusions and unknown/unjudged scope before any candidate comparison.

**precisionRule**: For each actionable label SUPPORTS and REFUTES, TP is an exact predicted/gold label match and FP is that predicted label against another actual judged gold label, including NOT_ENOUGH_EVIDENCE. Require the arithmetic mean of these two per-label precisions >=0.90. An absent or zero prediction denominator for either required label is undefined and cannot pass.

**recallRule**: Require TP_SUPPORTS/N_gold_SUPPORTS >=0.80 and TP_REFUTES/N_gold_REFUTES >=0.80 separately. ABSTAIN, missing predictions and wrong labels count as misses. A missing required gold class leaves that role's qualification unestablished; do not invent class members or substitute a pooled metric.

**answeredCoverageRule**: Require the number of valid explicit SUPPORTS, REFUTES or NOT_ENOUGH_EVIDENCE decisions divided by the complete eligible frame N >=0.80. ABSTAIN is unanswered. Technical failures, invalid output and timeouts remain hard failures and cannot be converted into abstention or excluded units.

**diagnostics**: Publish the complete confusion matrix, all per-class precision/recall, answered coverage, abstentions, rationale/anchor coverage and uncertainty intervals with actual Ns and method. NOT_ENOUGH_EVIDENCE is distinct from REFUTES and ABSTAIN. Unjudged evidence is never invented negative gold.

**humanAuthority**: These bounded initial targets do not certify scholarly truth or replace mandatory human review of consequential, inferred, disputed or low-confidence candidates. Same-model serial verification remains correlated, not independent-model evidence.

All three full unnumbered architecture texts and complete seven-page style/workflow/page/HTML payload are included under architecture-ux/. Source3541 is current/initial only, not finalW2/G2. Actual validation/acceptance remain pending. The 48 task IDs, 16 slice IDs and 924 hours including 28 refactoring hours remain. Successor05 changes executable slice order and one explicit task dependency, and reallocates four proof hours between existing tasks; all other microtiming goals remain unchanged.

## Ordered execution feasibility05

Proposed W3 execution order: CAP-07.S04, CAP-07.S02, CAP-07.S05, CAP-07.S03. Inherited CAP-07.S01 remains before these slices with all four W1 decisions/approval history unchanged. Every task includes explicit dependencies, its slice external dependency union and every earlier slice APPROVED gate. The64-node task/slice-gate witness is acyclic; it is source-only planned-data feasibility, not actual readiness or completed review. Preserve future-Wave decisions and states.

Registry/prompt/schema approval-state and UI/contract closure before local inference: freeze lawful gold frame, exact scoring/denominator rules and attestation/promotion schema; characterize deterministic scoring with declared synthetic reference cases, malformed/missing/forged report denial, immutable default/upgrade/rollback and benchmark/reviewer/residual bindings. Missing real evaluation remains Unknown/unqualified and cannot promote a role. This task does not claim actual local inference or measured model quality.

After complete S04 approval, retain genuine real local prompt/runtime integration: execute exact versioned prompt/schema through the signed no-network current-principal worker and canonical fixture-only qualification authority; measure admitted CPU/profile resources, actual cancellation/crash/normal drain, parser/model serialized reservation and structured/refusal handling. No mocked transport/resource pass or automatic scholarly role promotion. S05.T03 retains actual comparative gold scoring/default-upgrade proof.

After complete local-runtime S02 and observability/budget S05 predecessors, collect genuine comparable local model/prompt evaluations through that real admitted runtime on frozen lawful task/domain/profile/gold inputs. Apply unchanged metricPolicy03, bind benchmark/reviewer/residuals and actual report attestation; prove default upgrade/regression denial, controlled promotion/rollback/dependent-stale behavior in the existing dashboard. Registry mechanisms from S04 do not substitute for actual model outcomes; later consuming tasks requalify their exact changed task/prompt/schema inputs.

Allocation05 transfers four planned integration-proof hours from S04.T03(20→16) to S02.T03(20→22) and S05.T03(20→22). All product requirements remain, CAP07 total stays240 and the Wave stays924 hours with28 refactoring hours counted once. Estimates are proposed effort, not measured runtime.

## Canonical proposed-publication reconciliation

Actual W2/G2 initial completion is recorded at1cc8131d8b74cf6c536d48ce4badc25933981bbb; the current planning predecessor and committed post-exit roadmap is2e2f1a9d042c3dd8db3f8f31b648a36ad004c505. See artifacts/evidence/W2.initial-exit-recording-receipt-20261016-01.json and the independent Wave/S06/CP10 records. Historical3541 product,1b377 build/reference/Native,fc694 full90 and ownerf86 identities remain distinct. Initial1000 functional commit is qualified, but100k publication/fullmanifest/replay/reopen and continuous performance remain UNQUALIFIED; no1000 productcap or W3metadata/vector100k import-throughput inference. All failed/UNKNOWN/UNTESTED evidence, parser-only2.5333542s acceptance, source-search median7s/all24raws, strictClippyFAIL,409UNKNOWN, security expiry and platform/installer gaps remain. Owner933b moves optional cosmetics and optimization/performance intake to newW10; functional/security qualification residuals remain separately trackedW9, and larger-computing product workW5. Before W3 approval, suggested soft median timing overage strictly<7s may be accepted with W10 debt; completed comparable trials/allraws retained, failed/timeouts and hard functional/security/resource/cancellation bounds unchanged. Hosted university/cloud labels areW11/W12. All48IDs/16slices/924hours including28once, ordered proof ownership, policy03 metrics/token semantics and serial admission are retained. ADR0056–58/reference1.10 remain Proposed, active1.9 unchanged and W3approvalPENDING; no implementation is authorized.

## W3 authority recording — 2026-10-16

The owner approved the complete reviewed W3 proposal at
`45216934b81c4a437b3707df0f9e7f79a825e271` and directed implementation; see
`artifacts/evidence/W3.owner-planning-approval-20261016-01.md`.
ADR-0056, ADR-0057 and ADR-0058 are now Accepted. The exact reviewed experience
is published as RO-UI-ACADEMIC-MINIMAL-1.10 at
`3b47dfd4f332805e66c58542d3decd4e56c7f45e`, following its immutable human
design approval record. This is authority recording and material-plan binding,
with no change to selected decisions, task IDs, dependencies, criteria, proof
ownership, estimates or allocations. Earlier proposed/private wording remains
the original planning history. This paragraph applies only to the W3 contribution;
inherited decisions and future Waves retain their own authority.

The ordinary complete-Wave approval below/beside this plan binds the final
acceptance snapshot once. Taskctl readiness and dependency-eligible claims remain
mandatory; no actual model fit, quality, annotation, runtime, product proof or
release approval is supplied by planning acceptance. Minor nonfunctional styling
and eligible suggested-target median timing optimization go to W10 under the
latest owner direction; all hard functional/security/rights/resource/cancellation
limits and every raw failed or unknown result remain preserved.
