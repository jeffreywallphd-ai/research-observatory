# CAP-07.S01.T03 acceptance closure

Claim base: `5b283d3b26f3a7f6b8deb57e4ce0dfcf2be314d3`.
Authority: approved W1 packet at `c5bbd97c0cdc665eecb973f5862478ef7be97752`,
CAP-07 W1-binding decisions D01/D06–D08, CAP-07.S01 sections 2, 5, 7–13,
ADR-0021, and `docs/architecture/model-gateway-contracts.md`.

## Outcome and limits

Implement the Core-only policy/routing boundary over the completed task and
registry contracts: bounded attempts, explicit fallback, deadlines,
cancellation, circuit protection, and durable content-redacted decisions.
Original task identity and bytes remain immutable. A candidate list is never a
dispatch permit. Reauthorize each attempt, including retry and fallback.

W1 does not install weights, call a live provider, acquire credentials, implement
remote payload consent, or add a model runtime. Those remain W3 work. Existing
production inventory stays empty. No UI or experience-reference change is
planned; feature-specific execution disclosures are downstream consumers of the
typed result and audit contracts, not a new synthetic execution button.

## Material acceptance map

| Boundary | Intended invariant | Proof |
|---|---|---|
| Task and input authority | Deep-owned T01 task; explicit input references exactly match the task; identity/hash substitution or same-ID changed request cannot dispatch. | Contract negatives and replay/conflict tests. |
| Current permission | Project, canonical input identity, current privacy, model-use rights, source classification and budget are separate conjuncts. Missing authority denies. | Real protected project/repository/privacy denial; synthetic complete authority for positive cases. |
| Route and fallback | Fresh exact catalog/manifest/runtime facts and policy before every attempt; pinned execution never substitutes; preferences cannot bypass eligibility or egress. | Deterministic local/remote, stale, changed-policy, pinned and resource/cost matrix. |
| Attempts and outputs | Retry only classified transient failures, within a finite shared attempt/deadline/cost budget; output must pass T01 validation and exact route/policy binding. | Transient/nonretryable/malformed/mismatched output fixtures; no invalid or partial output promoted. |
| Cancellation and timeout | Propagate promptly; do not await an unresponsive adapter indefinitely or accept a late completion; preserve the request. | Deterministic cancellation/deadline/late-result fixtures and measured acknowledgement. |
| Audit, concurrency and restart | Persist admitted request, alternatives, attempts and terminal outcome with integrity, compare-and-swap and atomic provenance/outbox; never silently replay an ambiguous in-flight attempt. | Real SQLCipher restart, corruption, collision, atomicity and concurrent-admission tests. |
| Circuit breaker | Bounded failure threshold/cooldown with attributable state; no pinned substitution and no stale half-open authority after interruption. | Failure/open/reset/restart fixtures, including competing attempts. |
| Integration | Only Core composition supplies actor, policy, catalog, adapters and persistence; no caller permission flags or provider SDK types. | Composition/principal denial, portable adapter conformance, affected architecture and generated-contract checks. |
| Performance | Gateway overhead p95 under 25 ms excluding model execution; cancellation acknowledgement under 100 ms. | Named isolated fixture benchmark with measured scope; no live-model throughput claim. |

## Preflight incorporated

Read-only independent boundary inspection by
`agent:/root/registry_persistence_preflight` found:

- Domain rights include model-specific allowed/denied uses, but current aggregate
  and object persistence expose only coarse `rights_status`. That coarse status
  and privacy's local-read allowance do not grant model use.
- Provenance's default `private-research` label is not an authoritative mapping
  to the task's four source-classification levels.
- Current project settings provide versioned privacy, not a numerical model
  budget or model-preference authority. A caller's requested limits cannot grant
  spending or egress authority.

The production policy adapter will therefore perform real canonical identity
and privacy checks and explicitly deny the missing rights/classification/budget
facts. Positive routing fixtures will inject complete, task-bound authority;
they will not be described as production authorization. This is the existing
fail-closed contract, not permission to invent missing upstream records.

## First checks and deferred coverage

Add router success, fallback-denial, immutable-request, pinned, cancellation and
restart regressions before implementing their paths. Qualify the exact committed
candidate with affected AI, service/persistence, security, contracts, quality,
architecture and inventory checks. Expand only for demonstrated shared-path
impact. Full profiles, native Windows, packaging and cross-capability fresh
qualification remain at slice/checkpoint/W1 exit as required. The previously
disclosed unrelated `selective_recalculation.py` typecheck failure remains an
explicit W1 full-quality obligation, not a waived check.

No new human gate discovered by this pass. Independent expanded security review
is required before task completion and integration.

## Bounded maintenance: async port execution lint

At claim base `5b283d3b26f3a7f6b8deb57e4ce0dfcf2be314d3`, architecture-check
blob `6140bd9372a67bebfb1e3f965b763f2518c5ffa1` classifies every attribute call
named `execute` as SQL. The approved `ModelAdapter.execute` contract reproduces
that false positive. A focused failing regression precedes the correction.

