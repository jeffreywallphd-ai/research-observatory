---
document_type: generated-backlog-status-summary
source: planning/backlog.yaml
source_sha256: f22924d7744070dcbc28d9c157e679c513c0fde89e30315d99d5912ddb06d3b1
generator: tools/backlog_views.py
manual_edit: prohibited
---

# Backlog status summary

> **GENERATED FILE - DO NOT EDIT.** `planning/backlog.yaml` is authoritative. Run `python tools/backlog_views.py --repo .` to regenerate this file.

## Ledger totals

| Item | Count |
|---|---:|
| Capabilities | 20 |
| Slices | 117 |
| Tasks | 356 |
| Enabler tasks | 2 |
| Waves | 12 |
| Wave approval bases | 1 |
| Wave amendments | 2 |
| Release gates | 12 |

## Status distributions

### Capability completion

| Status | Count |
|---|---:|
| `APPROVED` | 1 |
| `PAUSED` | 1 |
| `PENDING` | 18 |

### Wave campaign state

| Status | Count |
|---|---:|
| `NONE` | 11 |
| `PAUSED` | 1 |

### Slice completion

| Status | Count |
|---|---:|
| `APPROVED` | 13 |
| `PENDING` | 104 |

### Task state

| Status | Count |
|---|---:|
| `NOT_STARTED` | 275 |
| `READY` | 3 |
| `DONE` | 42 |
| `DEFERRED` | 36 |

### Wave amendment lifecycle

| Status | Count |
|---|---:|
| `ACTIVE` | 1 |
| `ADOPTED` | 1 |

### Enabler task state

| Status | Count |
|---|---:|
| `DONE` | 2 |

## Wave authority and append-only amendments

Proposal approval, materialization lifecycle, and campaign state remain distinct. A Wave approval is immutable; later authority is an ordered amendment record.

| Wave | Authority | Packet / ECR | Approval record | Lifecycle | Bootstrap | Campaign | Enabler tasks |
|---|---|---|---|---|---|---|---:|
| `W1` | `BASE` | `594e63be501711d67d17a4aef176bb9b6a8748be` | `901eb5c1351fa32c7173a5f0cebc2fdf9ddb1701` | `APPROVED` | - | - | 0 |
| `W1` | `W1.A01` | `-` | `planning/wave-amendment-approvals/W1.A01.json` | `ADOPTED` | `NONE` | `NONE` | 0 |
| `W1` | `W1.A02` | `ECR-0001` | `planning/wave-amendment-approvals/W1.A02.json` | `ACTIVE` | `APPROVED` | `ACTIVE` | 2 |

## Amendment-exit review and adoption projections

Immutable exit rounds, the latest completion projection, and bound adoption checkpoints remain distinct.

### Amendment-exit review and adoption — W1.A01

**Exit-review mode:** `legacy latest-completion-only projection` — no immutable exit rounds are recorded; this view does not fabricate history.

**Latest completion projection:** `APPROVED` by repository-owner at `2026-08-20T23:38:52+00:00`

**Latest completion evidence:** `planning/wave-amendment-approvals/W1.A01.json`

**Latest completion notes:** Historical authority migration only.

**Bound amendment-adoption checkpoints:**

- None

### Amendment-exit review and adoption — W1.A02

**Exit-review mode:** `append-only v1` / 1 completed round(s)

#### Exit round R01

**Immutable amendment-exit packet:** `R01` / packet SHA-256 `4e1a290f48f1ad2a5663fa1de657758aebcff7c6429deb79deb9ef419c3cf6df`

- Candidate / declared candidate / branch: `b77d5b1cea5526b391d5acbe3aa220a0ba510ca6` / `546eb572526acd2996ee2c5fb74f29135d295760` / `codex/w1-windows-local-runtime`
- Submitted by / at: codex / `2026-08-21T03:00:48+00:00`
- Bound exit evidence: amendment `W1.A02` / `artifacts/evidence/W1.A02.exit.json` / `fdfcbd04977e2c786caa36ad429f7713c5832fd6739663a52b0838ae64d48204` / `b77d5b1cea5526b391d5acbe3aa220a0ba510ca6`
- Acceptance-criteria SHA-256: `3144c4095e1d75a552137bb96fb35a74faa2f7eaa0c3e4f78eaaaa7ee7d15323`
- Selected-check SHA-256: `fba8ee2f3521746f6bfa8f2ee2fc2478009012967cedb4d280546496fed654fe`
- Selected checks: `.venv\Scripts\python.exe tools\taskctl.py --file planning\backlog.yaml validate`, `.venv\Scripts\python.exe tools\taskctl.py --file planning\backlog.yaml review-telemetry`, `.venv\Scripts\python.exe tools\plan_review_check.py --repo .`, `.venv\Scripts\python.exe tools\backlog_views.py --repo . --check`, `.venv\Scripts\python.exe tools\planctl.py --repo . ecr validate ECR-0001 --require-approved`, `git diff --check`
- Prior round / replayed open findings: `-` / -

