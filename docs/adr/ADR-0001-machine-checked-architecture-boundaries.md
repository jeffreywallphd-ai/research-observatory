---
id: ADR-0001
title: Adopt machine-checked architecture boundaries and protected-interface review
status: Accepted
date: 2026-08-08
deciders:
  - CAP-00 architecture baseline implementation
linked_tasks:
  - CAP-00.S02.T01
  - CAP-00.S02.T03
decision_scope: Repository module dependency directions, stable-interface ownership, deployment-profile boundaries, and ADR enforcement for protected paths.
affected_paths:
  - architecture-boundaries.json
  - architecture-protected-paths.json
  - repository-structure.json
  - docs/architecture/source/systems-design.md
  - packages/contracts/**
  - apps/desktop/**/api/**
  - services/core-api/**/ports/**
  - workers/**/contracts/**
supersedes: []
superseded_by: null
---

# ADR-0001: Adopt machine-checked architecture boundaries and protected-interface review

## Context

The Architecture Baseline 1.3 defines one desktop client, a Python modular
monolith, isolated workers, portable contracts, and distinct local, university,
and cloud project-home boundaries. Narrative guidance alone cannot reliably stop
an automated change from introducing a reverse dependency, an unreviewed stable
interface change, or a later-wave server implementation.

## Candidates

1. Keep the narrative baseline as the only authority and rely on reviewer memory.
2. Maintain a default-deny machine contract and require an indexed ADR whenever a
   change set touches protected module or interface paths.
3. Freeze every architecture-related path and require manual repository-owner
   edits outside the normal task workflow.

## Decision

Adopt candidate 2. `architecture-boundaries.json` defines purposes, allowed
dependencies, prohibited directions, stable interfaces, and deployment-profile
boundaries. `architecture-protected-paths.json` identifies changes requiring an
associated Proposed or Accepted ADR. The ADR must be indexed, task-linked, and
included in the same change set.

## Consequences

Architecture drift becomes deterministic and reviewable. Intentional changes
carry context, tradeoffs, compatibility, security, deployment-profile, migration,
rollback, and verification reasoning. The gate adds maintenance overhead and
requires path patterns to evolve as stable interface locations are introduced.
Local-first implementation remains authoritative; university/cloud implementation
stays release-gated. Reverting this policy requires a superseding ADR because the
policy file protects itself.

## Verification

- `python tools/architecture_check.py --repo .`
- `python tools/adr_check.py --repo .`
- `python tools/adr_check.py --repo . --base HEAD^ --head HEAD`
- Foundation tests for unindexed ADRs and uncovered protected changes.

## Task links

- `CAP-00.S02.T01` created the architecture map and dependency contract.
- `CAP-00.S02.T03` installs this ADR registry, scaffold, and enforcement gate.
