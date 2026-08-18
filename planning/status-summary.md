---
document_type: generated-backlog-status-summary
source: planning/backlog.yaml
source_sha256: 365379ec1e30db9d524f942dce46a5a5ac7ead82d2ffba82efc2aaf4dca73331
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
| Waves | 12 |
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
| `ACTIVE` | 1 |
| `NONE` | 11 |

### Slice completion

| Status | Count |
|---|---:|
| `APPROVED` | 12 |
| `PENDING` | 105 |

### Task state

| Status | Count |
|---|---:|
| `NOT_STARTED` | 280 |
| `READY` | 1 |
| `REVIEW` | 1 |
| `DONE` | 38 |
| `DEFERRED` | 36 |

## Wave progress

| Wave | Pre-Wave approval | Campaign | Qualification | Approved slices | Done tasks | Exit gate |
|---|---|---|---|---:|---:|---|
| `W0` - Engineering foundation | `APPROVED` | `NONE` | `APPROVED` | 6/6 | 19/19 | `G0` / `APPROVED` |
| `W1` - Windows local runtime and durable core | `APPROVED` | `ACTIVE` | `IN_PROGRESS` | 6/15 | 19/48 | `G1` / `PENDING` |
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
| CAP-local-project-storage (`CAP-02`) — Local projects, durable storage, security, and recovery | `NONE` | `PENDING` | 2/5 | 6/16 | `CAP-02.S03.T01` |
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

| Task | Status | Owner | Branch |
|---|---|---|---|
| `CAP-02.S03.T01` Implement content-addressed object storage abstraction | `REVIEW` | codex | `codex/w1-windows-local-runtime` |
