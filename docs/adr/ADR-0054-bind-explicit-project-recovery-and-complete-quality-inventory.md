---
id: ADR-0054
title: Bind explicit project recovery and complete quality inventory
status: Proposed
date: 2026-10-11
deciders: []
linked_tasks:
  - W2.A06.T01
  - W2.A06.T02
  - W2.A06.T03
decision_scope: Explicit reviewed local repair-copy recovery, Native-owned durable operational session identity, and complete quality inventory data. No shared boundary/checker policy change.
affected_paths:
  - services/core-api/src/research_observatory_core/ports/project_recovery.py
  - packages/contracts/core-api/**
  - packages/contracts/project/**
  - quality-scope.json
supersedes: []
superseded_by: null
---

# ADR-0054: Bind explicit project recovery and complete quality inventory

## Context

CAP-02.S01 requires explicit reviewed stale-lock recovery. Retained whole-process termination exposed the unimplemented recovery path. ADR-0008 keeps Native process/host authority; ADR-0012 preserves portable projects; ADR-0001 requires a task-linked indexed record for protected API/port/quality data changes. W2 restoration of W1 behavior is explicitly authorized. Original adverse evidence and task history stay immutable.

## Candidates

1. Restore reviewed recovery with a verified working copy and a durable typed operational ownership witness; synchronize all governed quality data and retain every checker. Recommended.
2. Limit action to separately reviewed original-fixture operator recovery and defer the product feature. This does not satisfy whole Desktop/Core production recovery and must not reduce Wave criteria silently.

## Decision

Proposed under ECR-0014/W2.A06, not yet accepted: Native owns actual current principal, same-machine and parent/child process birth/executable/session authority and provides a typed controlled startup binding. Core owns preview/confirm/cancel/status, heartbeat and verified copy via a typed port. Renderer evidence never grants host authority. Persist a dedicated private nonportable witness with inner current-user DPAPI and outer same-machine DPAPI, containing no project key, vault root or research content. Existing project-key/current-user protections remain unchanged. New sessions publish a recoverable lock only after durable witness publication; failures never grant eligibility. Unknown/living/reused process, foreign host/user, absent/tampered proof, changed source/heartbeat, redirect/hard link, key/integrity/collision/concurrency failure denies. Ten-second heartbeat is metadata, never a stale-age takeover permission.

Explicit human preview/confirm creates only a verified empty-destination working copy; original project, old lock and old ciphertexts remain untouched. Verify database/WAL consistency, object authentication/inventory, IDs/revisions and accepted facts before atomic publication. Normal explicit open acquires new operational authority on the copy. No automatic unlink/takeover/reparse/acceptance or arbitrary legacy override. Existing approved Projects recovery/lifecycle region and focus/dialog patterns are restored, not redesigned. Old unproven R03 cannot receive a backfilled witness; any separately authorized one-use operator attempt requires exact preserved proof and independent closure.

quality-scope.json must cover complete actual governed discovery under unchanged six roots/exclusions, preserving every valid entry and adding omissions/new sources. No checker, formatter, architecture-protected-path or release-gate source changes. Exact verification-method choices are separately bound in the ECR proposal and retain original FAILs.

## Consequences

Windows x64 local-only operational proof survives complete Native/Core death for newly eligible sessions. It is not portable host authority or protection against administrator/OS/credential compromise. No project/vault format migration or new scholarly-object encryption. Legacy unknown sessions are denied truthfully. Each linked task updates only its own implementation/verification notes in this same indexed record; no fabricated Accepted state or generalized policy change.

## Verification

Required actual owned whole Native/Core termination and fresh startup, protected readback, real principal/foreign-host/PID reuse/unknown query/tamper/path/key/copy/audit/cancel/race denials. Existing reference UI keyboard/focus/theme/reflow proof and exact source/task/review hashes. Complete quality discovery/check; originals retain truthful outcomes, with only explicit ECR finite methods. Existing ADR check against each actual task base/candidate. No results exist in this Proposed record.

## Task links

- W2.A06.T01: security/port/API/witness/copy implementation and actual security evidence.
- W2.A06.T02: existing Projects state/action/focus restoration and shipping integration evidence.
- W2.A06.T03: complete quality data and exact finite verification qualification.

## W2.A06.T01 implementation in progress

The original ECR-0014 contract above remains Proposed. The exact owner-approved
single-adapter addendum is recorded in
`artifacts/evidence/W2.A06.T01.object-inventory-scope-addendum-01.owner-decision.json`.
Its additional existing `object_store.py` entrypoint verifies only a privately
owned recovery staging copy through complete canonical facts, current object
metadata and physical inventory, retained rights/key authority, bounded existing
authenticated streams and cancellation. It does not repair or open the original
project, extend the public ObjectStore port, change scholarly encryption, or
replace existing canonical connection controls.

The additive `NativeRecoveryContractTests` drives the actual compiled Native
supervisor and protected Core in two separately owned Windows Jobs. It binds
current build inputs and holds source/executable files against write/delete,
abruptly terminates the original whole pair, verifies an original-derived copy,
then obtains fresh ordinary open and protected lineage/intent/object readback.
It grants no shipping UI or frontend predicate exemption. The original general
probe builder and its desktop assertions remain; its zero-test setup failure is
preserved. Shipping Native/Core/UI recovery belongs to W2.A06.T02.

Current observations remain development evidence from uncommitted source.
An isolated anonymous-thread check proves private witness ACL and inner
current-user DPAPI denial followed by owner readback after reversion; it does
not claim a different Windows login or foreign host. Foreign-machine wrapper
proof and exact committed-candidate review remain outstanding. No task, slice,
Wave, release, or accepted ADR status is inferred from these observations.

Independent development review identified terminal-preview admission exhaustion
and a gap between staged authentication and publication. Regression cases retain
the original failures. Terminal entries may be reclaimed only after validation
and any worker finish; pending validation, active copies and unopened verified
targets retain their authority bindings. Staged database, committed WAL and
portable content receive strict file holds before verification. Only SQLite's
derived shared-memory index, a newly created empty WAL, and the exact owned
audit append may change. Windows directory publication requires closing child
handles, so complete content/identity binding is compared again under fresh
strict destination holds before ready/open authority. Changed published content
is quarantined by the operation-owned root identity. These are implementation
details within the approved criteria, not a new verification exemption.

The 64-entry limit bounds active preview/copy sessions. Completed terminal
entries may be reclaimed; ready previews remain until cancellation or Core
restart. This limit grants no expired or discarded preview confirmation.
Each owned staging copy receives a flushed temporary root completion marker
before copying. Ordinary package validation rejects this extra entry, so failed
quarantine and interrupted publication remain denied across a fresh Core
startup. Complete published bytes stay held through final marker removal;
removal failure retains an incomplete copy and cannot report ready. Successful
copies retain the existing project format without the temporary marker.

The owner confirmed no second Windows PC or VM is available. The original
foreign-host criterion remains unverified and unchanged; local checks cannot
claim its completion. A separate verification decision is required before this
hardware-dependent gate can be deferred.

### Approved local proof corrections

The two exact owner-approved corrections are published at
`ca4ec3f658e1bffe810d9aa8c590ad5ac290ed7c`, with immutable decision,
supplement and actual introduction records under
`artifacts/evidence/W2.A06.T01.local-verification-corrections-01.*`.
The physical second-Windows-installation witness denial is explicitly untested;
the approved timing supplement carries it to the first available independent
Windows installation and requires it by W5 exit. All local security obligations,
both DPAPI scopes and subsequent independent/release gates remain required.
The separate single-test scope supplement permits only the reviewed two-line
cancellation keyword forwarding correction in `test_local_object_store.py`;
its assertions and timing bounds are unchanged. Original failures remain.

The due-now acceptance review identified three missing explicit negative cases:
an actual reversed DPAPI artifact against fixed trusted issuance order, an
actual OS-denied process query under an anonymous thread principal, and a
separate same-host Native/Core instance attempting to close the live owner's
project. Focused characterization tests close those evidence gaps within the
existing T01 source envelope. Their actual committed results and independent
disposition remain pending; this note grants no Accepted ADR or task status.

The actual anonymous-principal process-query characterization initially failed:
Windows supplied a complete restricted snapshot that omitted the still-live
owner, and Native reported `dead`. The owned query now corroborates absent PID
enumeration with `OpenProcess` invalid-parameter absence before returning
`dead`; an actual access denial remains `unknown`. The original failure and
focused successor are retained. This restores conservative owner-query denial
inside the approved Native scope, without granting new authority.

The combined whole-pair successor then exposed a retained-handle case:
`OpenProcess` can still open a terminated process object, and the conservative
query denied recovery with `owner-death-unproven`. That adverse result remains
preserved. Native now requests process synchronization alongside limited query
access and uses a zero-time OS process wait: a signaled object proves termination,
a timeout preserves the existing process-birth and executable checks, and any
other wait result remains `unknown`. Access denial still remains `unknown`.
These bounded local checks are development evidence; committed qualification,
task review and later Wave gates remain pending.

A further criterion-linked review found that signaled termination alone skipped
the trusted process-birth comparison. The actual retained Native test-process
characterization reproduced `dead` for a mismatched creation time; its failed
run and earlier test-fixture setup errors are retained separately. The signaled
branch now reads the OS creation FILETIME from the opened process handle before
classifying the owner: matching birth permits `dead`, mismatched birth returns
`pid-reused`, and unavailable birth remains `unknown`. The actual retained-handle
case and other selected Native recovery cases pass in development; fresh final
candidate proof and independent task disposition are still required.

### W2.A06.T02 recovery controls

The Projects workspace now provides an explicit recovery review using the
existing native directory picker and the exact Core recovery projection.
Confirmation creates only the verified working copy; opening uses the normal
project API after a separate human action. The retained source, destination and
preview identity stay bound while status advances. Unavailable or malformed
responses cannot grant confirmation, opening, success or cancellation.

The native modal starts at Cancel, supports local dismissal even when Core is
unavailable, and restores focus to an enabled action or the recovery status.
Dismissal does not claim that Core cancelled the operation. Polling announces
only material changes. A lost open response requires explicit status readback;
if Core reports the copy opened without confirmed project details, the user can
explicitly close that exact copy through the existing project API to obtain a
genuine closed projection. Opening is never replayed automatically.

These are implementation notes within the approved T02 envelope. Development
unit/type checks are not shipping desktop, task, slice or Wave qualification.
Fresh actual Native/Core/UI, keyboard, failure, cancellation, protected-readback
and restart evidence plus independent review remain required.

The actual shipping check at `8f26edfbcfcbde64a5df18deffb184f51bd1c2e2`
found that Tab after the last recovery button could leave the dialog. That
failure is retained. Recovery now uses the existing Task Center dialog pattern
to wrap forward and reverse Tab between enabled dialog controls. Fresh shipping
keyboard verification at the corrected committed candidate remains required.

### W2.A06.T03 complete quality inventory

The claimed T03 data update preserves all 584 valid declared Python paths and
adds the 146 omissions found by complete filesystem discovery across the six
unchanged governed roots. Discovery excludes only node_modules and linked
directories, as the existing quality governor does; it is not limited to tracked
files. The observed complete set has 730 paths and no stale or untracked Python
entries. Exact fresh set equality, formatting, lint and types remain required;
this observation is not a permanent expected count or a quality PASS.

Original architecture, desktop lint, security and quality checkers remain
unchanged. The owner-approved finite 45 AST plus three literal method, exact
Reader CSP method and one unchanged formatter-debt disposition require actual
independent source/control readiness and fresh final-candidate evidence.
Missing, changed, duplicate or additional findings remain blocking. Original
failures and approval records stay preserved; no shared checker exemption,
accepted ADR state, task completion or Wave release is inferred here.


#### W2.A06.T03 TY01 typed fixture repair

The exact owner-approved TY01 supplement appends only necessary test typing
repairs, one annotation-only anchor schema generator and four empty test package
markers to this task's source envelope. The original ECR, packet, approval and
criteria remain immutable. The one-use recording exception binds the actual
decision, reviewed source hashes and later introduction provenance; it grants
no shared framework implementation or additional verification exemption.

The repair retains every original test assertion and invalid-input
rejection, uses faithful service/port doubles that reject unexpected calls,
and adds required-present narrowing and actual fixture/container declarations.
The schema generator's model choices and the PDF fixture's authored byte logic
remain unchanged. The inventory preserves all730 valid entries and adds only
the four actual empty markers;734 is an observation, never a count-only gate.
The initially prepared fifth marker was removed before commit when diagnosis
showed that it changed the existing Foundation discovery namespace. The original
Foundation namespace and all its other tests remain unchanged; only the approved
taskctl test receives its necessary import correction. Diagnostic-driven
follow-on repairs remain within the exact existing-test upper bound in TY01.

Complete fresh unchanged quality, byte-sensitive outputs, affected existing
tests and actual independent committed source/security/reference review are
required. Every newly exposed error still blocks. The original196-error FAIL,
the separate prelaunch transport failure and exact formatter debt stay retained.
Fresh final integrated build/CSP/recovery evidence and all task/amendment/Wave
reviews and release decisions remain due; no PASS is asserted by this note.
