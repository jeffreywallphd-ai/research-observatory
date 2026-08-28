---
id: ADR-0023
title: Use mode-specific researcher-controlled intent policy vocabulary
status: Accepted
date: 2026-08-28
deciders:
  - W1 repository-owner pre-Wave approval at 594e63be501711d67d17a4aef176bb9b6a8748be
linked_tasks:
  - CAP-03.S02.T01
  - CAP-03.S02.T03
decision_scope: Epistemic-mode requirements, use-case compatibility, evidence and scope vocabulary, autonomy bounds, egress declaration, stopping conditions, and human authority.
affected_paths:
  - packages/contracts/intent/**
  - services/core-api/src/research_observatory_core/research_intent_contracts.py
  - tests/contracts/test_research_intent_contracts.py
  - docs/architecture/research-intent-contracts.md
supersedes: []
superseded_by: null
---

# ADR-0023: Use mode-specific researcher-controlled intent policy vocabulary

## Context

Systematic evidence aggregation, theory synthesis, technical evaluation,
hermeneutic inquiry, critical problematization, novelty challenge, and empirical
study design do not share one defensible notion of completeness or stopping.
One free-form mode string would permit structurally valid but epistemically
incoherent intent. Conversely, one rigid empirical checklist would erase
legitimate interpretive and critical practice.

The Research Intent Contract must retain researcher-authored narrative while
providing enough typed policy vocabulary for later service-bound enforcement.
AI may propose alternatives or detect omissions, but may not accept intent,
silently change scope, adjudicate evidence, approve claims, or decide that the
research is complete.

## Candidates

1. Use one mode-independent checklist and one global stopping rule.
2. Store only free-form intent text and interpret policy at execution time.
3. Combine shared structured fields and researcher narrative with a
   discriminated requirement branch and stopping vocabulary for each mode.

## Decision

Adopt candidate 3. The portable contract carries one of seven explicit modes:
systematic, theory, technical, hermeneutic, critical, novelty, or empirical.
Each mode has a distinct requirement branch and a compatible primary-use-case
set. Shared fields preserve the research question, intended contribution,
phenomenon, unit and level of analysis, source scope, evidence types, novelty
standard, autonomy, stopping rule, egress policy, and unresolved decisions.

Required completion varies by mode. Accepted systematic, technical, novelty,
and empirical intent requires specified unit and level; theory, hermeneutic,
and critical work may mark either not applicable with rationale. Unknown,
not-applicable, and specified states remain distinct. Drafts may retain unknown
fields and unresolved decisions, but an accepted governing revision must be
decision-complete.

Stopping conditions are typed by mode: coverage or source exhaustion for
systematic work; saturation or researcher decision for theory, hermeneutic, and
critical work; benchmark completion for technical work; nearest-prior-work
challenge for novelty; and protocol completion or researcher decision for
empirical work. All stopping requires human confirmation.
Every declared stopping condition must belong to the selected mode's closed
condition set; `resource-budget` is the only cross-mode secondary condition and
cannot replace the mode's required completion or researcher-decision condition.

Autonomy is bounded to human-only, suggestion, reversible preparation, or
reversible execution. Allowed actions use a closed vocabulary and each action
is capped by the selected autonomy level. That vocabulary excludes intent
acceptance, scope mutation, and direct external-egress authority. The contract
always denies machine authority to accept intent or change scope and always
retains explicit human gates for both. Egress is declared as local-only with no
destination or egress gate, or as an approved mode with at least one opaque
approved destination identity and an explicit external-egress human gate;
enforcement remains T03 work.

## Consequences

T02 may render mode-specific defaults and comparison UI from this vocabulary,
but may not invent a new mode or silently translate an incompatible use case.
T03 must enforce the same terms at service boundaries, return explicit policy
reasons, and record the governing accepted revision. Later profile catalogs may
add guidance without weakening these durable authority constraints.

The schema retains narrative within bounded strings. Structured validation is
not evidence that a scholarly choice is correct; acceptance remains a human
decision.

## Verification

- Valid generated-contract cases for all seven mode branches;
- mode/requirements and mode/use-case mismatch denial;
- valid mode-sensitive not-applicable states and invalid systematic omission;
- source temporal ordering, evidence, novelty, and egress consistency;
- closed mode-specific stopping sets, required completion semantics, and
  mandatory human confirmation;
- bounded action vocabulary and autonomy-level compatibility;
- local-only and approved-egress gate/destination consistency; and
- denial of AI acceptance or autonomy that can accept intent/change scope.

## Task links

- `CAP-03.S02.T01`
- `CAP-03.S02.T03`
