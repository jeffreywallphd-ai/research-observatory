---
document_type: generated-backlog-status-summary
source: planning/backlog.yaml
source_sha256: ab15b630ba6b7b3f1fd559bebf283d1ddd77dfcec39dbdf266c40a74efd87c40
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
| Release gates | 12 |

## Status distributions

### Capability completion

| Status | Count |
|---|---:|
| `APPROVED` | 1 |
| `IN_PROGRESS` | 1 |
| `PENDING` | 18 |

### Campaign state

| Status | Count |
|---|---:|
| `ACTIVE` | 1 |
| `COMPLETE` | 1 |
| `NONE` | 18 |

### Slice completion

| Status | Count |
|---|---:|
| `APPROVED` | 8 |
| `PENDING` | 109 |

### Task state

| Status | Count |
|---|---:|
| `NOT_STARTED` | 291 |
| `READY` | 1 |
| `IN_PROGRESS` | 1 |
| `DONE` | 27 |
| `DEFERRED` | 36 |

## Capability progress

| Capability | Campaign | Completion | Approved slices | Done tasks | Active task |
|---|---|---|---:|---:|---|
| `CAP-00` Delivery foundation and Codex execution system | `COMPLETE` | `APPROVED` | 6/6 | 19/19 | - |
| `CAP-01` Windows-first desktop shell and supervised local runtime | `ACTIVE` | `IN_PROGRESS` | 2/5 | 8/15 | `CAP-01.S03.T03` |
| `CAP-02` Local projects, durable storage, security, and recovery | `NONE` | `PENDING` | 0/5 | 0/16 | - |
| `CAP-03` Canonical domain, research intent, provenance, and durable workflows | `NONE` | `PENDING` | 0/6 | 0/20 | - |
| `CAP-04` Scholarly ingestion, connectors, canonicalization, and corpus governance | `NONE` | `PENDING` | 0/5 | 0/15 | - |
| `CAP-05` Document acquisition, parsing, source inspection, and page anchors | `NONE` | `PENDING` | 0/6 | 0/18 | - |
| `CAP-06` Local search, discovery, corpus diagnostics, and screening | `NONE` | `PENDING` | 0/6 | 0/18 | - |
| `CAP-07` Provider-neutral model gateway and governed AI execution | `NONE` | `PENDING` | 0/5 | 0/15 | - |
| `CAP-08` Evidence schemas, extraction, verification, and adjudication | `NONE` | `PENDING` | 0/6 | 0/18 | - |
| `CAP-09` Scholarly graph, comparison sets, synthesis, and reproducibility | `NONE` | `PENDING` | 0/6 | 0/18 | - |
| `CAP-10` Novelty auditing, research opportunities, and plural research modes | `NONE` | `PENDING` | 0/7 | 0/21 | - |
| `CAP-11` Windows PC/lab product hardening, validation, packaging, and release | `NONE` | `PENDING` | 0/6 | 0/19 | - |
| `CAP-12` University-hosted deployment, institutional identity, collaboration, and operations | `NONE` | `PENDING` | 0/6 | 0/18 | - |
| `CAP-13` Managed cloud control plane, tenant data planes, governance, and SaaS operations | `NONE` | `PENDING` | 0/6 | 0/18 | - |
| `CAP-14` Cross-platform desktop qualification and release | `NONE` | `PENDING` | 0/6 | 0/18 | - |
| `CAP-15` Empirical study design and protocol development | `NONE` | `PENDING` | 0/6 | 0/18 | - |
| `CAP-16` Manuscript blueprint, venue profiles, and article architecture | `NONE` | `PENDING` | 0/6 | 0/18 | - |
| `CAP-17` Technical report and study-results integration | `NONE` | `PENDING` | 0/6 | 0/18 | - |
| `CAP-18` Source-grounded manuscript drafting and publication artifacts | `NONE` | `PENDING` | 0/6 | 0/18 | - |
| `CAP-19` Reviewer simulation, editorial synthesis, and revision | `NONE` | `PENDING` | 0/6 | 0/18 | - |

## Release gates

| Gate | After wave | Unlocks | Status |
|---|---|---|---|
| `G0` Executable engineering baseline | `W0` | `W1` | `APPROVED` |
| `G1` Durable Windows local application core | `W1` | `W2` | `PENDING` |
| `G2` Inspectable Windows local corpus | `W2` | `W3` | `PENDING` |
| `G3` Windows local evidence workbench | `W3` | `W4` | `PENDING` |
| `G4` Minimum compelling Windows scholarly-reasoning product | `W4` | `W5` | `PENDING` |
| `G5` Windows PC/lab version 1.0 | `W5` | `W6` | `PENDING` |
| `G6` Cross-platform desktop version 1.0 | `W6` | `W7` | `PENDING` |
| `G7` Study design and manuscript foundation | `W7` | `W8` | `PENDING` |
| `G8` End-to-end research-production desktop | `W8` | `W9`, `W10` | `PENDING` |
| `G9` Advanced research-intelligence preview | `W9` | - | `PENDING` |
| `G10` University pilot | `W10` | `W11` | `PENDING` |
| `G11` Cloud limited availability | `W11` | - | `PENDING` |

## Active work

| Task | Status | Owner | Branch |
|---|---|---|---|
| `CAP-01.S03.T03` Implement sidecar lifecycle supervision in Tauri | `IN_PROGRESS` | codex | `codex/cap-01-desktop-shell` |
