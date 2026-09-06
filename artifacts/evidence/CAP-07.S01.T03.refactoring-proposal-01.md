# CAP-07.S01.T03 — bounded refactoring decision

Status: **PROPOSED; no exception or implementation approved by this record.**
Candidate: `c8044e4371a6082cbb7cb402bd824aca770b7249`.
Evidence: [diagnostic observation](CAP-07.S01.T03.preflight-04.json), retaining
the earlier failed qualification and independent finding history.

## Current condition

CAP-07.S01.T03 remains incomplete: protected gateway overhead must meet
CAP-07.S01 section 11's unchanged p95 <25 ms criterion. The last qualifying
candidate passed 12/13 selected checks; performance failed. Instrumented runs
have not changed that disposition. G1/W1 passing is not currently approvable.

The next concrete optimization would reuse an exact, previously validated,
deeply immutable task snapshot during one routing invocation. The prototype
avoided seven of ten task decodes per invocation. It is not production-ready and
does not prove a qualified speedup. The independent preflight classifies the
generic-decoder lifecycle addition as supplemental refactoring, unlike a local
expression optimization inside the active task.

No foundational storage change is proposed. Two smaller expressions were also
inspected, but neither has an evidence-backed material saving. In particular,
replacing JSON normalization with a plain tree copy requires care because the
current decoder may accept scalar subclasses; normalization semantics must not
be lost merely to improve a timing result.

## W1 accounting, without assumed headroom

Read-only reconciliation by `agent:/root/refactoring_policy_preflight`
authenticated the original approval/baseline relationship and unchanged adopted
packet blobs. The baseline at
`594e63be501711d67d17a4aef176bb9b6a8748be` contains 48 atomic W1 tasks:
23 M x3 +25 L x5 = **P194**, giving a **29.1-point** ceiling.

| Recorded allocation | Points |
|---|---:|
| W1.A05.T01 authentication-provider refactor; exact historical exception | 5 |
| W1.A08.T01 styling consolidation | 5 |
| W1.A09.T01, W1.A09.T02, W1.A09.T03 | 3+3+5=11 |
| Named subtotal | 21 |

W1.A06/W1.A07 explicitly record zero. W1.A09's final 11 replaces its earlier
proposed 3, not W1.A08's separate 5. W1.A09 also identifies separate generic
entry/return maintenance forecast M3 outside that product allocation.

Total R remains unknown: W1.A01–W1.A03 have incomplete refactoring allocations,
W1.A02/W1.A03 lack complete task estimates, and historical bootstrap/recovery/
maintenance and spent/remaining overruns lack full reconciliation. **8.1 is
arithmetic, not proved available capacity.** The historical W1.A05.T01 exception
does not authorize this work or reset the Wave budget. No missing effort is
assumed zero, and none of these historical records is rewritten.

## Recommendation and alternatives

Recommend an explicit owner exception of **at most M3 points** for this one
supplemental implementation-and-verification increment despite unproved
historical headroom. Use the existing estimate basis, retain the original P194
and prior allocations, and charge the new allocation once. This is not a new
15% allowance, a reset, a general permission to refactor, or an assertion that
historical R was below its ceiling. Implementation plus remaining review/remedy
effort must stay inside the three-point forecast; report exhaustion before
expanding the work. Success is not promised by the prototype.

Exact permitted scope if approved:

- Private stdlib-only decode scope in the existing Python generator/template,
  activated only by the routing invocation; generated Python and focused tests.
- At most two retained returned snapshots, each at most 64,000 canonical bytes;
  identity comparison, not equality, hash-only lookup, or caller-object caching.
- Only provably deep-cacheable exact built-in primitives/keys and decoder-owned
  immutable containers qualify; other accepted inputs retain full validation.
- Active creator-thread ownership on lookup/insertion, bounded retention, nested
  scope isolation, and reference clearing/deactivation on every exit, including
  copied contexts, exception, cancellation and worker-thread cases.
- Unchanged task/result/schema acceptance, fresh result validation, permission,
  catalog, principal, history integrity, cost/deadline and persistence checks.
- Characterization/adversarial tests before product changes where practical;
  generated-contract checks, affected quality/security/integration tests, fresh
  committed-candidate performance evidence and independent disposition.

Expected paths: `packages/contracts/model-gateway/model-task.template.py.txt`,
its generated `services/core-api/src/research_observatory_core/model_gateway_contracts.py`,
`services/core-api/src/research_observatory_core/model_routing_contracts.py`,
the existing model-gateway/routing contract and protected integration tests,
and directly related task evidence/generated status views. No storage adapter,
public schema, TypeScript API, deployment or UX change is included.

Alternative: complete the historical cumulative accounting first and proceed
only if adequate capacity is proved. This avoids an exception but may require
substantial historical analysis unrelated to the feature. Deferring the
optimization is lawful but does not complete CAP-07.S01.T03. A performance-target
revision is a separate product/release-criterion amendment requiring its own
review and human approval; it is not included or recommended by this proposal.

## Decision and resume condition

The owner may approve or decline only the bounded M3 exception above. Record an
approval append-only with this exact proposal/candidate; never overwrite this
proposal or infer approval from diagnostics. No new product authority, ECR,
controller or Wave approval is asserted by this request. Follow any stricter
applicable authority route exposed during review before implementation.

Independent route preflight by `agent:/root/refactoring_policy_preflight`
confirmed that an explicit budget-only owner exception may use existing task
evidence without a new ECR, conditionally on these unchanged contracts. This is
not independent approval of an implementation or an owner exception.

After a recorded exception, or independently reviewed proof of sufficient
cumulative capacity, resume the existing owned CAP-07.S01.T03 task through
`python tools/taskctl.py --file planning/backlog.yaml reopen CAP-07.S01.T03
--agent codex --reason "<recorded decision/evidence reference>"` if BLOCKED,
perform task-start acceptance closure for the memo risks,
then implement and verify. The 25 ms target, task review, slice qualification,
full W1 qualification and separate human G1 approval remain required.

## Review links

- [W1 packet](../../planning/review-site/waves/W1.html)
  — `planning/review-site/waves/W1.html`.
- [CAP-07.S01 slice](../../planning/review-site/CAP-07/CAP-07.S01.html)
  — `planning/review-site/CAP-07/CAP-07.S01.html`.
- [CAP-07.S01.T03](../../planning/review-site/CAP-07/CAP-07.S01.T03.html)
  — `planning/review-site/CAP-07/CAP-07.S01.T03.html`.
- [CAP-07.S01.T01 contract prerequisite](../../planning/review-site/CAP-07/CAP-07.S01.T01.html)
  and [CAP-07.S01.T02 registry prerequisite](../../planning/review-site/CAP-07/CAP-07.S01.T02.html)
  are DONE; their public boundaries are not reopened by this proposal.
