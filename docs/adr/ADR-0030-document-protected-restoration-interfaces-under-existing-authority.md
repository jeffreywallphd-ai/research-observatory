---
id: ADR-0030
title: Document protected restoration interfaces under existing authority
status: Proposed
date: 2026-09-26
deciders: []
linked_tasks:
  - CAP-04.S02.T03
  - CAP-00.S02.T03
decision_scope: Documentary association of protected restoration interfaces and their bounded maintenance delivery with existing ADR-0001, ADR-0003 and ADR-0027; this Proposed record grants no new authority.
affected_paths:
  - tools/ui_change_gate.py
  - packages/contracts/connectors/connector-page.schema.json
  - packages/contracts/core-api/connector-diagnostics.test.ts
  - packages/contracts/core-api/connector-diagnostics.ts
  - packages/contracts/core-api/generated.ts
  - packages/contracts/core-api/openapi.json
  - packages/contracts/package.json
supersedes: []
superseded_by: null
---

# ADR-0030: Document protected restoration interfaces under existing authority

## Context

W2.C02.T01 restores the already approved Source Manager operational visibility
from CAP-04.S02 sections 11–12. Its exact candidate adds optional bounded
measurements to a protected connector page and a read-only content-free
diagnostics projection. ADR-0027 already separates protected scholarly replay
from private authentication and ordinary diagnostics. The accepted original
task, Wave packet, reference, observations and approvals remain immutable.

The candidate's ADR range check exposed a procedural incompatibility: ADR-0001
requires a changed indexed record for protected interfaces, while the linked
correction and its separate maintenance adapter exclude all ADR delivery.
An unchanged existing ADR cannot satisfy that check. This companion provides
the required review association; it does not introduce architecture authority.

## Candidates

1. Omit the range check, widen its base, or treat an unchanged ADR as changed.
   These choices would lose exact association and are rejected.
2. Associate a new Proposed companion through the existing independently
   authenticated control-maintenance chain. Preserve all accepted decisions
   and enforce exact documentary scope and immutable delivery.
3. Change product architecture through a new accepted decision and human
   amendment. That route is required for an actual authority change, which
   this restoration does not propose.

## Decision

Apply the existing accepted decisions using candidate 2. ADR-0001 continues to
require a changed indexed record; ADR-0003 continues to require independent
restoration classification and authenticated captures. No ADR checker exemption
or general authority-document path allowance is introduced.

Within one independently reviewed bounded control-maintenance chain, the
adapter may admit one new Proposed ADR and its jointly introduced registry
entry. Every prior ADR and registry entry/order/metadata stays unchanged.
The new record has no decider, supersession or accepted status. Exact affected
paths must identify actual changed protected controls or the active correction's
admitted implementation, and the correction's original task must be linked.
Source/evidence/review ordering, complete hashes and regular-file/full-history
checks remain mandatory. Rewriting or reverting the companion later does not
inherit its old review. A Proposed record cannot authorize implementation that
conflicts with accepted architecture, approved scope or human decisions.

Under ADR-0027, the product restoration records actual transport entry counts,
retries, monotonic elapsed time and last status separately from scientific
identity. Historical pages omit absent measurements and retain exact old bytes;
same-invocation replay preserves the original observation. A new cache-only
invocation records zero transport attempts and unavailable transport latency.
Diagnostics reuse current project/session and original inspection rights, expose
no query, response payload or credentials, and never send a request. Strict
native/client admission and observation matching bound the read projection.
Completion estimates remain explicitly unavailable; selected request limits
do not promise an end-to-end deadline.

## Consequences

The change adds one exact documentary association and independent control
review, without relaxing protected-interface, UI or correction approval rules.
Old approvals and accepted ADR bytes remain usable at their original commits.
No database migration, credential delivery, rights grant, external telemetry,
new reference, hosted deployment or release decision results. Windows x64 is
the current qualification platform; other platforms retain their planned gates.

If qualification fails, keep the failed evidence and leave product submission
blocked. Roll back the control change through a separately reviewed revert;
preserve the companion and its history. Optional product measurements do not
require rewriting old protected pages, identifiers or scientific fingerprints.

## Verification

- Real-Git maintenance/correction tests reject changed prior decisions or index
  entries, unsupported state/authority fields, malformed/missing associations,
  unrelated/wildcard paths, rewritten/reverted history and mixed product scope.
- The actual task-base-to-candidate ADR range check must pass, alongside the
  unchanged registry, source-inventory and independent-review validators.
- Source measurement, denial/retry/cache/replay, historical-byte, protected
  Windows persistence/restart, strict typed/native and renderer race tests
  establish product behavior. Their candidate-bound evidence remains separate
  from this maintenance record.
- Current product/reference captures and independent UI classification, formal
  corrective disposition and fresh slice/Wave qualification remain required.

## Task links

- `CAP-04.S02.T03`
- `CAP-00.S02.T03`
