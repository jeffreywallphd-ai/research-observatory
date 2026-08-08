---
id: ADR-0002
title: Govern the evaluation registry as a support-only repository area
status: Accepted
date: 2026-08-08
deciders:
  - CAP-00 benchmark-registry implementation and independent review
linked_tasks:
  - CAP-00.S05.T02
decision_scope: Ownership and dependency direction of the top-level evaluation registry, golden outputs, benchmark cases, schemas, and approval records.
affected_paths:
  - architecture-boundaries.json
supersedes: []
superseded_by: null
---

# ADR-0002: Govern the evaluation registry as a support-only repository area

## Context

The Architecture Baseline 1.3 names `evaluation/` as the home for benchmarks,
calibration, and regression gates. CAP-00.S05.T02 must establish reusable golden
outputs and benchmark lineage before product modules exist, while preserving the
rule that governance and test assets never become mutable product runtime state.
The current machine architecture contract lists every top-level area but omitted
the baseline's evaluation area, causing the intended registry to fail closed.

## Candidates

1. Put benchmark definitions under `tools/` or `tests/`, mixing executable
   automation or test harnesses with long-lived datasets, baselines, and approvals.
2. Add `evaluation/` as a support-only architecture area that tests and tools may
   inspect but product runtime modules cannot depend on.
3. Store baselines as ungoverned artifacts outside the repository, weakening
   offline reproducibility, rights review, and exact commit evidence.

## Decision

Adopt candidate 2. `evaluation/` owns only versioned benchmark registries,
datasets/case references, golden outputs, schemas, and approval lineage. It is a
support target for verification and repository tooling, never a governed product
module or a runtime configuration source. Baseline mutation remains subject to
hash, version, history, explicit approval, task evidence, and independent review.

## Consequences

Evaluation assets become discoverable, offline, reviewable, and portable across
local, university, and cloud qualification without changing product behavior.
The new area adds maintained registry and approval schemas, canonical baseline
and prompt paths, and an immutable hash-pinned approval boundary; large or licensed
datasets must remain external or use separately governed distribution mechanisms.
No network service, secret, user content, model binary, or generated scratch
result belongs in the area. Tests may depend on evaluation assets, but apps,
services, workers, and portable product contracts may not. Rollback removes the
area and this architecture declaration together after preserving any required
evidence; a different long-term location requires a superseding ADR.

## Verification

- `python tools/architecture_check.py --repo .`
- `python tools/adr_check.py --repo . --base <task-base> --head HEAD`
- `python tools/benchmark_registry.py --repo .`
- Foundation unit tests for deterministic execution, confinement, hashes, and
  version/history/human-approval denial boundaries.

## Task links

- `CAP-00.S05.T02` creates the support area, registry, runner, initial baselines,
  and approval policy.