**Disposition / reviewer / time:** `changes-requested` / b00-independent-reviewer / `2026-08-22T01:56:53+00:00`

**Reviewed state commit:** `b77d5b1cea5526b391d5acbe3aa220a0ba510ca6`

**Immutable exit-review ledger:** `artifacts/evidence/W1.A02.exit-review-R01.json` / `758f40080e775d5ba19a78465d0ea7dec422929ff9285d61bb6978a49b1f48e7`

**Review notes:** CHANGES_REQUESTED at exact frozen state b77d5b1cea5526b391d5acbe3aa220a0ba510ca6. ECR authority, B00/T01/T02 histories, evidence hashes, privacy-safe telemetry, backlog, generated views, and 145 review pages pass. Adoption is not ready because amendment-exit evidence and checkpoint evidence are not exact-commit bound, and the exit record conflates the amendment campaign with the paused W1 campaign. No W1 qualification, adoption, G1 approval, ordinary resume, remote integration, or full W1 exit-suite claim was made.

**Findings opened:**

- `W1.A02-EXIT-R01-F01` `high` blocking=`True` criterion=`6` — Amendment-exit approval and adoption are not bound to the reviewed candidate or evidence; reproduce: The frozen completion record stores only the string artifacts/evidence/W1.A02.exit.json, without its SHA-256, candidate commit, branch, or an immutable exit-review ledger. command_amendment_review does not load or validate the exit evidence, and command_amendment_adopt revalidates amendment authority and task inventory but not the independently reviewed exit candidate/evidence. In a read-only in-memory replay, approve the current completion, replace completion.evidence with artifacts/evidence/never-reviewed-or-existing.json, and invoke adoption with artifacts/evidence/never-reviewed-checkpoint.json. Adoption succeeds, records ADOPTED and W1.CP01, and full semantic validation returns zero errors even though neither evidence path exists. An adverse amendment-exit review also lacks a frozen append-only finding/closure ledger, so a later submission can overwrite the completion projection while retaining only free-form lifecycle rationale.; remediate: Extend the frozen append-only review control to amendment exit: bind submission to exact candidate/frozen-state commit, branch, evidence path/SHA/commit, criteria and selected checks; store immutable severity-ranked exit-review attempts, findings, and closures; and make review plus adoption revalidate the exact reviewed blob and history. Store the adoption checkpoint as a validated path/SHA/commit reference and deny missing, substituted, stale, forked, dirty, or unreviewed evidence. Add adversarial tests for nonexistent and post-review-substituted exit/checkpoint evidence and preservation of a changes-requested exit round.
- `W1.A02-EXIT-R01-F02` `medium` blocking=`True` criterion=`5` — Exit evidence records an impossible mixed stopped-state tuple; reproduce: artifacts/evidence/W1.A02.exit.json records stoppedState as campaignStatus=PAUSED, campaignScope=wave-amendment, and pauseReason=amendment-hold. No campaign has that tuple. At b77d5b1, the amendment campaign is REVIEW/wave-amendment with pause_reason=null, while the W1 campaign is PAUSED/amendment-hold with the explicit ECR preparation pause reason.; remediate: Replace stoppedState with separately named exact waveCampaign and amendmentCampaign objects, preserving the exact required next transition. Regenerate and validate affected views, freeze a new evidence hash and candidate, and resubmit the amendment exit without claiming W1 qualification, adoption, or resumption.

**Prior finding closures:**

- None

**Current immutable amendment-exit submission awaiting review:** None

**Latest completion projection:** `CHANGES_REQUESTED` by b00-independent-reviewer at `2026-08-22T01:56:53+00:00`

**Latest completion evidence:** `artifacts/evidence/W1.A02.exit.json`

