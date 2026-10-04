---
id: ADR-0040
title: Document protected desktop activation correction
status: Proposed
date: 2026-10-04
deciders: []
linked_tasks:
  - W2.A04.T01
  - W2.A03.T02
decision_scope: Documentary association and exact source attribution for the owner-approved ECR-0012 paused-predecessor correction and later ECR-0011 desktop activation at its retained task base.
affected_paths:
  - tools/ui_change_gate.py
  - verification/extensions/desktop-ui.json
  - verification/baselines/desktop-ui.json
supersedes: []
superseded_by: null
---

# ADR-0040: Document protected desktop activation correction

## Context

Accepted ADR-0001 requires a changed, indexed, task-linked Proposed or Accepted
ADR in the actual protected-path change set. ECR-0011's frozen seven-source
W2.A03.T02 envelope omitted the documentary companion and index. ADR-0039
belongs to completed T01 and stays unchanged. The retained preflight denied
the extension and baseline before consumer edits.

The owner approved exact ECR-0012/W2.A04 packet candidate
`7f35c7a8e49eb8415ffdffa5a2e04374161f0eae`, SHA-256
`eb1cbf1b827bffdd5914f9255c6f0bba374621f916711b3e05815202d0312b8c`.
It binds the whole paused A03 record at `a211f241`, whose sole parent is the
retained T02 base `ca8b1448`. That commit saves claim, block and pause together;
no intermediate IN_PROGRESS claim was committed. The original W2 approval,
completed T01, approved Academic Minimal 1.8 package and accepted decisions
remain authoritative.

## Candidates

1. Shorten or widen the verification base, retroactively edit T01's ADR, or
   treat the absent committed claim as a generic exemption. These would conceal
   history or revise frozen scope. Reject.
2. Keep A03 paused and T02 blocked. This preserves authority but leaves the
   approved activation incomplete. Available if correction proof fails.
3. Deliver this single Proposed companion and one appended index entry in a
   separately reviewed five-source A04 task. Authenticate its full delivery and
   exact return sequence inside the retained T02 range. Select under ECR-0012.

## Decision

Preserve the closed v1.4 contract and its existing assertions. Derive only the
exact ECR-0012 correction from immutable packet/owner/independent review, B00,
materialization, activation, claim, source submissions and independent task
dispositions, integrated S01 review, exit review and separate security adoption
checkpoint. Authenticate the exact combined paused snapshot and complete DONE
T01 record. Every actual A04 source commit stays inside its five-source envelope
under its own active claim; every intermediate path and regular blob is checked.
This companion is introduced once with one new index entry; old registry entries,
metadata, accepted ADRs and ADR-0039 remain unchanged.

Adoption returns the complete frozen A03 record with T02 still BLOCKED. Later
separate supported A03 activation and T02 reopen must preserve T02's base,
definition/hash, criteria, owner, branch and worktree, with matching claim leases.
Only subsequent active T02 delivery may edit its original seven consumer sources.
Partition the independently reviewed A04 correction from T01 and T02 source
without removing any commit from the real base-to-candidate range. Reject absent
or substituted combined history, changed completed records, forged/stale/forked
authority, missing return, premature or foreign activation/reopen, extra source
or ADR/index changes, redirected/dirty inputs and hidden add/revert history.

This adds documentary association under ADR-0001 and exact approved-history
attribution under ADR-0003/0004. It supersedes no accepted decision, grants no
new security, migration, research I/O or release authority, and does not alter
the reference, witness, schema, controller, renderer, native/Core or runtime.

## Consequences

T02's actual retained task range now contains the separately reviewed companion
and registry entry. Its exact range must pass ADR association; a campaign base
cannot replace that task base. Old uncorrected v1.0-v1.4 histories keep their
original rules and denials. Original CAP-05.S01.T01 retains its full `6506c684`
base, two-contract inventory, independent current classification and complete
capture producer/dependent-input closure.

Missing or adverse proof denies continuation and stays in append-only history.
Rollback leaves A03/W2 paused and T02 blocked until a reviewed descendant
conforms. Do not rewrite approvals, move bases, erase failed evidence, weaken
tests or relabel a baseline. No university/cloud deployment is introduced.

## Verification

- Focused real-Git positives and substitutions cover the exact combined
  snapshot, correction ownership, five-source attribution, return and separate
  activation/reopen. Disposable future reviews and capture mocks prove control
  lineage only, with their limits stated.
- Validate this task's actual claim-base-to-candidate ADR association and a
  disposable future T02's actual `ca8b1448` range. Check one new Proposed entry,
  unchanged old registry metadata/entries and immutable prior ADR bytes.
- Run affected Python quality, canonical backlog/views/site and selected old
  UI authority regressions at a committed stable candidate. Obtain expanded
  independent control/security/ADR task review, integrated S01, exit and separate
  security adoption review before the correction returns its hold.
- Fresh T02 66-image capture, original native/Core/D3D acquisition, joined
  CAP-04.S05, full W2 qualification and human release remain later gates.

## Task links

- `W2.A04.T01` owns this companion, its one registry entry and the exact gate
  correction under independently reviewed ECR-0012.
- `W2.A03.T02` owns later protected extension/baseline activation in its original
  seven-source envelope after reviewed correction return and supported reopen.