The intended delta recognizes awaited calls on an unmodified parameter explicitly
typed by an imported repository async Protocol. It does not grant runtime
authority or exempt database imports, concrete adapters, untyped/reassigned
receivers, synchronous SQL, or other database methods. Generic positive/negative
fixtures and all prior architecture tests must pass. This is bounded
evidence-control maintenance inside the task's expanded independent review,
not an architectural permission change or a new controller.

## Integrated findings and implementation refinements

- Recovery preflight confirmed the existing workflow queue owns execution fencing.
  This task adds only exact-principal/revision terminal journal recovery, with
  uncertain prior execution retained and no automatic redispatch.
- Protected integration initially measured about 110 ms p95, above the slice's
  25 ms target. Request-scoped fully verified connection reuse, indexed exact
  namespace reads, single-serialization hashing and synchronous atomic groups
  reduced this substantially; the performance assertion remains open until it
  actually passes. Neither durability nor encryption settings were reduced.
- Profiling also found redundant traversal of already-invalid generated Python
  schema branches. The source template now short-circuits conclusive structural
  failures. The schema and semantic acceptance rules are unchanged; differential
  JSON Schema checks, all prior decoder tests and generated-byte checks cover
  the affected public-contract implementation before independent review.
- The review site was stale although the backlog was current. The tracking guide
  and planning entry now conditionally require HTML regeneration after visible
  task/review/worksheet changes; Markdown regeneration alone is insufficient.
  The two-file guidance delta received read-only approval in principle, with
  exact-commit disposition still required before integration.
- Architecture exception preflight found receiver rebinding, annotation shadowing
  and a fake `Protocol` base could hide SQL calls. Focused regressions reproduced
  these failures; the correction conservatively revokes exemptions for ambiguous
  bindings and verifies the base's unshadowed `typing.Protocol` import. These
  adverse findings remain part of the task's independent-review replay.
- Further profiling isolated repeated pure task validation. Schema-proved
  discriminated-union selection and one bounded exact-text invocation memo
  retain all schema/semantic acceptance rules; no policy or history is cached.
  Memo scope exit clears inherited contexts. Admission, alternatives and first
  attempt now commit atomically before any adapter call; injected failure proves
  complete rollback and safe retry of the unchanged request.
- A late-cancellation regression exposed premature circuit release while a
  non-cooperative adapter remained active. Cancellation still returns promptly,
  but uncertain execution retains its reservation for supervised recovery.
  Raw session-open/transaction-control storage failures are also normalized;
  protected fault injection proves rollback and a usable subsequent transaction.
- Benchmark sampling was expanded from 20 to 100 retained warm observations
  plus a separately reported cold call, using nearest-rank p50/p95 with no slow
  sample trimming. The 25 ms bound and inclusion of protected I/O are unchanged.
  Exploratory results around 22 ms p50 / 28 ms p95 remain failures, not qualifying
  evidence. The isolated benchmark includes synthetic adapter construction and
  dispatch but not production lifecycle-factory overhead or live inference.
- Reuse of validated journal bytes is restricted to a single `BEGIN IMMEDIATE`
  transaction. Commit/rollback clears the memo; tests require fresh persisted
  history reads and detect intervening corruption in the next transaction.
- Independent phase profiling attributed the remaining tail primarily to
  protected open/commit/close variance, not a demonstrated routing CPU defect.
  Its one diagnostic run measured 21.196 ms p50 / 23.936 ms p95, with all 100 warm
  samples retained; this is advisory, not qualification. Fresh committed-candidate
  measurement and independent disposition remain required. Reference host:
  Windows AMD64, Intel Core i5-14600KF, Python 3.14.6, protected SQLCipher fixtures
  with explicitly injected in-memory keys and no ordinary vault access.
- The same preflight found a cross-thread memo cleanup/refill race. Restricting
  memo hits and writes to the creating thread prevents inherited worker contexts
  from sharing or reviving it; focused thread/scope-exit regressions cover this.

## First candidate adverse review and missed acceptance rows

Candidate `eda91ee61d035dc72bc8808bfeaa829b0b27bc35` passed its 13 selected
checks, but independent pre-submission review identified three P2 defects.
`CAP-07.S01.T03.preflight-01.json` preserves the findings; no formal submission
round or approval is inferred. The original fresh-check logs remain local.

| Finding / immediate cause | Added acceptance row and regression |
|---|---|
| F01: the outer async timeout could not preempt synchronous authorization/description work. | Advance only the gateway clock during authorization; no dispatch after the effective deadline. Recheck again before output publication. |
| F02: registry permission checked one attempt while the router accumulated only its own restriction. | Persist the effective permission/policy intersection per attempt; retain total reservations across retry/fallback; reject cap shrinkage before dispatch, output and successful replay, and reject forged historical cumulative cost. Null permission caps never waive routing limits. |
| F03: lexical binding inventory omitted Python generic parameters. | TypeVar, ParamSpec and TypeVarTuple function/class fixtures revoke the async Protocol exemption when shadowed. |