**Latest completion notes:** CHANGES_REQUESTED at exact frozen state b77d5b1cea5526b391d5acbe3aa220a0ba510ca6. ECR authority, B00/T01/T02 histories, evidence hashes, privacy-safe telemetry, backlog, generated views, and 145 review pages pass. Adoption is not ready because amendment-exit evidence and checkpoint evidence are not exact-commit bound, and the exit record conflates the amendment campaign with the paused W1 campaign. No W1 qualification, adoption, G1 approval, ordinary resume, remote integration, or full W1 exit-suite claim was made.

**Bound amendment-adoption checkpoints:**

- None


## Task review history projections

Append-only rounds remain distinct from the current latest-review projection. Legacy records are labeled latest-review-only and receive no synthesized rounds.

| Task | Mode | Completed rounds | Current submission | Latest projection | Open findings |
|---|---|---:|---|---|---|
| `CAP-00.S01.T01` | `legacy latest-review-only` | 0 | `-` | approved / codex-review | - |
| `CAP-00.S01.T02` | `legacy latest-review-only` | 0 | `-` | approved / codex-review | - |
| `CAP-00.S01.T03` | `legacy latest-review-only` | 0 | `-` | approved / codex-review | - |
| `CAP-00.S02.T01` | `legacy latest-review-only` | 0 | `-` | approved / codex-review | - |
| `CAP-00.S02.T02` | `legacy latest-review-only` | 0 | `-` | approved / codex-review | - |
| `CAP-00.S02.T03` | `legacy latest-review-only` | 0 | `-` | approved / codex-review | - |
| `CAP-00.S03.T01` | `legacy latest-review-only` | 0 | `-` | approved / codex-review | - |
| `CAP-00.S03.T02` | `legacy latest-review-only` | 0 | `-` | approved / codex-review | - |
| `CAP-00.S03.T03` | `legacy latest-review-only` | 0 | `-` | approved / codex-security-review | - |
| `CAP-00.S04.T01` | `legacy latest-review-only` | 0 | `-` | approved / codex-review | - |
| `CAP-00.S04.T02` | `legacy latest-review-only` | 0 | `-` | approved / codex-review | - |
| `CAP-00.S04.T03` | `legacy latest-review-only` | 0 | `-` | approved / codex-review | - |
| `CAP-00.S05.T01` | `legacy latest-review-only` | 0 | `-` | approved / codex-review | - |
| `CAP-00.S05.T02` | `legacy latest-review-only` | 0 | `-` | approved / codex-review | - |
| `CAP-00.S05.T03` | `legacy latest-review-only` | 0 | `-` | approved / codex-review | - |
| `CAP-00.S06.T01` | `legacy latest-review-only` | 0 | `-` | approved / codex-review | - |
| `CAP-00.S06.T02` | `legacy latest-review-only` | 0 | `-` | approved / agent:descartes | - |
| `CAP-00.S06.T03` | `legacy latest-review-only` | 0 | `-` | approved / agent:descartes | - |
| `CAP-00.S06.T04` | `legacy latest-review-only` | 0 | `-` | approved / agent:descartes | - |
| `CAP-01.S01.T01` | `legacy latest-review-only` | 0 | `-` | approved / agent:descartes | - |
| `CAP-01.S01.T02` | `legacy latest-review-only` | 0 | `-` | approved / agent:maxwell | - |
| `CAP-01.S01.T03` | `legacy latest-review-only` | 0 | `-` | approved / agent:maxwell | - |
| `CAP-01.S02.T01` | `legacy latest-review-only` | 0 | `-` | approved / agent:maxwell | - |
| `CAP-01.S02.T02` | `legacy latest-review-only` | 0 | `-` | approved / agent:maxwell | - |
| `CAP-01.S02.T03` | `legacy latest-review-only` | 0 | `-` | approved / agent:maxwell | - |
| `CAP-01.S03.T01` | `legacy latest-review-only` | 0 | `-` | approved / agent:maxwell | - |
| `CAP-01.S03.T02` | `legacy latest-review-only` | 0 | `-` | approved / agent:maxwell | - |
| `CAP-01.S03.T03` | `legacy latest-review-only` | 0 | `-` | approved / agent:curie | - |
| `CAP-01.S04.T01` | `legacy latest-review-only` | 0 | `-` | approved / curie | - |
| `CAP-01.S04.T02` | `legacy latest-review-only` | 0 | `-` | approved / agent:curie | - |
| `CAP-01.S04.T03` | `legacy latest-review-only` | 0 | `-` | approved / agent:curie | - |
| `CAP-02.S01.T01` | `legacy latest-review-only` | 0 | `-` | approved / agent:curie | - |
| `CAP-02.S01.T02` | `legacy latest-review-only` | 0 | `-` | approved / agent:curie | - |
| `CAP-02.S01.T03` | `legacy latest-review-only` | 0 | `-` | approved / agent:curie | - |
| `CAP-02.S02.T01` | `legacy latest-review-only` | 0 | `-` | approved / agent:curie | - |
| `CAP-02.S02.T02` | `legacy latest-review-only` | 0 | `-` | approved / agent:curie | - |
| `CAP-02.S02.T03` | `legacy latest-review-only` | 0 | `-` | approved / agent:curie | - |
| `CAP-02.S03.T01` | `legacy latest-review-only` | 0 | `-` | approved / agent:curie | - |
| `CAP-02.S03.T02` | `legacy latest-review-only` | 0 | `-` | approved / t02_security_review | - |
| `CAP-02.S03.T03` | `legacy latest-review-only` | 0 | `-` | approved / independent-agent-t03-slice-remediation | - |
| `CAP-02.S04.T01` | `legacy latest-review-only` | 0 | `-` | approved / cap02_s04_t01_security_review | - |
| `CAP-03.S01.T01` | `legacy latest-review-only` | 0 | `-` | approved / agent:curie | - |
| `W1.A02.T01` | `append-only v1` | 2 | `-` | approved / b00-independent-reviewer | - |
| `W1.A02.T02` | `append-only v1` | 2 | `-` | approved / b00-independent-reviewer | - |
## Wave progress

