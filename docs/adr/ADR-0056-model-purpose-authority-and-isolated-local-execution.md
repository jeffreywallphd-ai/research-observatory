---
id: ADR-0056
title: Model-purpose authority and isolated local execution
status: Proposed
date: 2026-10-16
deciders: []
linked_tasks:
- CAP-07.S02.T01
- CAP-07.S02.T02
- CAP-07.S02.T03
- CAP-07.S03.T01
- CAP-07.S03.T02
- CAP-07.S03.T03
- CAP-07.S04.T02
- CAP-07.S05.T01
- CAP-07.S05.T02
decision_scope: Proposed Windows local model-purpose authorization, worker isolation, qualification purpose, and shared resource admission; no accepted authority or W3 execution.
affected_paths:
- services/core-api/src/research_observatory_core/model_*.py
- services/core-api/src/research_observatory_core/workflow_executor.py
- services/core-api/src/research_observatory_core/ports/**
- workers/**
- packages/contracts/model-gateway/**
supersedes: []
superseded_by: null
---

# ADR-0056: Model-purpose authority and isolated local execution

This is an unnumbered private proposal using the existing ADR template. `id: null` reserves nothing; this file is not indexed, accepted, or a valid substitute for an accepted architecture record. Acceptance and the single complete W3 approval remain future actions after W2/G2. Exact proposed policy inputs are listed in the accompanying manifest.

## Context

[ADR-0021](ADR-0021-adopt-provider-neutral-model-task-and-result-contracts.md) already owns eight provider-neutral task kinds and immutable input/result authority. It does not grant model-use rights, resource availability, a runtime sandbox or a remote destination. [ADR-0028](ADR-0028-isolate-windows-connectors-and-parsers-behind-narrow-brokers.md) owns connector/parser isolation; its connector permissions and 256 MiB limit cannot be relabelled model authority. Systems Design 6/12 requires local operation, policy before inference, exact frozen routes and role-specific evaluation. Same-user loopback is not the claimed no-network/no-vault boundary.

The refinement-02 packet proposes CPU-only tiny/small choices, not present fit or scholarly capability. Root-selected policy03 adds parser/model exclusion through the existing LocalWorkerAdmission/LocalAdmissionController. Its source currently documents a cooperative, in-process, pre-claim ledger. We must extend that seam without claiming control of unrelated Core processes or importing planning machinery into runtime.

## Candidates

1. Run an ordinary same-user localhost inference server and rely on application checks. This has the lowest integration cost and suits a deliberately weaker trust claim, but ambient filesystem/network authority fails this proposal's hostile-artifact boundary.
2. Reuse native LPAC/private-pipe/lifetime mechanisms with a distinct model-purpose worker, explicit model artifact access, Core-held rights/budgets and conservative serial admission. This fits the local account/container-free outcome, at the cost of real native runtime/operator/ACL qualification.
3. Require a VM/container model service. This could offer another isolation layer but adds installation, capacity and operation prerequisites unsupported by the initial Windows local outcome. It remains an alternative if candidate 2 is demonstrated infeasible, never an automatic fallback.

## Decision

Propose candidate 2, subject to actual acceptance and implementation proof.

Core must resolve exact immutable source revisions, current rights observations, classification, accepted Intent, actor/session, purpose-specific model-use grants and an immutable budget policy before every dispatch. Preserve PUBLIC_METADATA, LICENSED_METADATA, OPEN_FULL_TEXT, LICENSED_FULL_TEXT, PRIVATE_RESEARCH and RESTRICTED, with most-restrictive composition and unknown=deny. The gateway's coarse public/internal/confidential/restricted projection is not a source grant. Inspection, storage, export, local modeling and egress remain separate permissions; human consent cannot override source-holder restrictions. Revocation stops new access and invalidates replay/acceptance authority, retaining provenance and restricted/stale derivatives without exposing them.

The signed, version-matched model-specific native worker receives bounded authorized text/tensors and read-only exact model/runtime artifact access, with explicit handle inheritance and private framed pipes. It receives no project DB, vault, secret, generic filesystem path, shell/tool invocation or network capability. Signed inventory/digests establish artifact identity, not safety or license rights. Disallow model-supplied Python/pickle/custom code, ONNX custom-op DLLs, remote configuration and arbitrary DLL search; disable runtime telemetry. Qualify llama.cpp and native ONNX CPU drivers separately, including the actual decoder/KV/operator/tokenizer companions. Opening a project, selecting a model, or refreshing status never downloads, evaluates or loads it.

Keep ADR-0021 task/result semantics and all eight kinds. Trusted qualification purpose belongs to Core operation/policy context, not a renderer-controlled flag or overloaded portable field. A finite, rights-cleared fixture qualification operation may gather technical and later evaluation evidence using the same real policy/principal/resource boundary. It cannot read arbitrary research, promote a model, write accepted scholarly outputs or pretend an evaluation already exists. Ordinary per-role execution additionally requires a current scoped evaluation attestation.

Manual routes pin the exact artifact/runtime/profile. Explicit auto-smallest or auto-best-fit selects only from a user-granted, installed, already-qualified per-role set. Filter current rights, capability, role quality and capacity first; auto-smallest chooses lowest measured eligible footprint, auto-best-fit uses declared role evaluation then lower footprint as tie-breaker. Record the selected route and reason before dispatch. No silent download, license acceptance, remote fallback or substitution for frozen work.

Incorporate the exact parserModelAdmission choice in `root-selected-policy-refinement-03.json` (manifest-bound SHA256 `1c40fcbe2ed959479e74305986b4b2cc7efed18d2fa7895c0a148cf07dc76d81`). One shared existing Core resource authority reserves the whole expensive demand before claim. Expensive parser and model work exclude each other across the projects supervised by that authority. Keep reservations until actual owned drain and model unload; cancellation, crash or unknown cleanup cannot release live capacity. Then reobserve pressure, reauthorize and admit the queued newcomer. This is not machine-wide synchronization.

Use refinement-02's whole-application preferred 2048 MiB / explicitly selected upper 3072 MiB targets, including Core/Native/renderer/WebView/background/model descendants, and its conservative max(A,B), 128 MiB interactive reserve and incremental physical/commit headroom rules. Per-role profile caps are proposed engineering targets, not measured fit. Job limits constrain private commit, not RSS/mapped model pages or an OS-enforced whole-app physical cap. Unknown coverage/headroom queues or denies. Preserve the inherited parser principal, quality, mutex, cancellation/recovery and 4096 MiB private-commit ceiling; it is neither actual use nor a new RAM requirement. Do not reduce it silently to make this aggregate proposal pass.

Remote adapters are optional and disabled by default. Safe protocol fixtures may qualify OpenAI-compatible and Anthropic transports without a provider account. Live use needs exact destination/model/terms/retention/price, source-specific lawful purpose, minimized payload preview, fresh scoped consent, credentials and nonzero human-authorized budget. Initial remote scope permits only positively classified, permitted public/open inputs; licensed/private/restricted or unknown inputs deny. Offline denies before DNS/HTTP and never queues a remote fallback. Reserve cumulative usage/spend before dispatch; unknown provider usage or cancellation is not an assumed refund.

## Consequences

This adds real worker/runtime packaging and canonical permission/budget work, rather than relaxing the existing intentional unavailable-policy denials. Tiny model metadata may still fail operator, memory or role quality qualification; that role stays unavailable and manual research remains usable. Manual fallback alone is not completion of a promised model-supported G3 outcome.

Add versioned canonical source-classification, model-use grant, budget/reservation and eligibility facts through backup-first migration from the actual approved predecessor. Do not reserve a schema number here, backfill consent, reinterpret old queued authority, or mutate frozen ADR-0021 envelopes. Old records with missing authority remain denied. Persist definition/run/attempt/lease/provenance links under ADR-0025; no DB transaction spans a model/network call. A richer internal versioned resource witness must not silently redefine existing coarse HostModelObservation fields.

On failed update/qualification, disable the new artifact/profile and retain old immutable history/compatible readers and verified backups. Cancel/unload and release only proven drained resources; do not downgrade isolation, reactivate stale approvals or substitute a different model. Keep private prompts, KV caches, outputs and diagnostics protected/ephemeral according to purpose; logs carry safe identifiers/codes rather than content. Shared project owner/OS administrator and compromised trusted Core remain outside this worker isolation claim.

## Verification

Future task evidence must establish real packaged LPAC identity, no direct internet/loopback or ambient vault/profile read/write, exact artifact and handle grants, framed protocol tamper/oversize/job mismatch denial, parent death/cancel/OOM/crash and normal descendant drain. Mocks do not prove these boundaries. Test rights revocation at dispatch/read/output/cache replay, missing/expired authority, budget races and unknown usage, pinned-route substitution, offline zero-egress and optional consent cancellation.

Prove actual parser/model contention queues or denies, no expensive overlap, retained live reservations on crash/unknown cleanup and fresh re-admission only after drain/unload and capacity recheck. Observe whole-app A/B/private-commit/mappings with intervals/gaps; report hard failures and overshoot, no current fit guarantee. Qualification fixtures cannot publish ordinary accepted evidence or grant themselves role eligibility. Verify backup/restart/old-authority denial and unchanged public envelope parity. Use existing architecture, ADR, contract, quality, packaging and affected UI checks after the proposal is ordinarily accepted; none ran for this payload.

## Task links

The frontmatter names model runtime/catalog/resource, optional remote, structured validation and budget/observability owners. CAP-07.S04.T03 and CAP-07.S05.T03 supply later role evaluation/promotion; CAP-06.S02.T02 and CAP-06.S03.T02 consume admitted embedding/rerank roles without bypassing this authority. Exact immutable IDs, dependencies and estimates remain those in the refinement-02 task register; this proposal adds no task or campaign.
