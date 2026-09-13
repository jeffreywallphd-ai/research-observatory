# G1 — proposed limited prototype transition

Status: **PROPOSED, NOT APPROVED**. G1 remains PENDING; W2 has not started.
Prepared from `ea4db5d26d76fcaba037c6453cc55827a31d5045`, following the owner's
instruction to move forward with G1 preparation. This append-only exception
proposal does not edit the frozen W1 packet, change test results or grant authority.

## Decision and prerequisites

W1's 68 tasks are DONE and its 15 ordinary slices are independently APPROVED.
G0 is APPROVED. Eight amendments are ADOPTED; W1.A04 is a retired, unexecuted
SUPERSEDED reservation. W1 core completion is owner-accepted with qualification
gaps, **not** a completed independent full-Wave PASS. The
[owner acceptance](../artifacts/evidence/W1.owner-core-acceptance-01.md) remains
the authority for that distinction.

The normal G1 route requires fresh full-Wave qualification and independent Wave
approval. Those requirements have not been met. The proposed alternative is a
one-time, explicitly human-approved prototype-transition exception, supported by
the component evidence below and a separately scoped independent exception review.
Neither this proposal nor that review can silently substitute for the normal gate.
The safe writer must also be verified before asking for the release decision.

If approved, the exception would permit G1's local Windows x64 prototype
transition, despite the enumerated qualification gaps, clearing W2's upstream
activation gate. W2 planning is already permitted; its separate packet approval
and campaign start would still be required. This would not authorize W2 execution, public
distribution, trusted installation, ordinary-vault qualification, credential
handling, authentication-success claims, new external services or a general
security/performance waiver. No new implementation work or standing waiver
mechanism is proposed.

## Four unchanged G1 criteria

These are historical, source-bound component results, not new executions at the
current control commit. Each linked review retains its receipt, producer, source,
log and execution-candidate bindings. Later control/test/documentation changes
do not make prior executions fresh or establish exhaustive runtime equality.

| G1 criterion | Evidence and its limits |
|---|---|
| Signed-development Windows desktop shell starts and supervises the compatible local service. | [Signing](../artifacts/tmp/W1.signing-actual-review-05.json), [signed lifecycle](../artifacts/tmp/W1.production-lifecycle-review-05.json) and [supervision](../artifacts/tmp/W1.supervision-run-review-06.json): exact development-signed package; Ready/start/shutdown; 22 supervision, denial, cancellation, crash/restart and cleanup assertions. Build `ac1d3bd6`, lifecycle/supervision `5927fe7c`. Not root trust, public distribution or sign-in proof. |
| Projects persist safely in SQLite and encrypted local storage. | [Protected boundaries](../artifacts/tmp/W1.protected-boundaries-review-02.json), [supplemental integration](../artifacts/tmp/W1.supplemental-review-02.json) and [native lifecycle](../artifacts/tmp/W1.native-review-13.json): disposable DPAPI/SQLCipher projects, separate create/restart/crash/recovery processes, replay fencing, protected maintenance and observed close/reopen/restart. Execution `ac1d3bd6`; not testing ordinary research vaults. |
| Provenance, workflows, human gates, and stale-output propagation operate end to end. | Protected/supplemental reviews above plus [worker qualification](../artifacts/tmp/W1.worker-resource-review-05.json): dependent-output staleness with unrelated/history preservation, 32 workflow tests, native intent acceptance/reconciliation and 2,048-job admission/backpressure/safe-point cancellation. Worker execution `d2ae1c2b`; qualitative acceptance is not numeric efficiency/nonregression acceptance. |
| Project creation stores a versioned primary use case and the desktop renders its ordered workflow while preserving access to all tools. | [CAP-03.S06 integration](../artifacts/evidence/CAP-03.S06.integration.review-R01.json): fourteen profiles, version/authority, restart, support-return and all-tools access. Native13 above corroborates persisted Rapid field orientation through restart/reopen. Historical slice proof and attributed UI observations, not a fresh full UX matrix. |