| Wave | Pre-Wave approval | Campaign | Qualification | Approved slices | Done tasks | Exit gate |
|---|---|---|---|---:|---:|---|
| `W0` - Engineering foundation | `APPROVED` | `NONE` | `APPROVED` | 6/6 | 19/19 | `G0` / `APPROVED` |
| `W1` - Windows local runtime and durable core | `APPROVED` | `PAUSED` | `PAUSED` | 7/15 | 23/48 | `G1` / `PENDING` |
| `W2` - Windows local evidence foundation | `PENDING` | `NONE` | `PENDING` | 0/11 | 0/33 | `G2` / `PENDING` |
| `W3` - Windows local research workbench | `PENDING` | `NONE` | `PENDING` | 0/16 | 0/48 | `G3` / `PENDING` |
| `W4` - Windows scholarly reasoning and novelty MVP | `PENDING` | `NONE` | `PENDING` | 0/9 | 0/27 | `G4` / `PENDING` |
| `W5` - Windows PC/lab production release | `PENDING` | `NONE` | `PENDING` | 0/8 | 0/25 | `G5` / `PENDING` |
| `W6` - Cross-platform desktop qualification | `PENDING` | `NONE` | `PENDING` | 0/6 | 0/18 | `G6` / `PENDING` |
| `W7` - Study design and manuscript foundations | `PENDING` | `NONE` | `PENDING` | 0/13 | 0/39 | `G7` / `PENDING` |
| `W8` - Results integration, manuscript drafting, and reviewer simulation | `PENDING` | `NONE` | `PENDING` | 0/18 | 0/54 | `G8` / `PENDING` |
| `W9` - Advanced research-intelligence preview | `PENDING` | `NONE` | `PENDING` | 0/3 | 0/9 | `G9` / `PENDING` |
| `W10` - University-hosted pilot | `PENDING` | `NONE` | `PENDING` | 0/6 | 0/18 | `G10` / `PENDING` |
| `W11` - Managed cloud delivery | `PENDING` | `NONE` | `PENDING` | 0/6 | 0/18 | `G11` / `PENDING` |

## Capability progress