Five focused tests failed before source changes (eight failures including generic
parameter subcases), reproducing all three findings. Remediation remains inside
the approved budget, deadline and architecture boundaries. T02 catalogs remain
unchanged; eligibility is ephemeral, and T03 journal candidates are unreleased.
Old incomplete T03 attempt-authority records fail closed, never gain a default
budget. No migration or production grant is introduced.

The first candidate's fresh protected fixture measured cold 19.296 ms, warm p50
21.227 ms and p95 23.913 ms (100 retained warm observations). Its log retained
aggregate metrics only, so it is not a reusable raw-sample baseline. The successor
benchmark emits every cold/warm sample and runtime/platform metadata into the
captured local log. It remains a fresh-only, isolated fixture measurement with
the same 25 ms target and disclosed production/native/package exclusions.

The second candidate, `6da0dea6b8b28ba24e4d07af921a4af475d7365a`, closed F01–F03
in independent replay (18 tests) but failed fresh performance: p95 25.789 ms,
with 8 of 100 warm samples at or above 25 ms. The other 12 selected checks passed.
`CAP-07.S01.T03.preflight-02.json` retains the exact check records, raw samples,
hardware and adverse disposition. No baseline or task approval was established.

A bounded independent decoder-only prototype saved 75.5 microseconds (14.67%)
per task/result pair and matched 845 exact error-list comparisons. This is a CPU
diagnostic, not gateway qualification. One protected-call profile also showed
816 schema-node visits across 10 task decodes and 3 result decodes. The small
successor removes per-node singleton-list/generator allocation and checks array
keywords only when present, preserving even untyped array constraints. Its guard
is more conservative than the prototype's schema-type guard; the prototype's
timing is not claimed for the final implementation. Public schema and TypeScript
bytes remain unchanged. A new 143-case schema-applicability characterization test
joins the existing differential and all-task-kind checks; fresh committed-candidate
measurement and independent review are still required, without target changes.

## Supplemental-refactoring decision after policy update

The successor's qualification still failed the unchanged 25 ms p95 target;
12/13 selected checks passed. [Preflight 04](CAP-07.S01.T03.preflight-04.json)
retains five subsequent diagnostics, not qualifying reruns. Protected open and
commit variance remains; normal authorized host execution did not remove it.
A single-thread prototype reused seven of ten task decodes, without establishing
a qualified speedup or production-safe cacheability.

Independent preflight identified scalar/key subclasses that can survive current
decoding. A proposed invocation-local identity memo must separately prove deep
cacheability, bounded retention and scope/thread cleanup while preserving full
validation for other accepted inputs. No authority, history, result, storage or
deadline check may be reused or removed. No memo or storage change was implemented.

Adding lifecycle state to the completed generic decoder has a supplemental
refactoring portion. W1's original estimate is 194 points, its ceiling 29.1,
and named historical allocations total 21; missing older accounting makes total
consumption and headroom unknown. The next Wave's approval resets its own budget,
not this active Wave's. The [bounded M3 proposal](CAP-07.S01.T03.refactoring-proposal-01.md)
requests an explicit owner exception or independently reviewed proof of capacity
before this optimization. It does not request W1 passing or change the target.

The owner subsequently approved the exact M3 exception in
[decision 01](CAP-07.S01.T03.refactoring-decision-01.json). The single inclusive
three-point allocation covers this diagnostic/preflight, implementation,
verification, review and remediation; historical total R stays unknown.

Additional acceptance rows before implementation:

| Memo boundary | Required proof |
|---|---|
| Reuse identity | Only a returned validated snapshot can hit by `is`; original mutable dictionaries, equal externally backed proxies and changed input must revalidate. |
| Deep immutability | Exact built-in scalar/key types and decoder-owned proxy/tuple trees only; accepted subclasses retain uncached public behavior. |
| Retention | At most two strong references, each <=64,000 bytes under the existing canonical JSON encoding; oversized and third snapshots remain valid but uncached. |
| Lifetime | Nested scopes isolate; success, exception and cancellation deactivate/clear references; copied contexts and foreign threads cannot hit or refill an expired/foreign scope. |
| Authority/result freshness | Existing permission revocation, history tampering, changed output, cost and deadline tests still reject with task reuse active. |
| Performance and compatibility | Exact schema/TypeScript bytes unchanged; fresh affected Python, generated-contract, quality and protected integration checks plus the unchanged benchmark and independent review. |

Canonical-size eligibility will be measured without importing registry/routing
back into the generic decoder. No arbitrary input is rejected merely because it
is not eligible for reuse. The prior pure exact-text routing memo remains
separate from permission/history and retains its existing lifetime bounds.