Full execution identities: `ac1d3bd6b9bd3555c1f6e0dc89a8097fcd69a74a`,
`5927fe7c9fe90937a309f3f0468586d6af3ebce7`,
`d2ae1c2b7ab30cf86015b4734f63690512cb944a`.
The selected component-review hashes were authenticated against the
[exit-assembly anchors](../artifacts/tmp/W1.exit-assembly-draft-02.md); that old
draft's superseded progress statements are not current status.

## Explicit limitations to carry forward, not relabel PASS

1. **Incomplete full qualification.** The
   [partial collection review](../artifacts/tmp/W1.remaining-results-review-01.json)
   retains 14 earlier PASS groups and, separately, 22 completed groups (12 PASS,
   10 FAIL). Foundation unit was incomplete; a security skip is unidentified.
   Parent post-input comparison was skipped; its later comparison is separate
   evidence, not a backfilled receipt. No independent full-Wave PASS exists.
2. **Residual control/fixture failures.** Historical binding/fixture errors,
   Windows CLI cleanup, protected benchmark key setup and scanner failure remain
   unresolved within the matrix. [Bounded follow-up](W1-W2-control-followup.md)
   records 35 focused passes, import/privacy fixture corrections and two
   normal-identity Git checks, not a replacement matrix. The scanner's cause is
   unknown; no clean dependency/security claim is supported.
3. **Performance.** The latest gateway warm p95 is **28.3827 ms** against 25 ms,
   still FAIL. The earlier exact 26.5902 ms acceptance does not cover that later
   observation. This proposal expressly includes the later value for human
   disposition. Existing [Core acceptance](../artifacts/evidence/W1.core-performance-owner-acceptance-01.md)
   retains readiness +22.7527% and idle memory +22.8732% against a 20% regression
   allowance; absolute budgets passed. Causes remain unestablished. Worker
   numeric efficiency/nonregression and its proposed baseline remain unaccepted.
4. **Authentication and native focus.** Hello is owner-deferred NOT_EXECUTED;
   availability is not successful verification. Native13's automated first-Tab
   observation remains unresolved, without an established application or
   automation cause. The earlier physical-keyboard observation is not a new pass.

Carry these into mutable W2 initiation for risk-based selection, without
automatically creating a large remediation project or replaying completed
suites. Before depending on an unqualified boundary, select the relevant narrow
check/remedy in W2 planning. A new demonstrated security, privacy, data-integrity
or accessibility defect still stops its affected work; this exception cannot
excuse it. Public distribution and broader deployment need their own qualification.

## Recording readiness and decision sequence

The [bounded recording repair](../artifacts/evidence/G1.recording-maintenance-01.md)
preserves immutable authority and skips only a retired bootstrap payload read.
Its terminal and pre-append tamper checks pass. Repository-aware validation
returned no errors; an ignored-copy G1 approval persisted and a stale CAS was
rejected, with live backlog bytes unchanged and no protected witness read.
The [proof record](../artifacts/tmp/G1-persistence-check-01.json) binds candidate
`ea4db5d26d76fcaba037c6453cc55827a31d5045`; its digest and producer are in the
maintenance note. The [independent control review](../artifacts/evidence/G1.recording-review-R01.json)
approves that bounded repair; the separate exception-proposal review must bind
this packet's committed bytes before the human decision.
The read-only `taskctl next` reports status-based readiness; it is not itself
proof of full qualification or approval of this exception.

Recommended option: complete the independent final review, then approve the
one-time limited transition above. Alternative:
keep G1 pending and finish the normal full qualification route before any W2
activation; that takes more testing and does not follow the owner's current
prototype-first preference. Deferring the decision also leaves W1 core accepted
and G1/W2 pending.

After readiness and an explicit decision on the exact committed proposal,
append the owner's approval with its commit/hash, then use the existing writer:

```text
python tools/taskctl.py --file planning/backlog.yaml gate approve G1 --approver repository-owner --evidence <append-only-G1-decision-record> --note "Limited local prototype transition; exceptions and scope are bound in the decision record."
```

Regenerate the views after successful recording. Do not resume the completed W1
campaign or start W2 from this command alone. W2 requires rolling-wave initiation,
its complete revised packet and separate immutable approval before a campaign
can claim work. [W1 review page](review-site/waves/W1.html) and
[W2 provisional plan](review-site/waves/W2.html) remain navigational projections.