| Capability contribution | Legacy campaign | Completion | Approved slices | Done tasks | Active task |
|---|---|---|---:|---:|---|
| CAP-delivery-foundation (`CAP-00`) — Delivery foundation and Codex execution system | `COMPLETE` | `APPROVED` | 6/6 | 19/19 | - |
| CAP-windows-desktop-runtime (`CAP-01`) — Windows-first desktop shell and supervised local runtime | `PAUSED` | `PAUSED` | 4/5 | 12/15 | - |
| CAP-local-project-storage (`CAP-02`) — Local projects, durable storage, security, and recovery | `NONE` | `PENDING` | 3/5 | 10/16 | - |
| CAP-research-domain-workflows (`CAP-03`) — Canonical domain, research intent, provenance, and durable workflows | `NONE` | `PENDING` | 0/6 | 1/20 | - |
| CAP-scholarly-ingestion (`CAP-04`) — Scholarly ingestion, connectors, canonicalization, and corpus governance | `NONE` | `PENDING` | 0/5 | 0/15 | - |
| CAP-document-inspection (`CAP-05`) — Document acquisition, parsing, source inspection, and page anchors | `NONE` | `PENDING` | 0/6 | 0/18 | - |
| CAP-search-screening (`CAP-06`) — Local search, discovery, corpus diagnostics, and screening | `NONE` | `PENDING` | 0/6 | 0/18 | - |
| CAP-model-gateway (`CAP-07`) — Provider-neutral model gateway and governed AI execution | `NONE` | `PENDING` | 0/5 | 0/15 | - |
| CAP-evidence-verification (`CAP-08`) — Evidence schemas, extraction, verification, and adjudication | `NONE` | `PENDING` | 0/6 | 0/18 | - |
| CAP-scholarly-graph-synthesis (`CAP-09`) — Scholarly graph, comparison sets, synthesis, and reproducibility | `NONE` | `PENDING` | 0/6 | 0/18 | - |
| CAP-novelty-opportunities (`CAP-10`) — Novelty auditing, research opportunities, and plural research modes | `NONE` | `PENDING` | 0/7 | 0/21 | - |
| CAP-windows-release (`CAP-11`) — Windows PC/lab product hardening, validation, packaging, and release | `NONE` | `PENDING` | 0/6 | 0/19 | - |
| CAP-university-hosting (`CAP-12`) — University-hosted deployment, institutional identity, collaboration, and operations | `NONE` | `PENDING` | 0/6 | 0/18 | - |
| CAP-cloud-platform (`CAP-13`) — Managed cloud control plane, tenant data planes, governance, and SaaS operations | `NONE` | `PENDING` | 0/6 | 0/18 | - |
| CAP-cross-platform-desktop (`CAP-14`) — Cross-platform desktop qualification and release | `NONE` | `PENDING` | 0/6 | 0/18 | - |
| CAP-study-design (`CAP-15`) — Empirical study design and protocol development | `NONE` | `PENDING` | 0/6 | 0/18 | - |
| CAP-manuscript-blueprints (`CAP-16`) — Manuscript blueprint, venue profiles, and article architecture | `NONE` | `PENDING` | 0/6 | 0/18 | - |
| CAP-results-integration (`CAP-17`) — Technical report and study-results integration | `NONE` | `PENDING` | 0/6 | 0/18 | - |
| CAP-manuscript-drafting (`CAP-18`) — Source-grounded manuscript drafting and publication artifacts | `NONE` | `PENDING` | 0/6 | 0/18 | - |
| CAP-review-revision (`CAP-19`) — Reviewer simulation, editorial synthesis, and revision | `NONE` | `PENDING` | 0/6 | 0/18 | - |

## Release gates

| Gate | After wave | Unlocks | Status |
|---|---|---|---|
| `G0` — W0 exit / W1 activation — Executable engineering baseline | `W0` | `W1` | `APPROVED` |
| `G1` — W1 exit / W2 activation — Durable Windows local application core | `W1` | `W2` | `PENDING` |
| `G2` — W2 exit / W3 activation — Inspectable Windows local corpus | `W2` | `W3` | `PENDING` |
| `G3` — W3 exit / W4 activation — Windows local evidence workbench | `W3` | `W4` | `PENDING` |
| `G4` — W4 exit / W5 activation — Minimum compelling Windows scholarly-reasoning product | `W4` | `W5` | `PENDING` |
| `G5` — W5 exit / W6 activation — Windows PC/lab version 1.0 | `W5` | `W6` | `PENDING` |
| `G6` — W6 exit / W7 activation — Cross-platform desktop version 1.0 | `W6` | `W7` | `PENDING` |
| `G7` — W7 exit / W8 activation — Study design and manuscript foundation | `W7` | `W8` | `PENDING` |
| `G8` — W8 exit / W9, W10 activation — End-to-end research-production desktop | `W8` | `W9`, `W10` | `PENDING` |
| `G9` — W9 exit / - activation — Advanced research-intelligence preview | `W9` | - | `PENDING` |
| `G10` — W10 exit / W11 activation — University pilot | `W10` | `W11` | `PENDING` |
| `G11` — W11 exit / - activation — Cloud limited availability | `W11` | - | `PENDING` |

## Active work

No task is currently active.
