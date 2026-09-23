# CAP-04.S01.T03 publication-control-01 independent disposition

**APPROVED for the bounded hot-path, interruptible-publication and diagnostic increment.**
Reviewer: `w2_commit_increment_review`.
Candidate: `ddc3b980ef65c0c1ef26766fbc02f2a8462f596c`.
Base: `3d87c3545c6908512054c5cbdb08e0445a488d8d`.
Initial review candidate: `c136912f8d115d50cfc84a9d65d518431a301019`.
This is not task completion, 100k or performance-baseline qualification, native
release qualification, or permission to relax a deadline or release criterion.

## Findings and bounded correctness

No additional actionable, criterion-bound material blocker was found.
T03-TRANSPORT-02-F01 remains **CLOSED**; this increment does not restore the
incorrect claim that cancellation proves no canonical import was published.

The fixed SQL statements replace repeated compilation, not authority checks or
query results. Fresh project, aggregate, revision and record bindings remain
supplied on each execution; the aggregate projection order and insert values
remain equivalent. No new result cache or broad repository redesign is added.

The extracted same-connection heartbeat retains the existing exact live-lease
predicates, duration validation, progress validation and history writes. The
publication writer validates before renewing and at final acceptance; it cannot
revive an already expired lease. Source records, manifest membership/seal,
accepted output and provisional heartbeat updates remain in one atomic
transaction. This restores the existing renewable lease semantics without
widening the configured 30-second interval or introducing partial canonical
visibility. No conflict with ADR-0025 was identified in this bounded mechanism.

The active-publication registration is made under current commit authority and
binds the exact internal project binding, inputs and claim. Authenticated
cancel/close routes can issue a stop-only signal before waiting for the lifecycle
mutex. Cancellation matches the logical command; a replaced binding or different
command cannot signal that registration. This preserves existing authenticated
logical-job cancellation semantics, not a new promise to distinguish stale
clients lacking a caller session discriminator. Current commit/resume authority
and the stopped binding continue to fence the old worker.

The storage progress hook is scoped, exposes no raw connection and is removed
before transaction unwinding. A stop rolls publication back; the cancellation
path then revalidates and persists ordinary durable cancellation before further
admission, with bounded expired-lease recovery when rolled-back heartbeats no
longer sustain the durable lease. Close drains/fences work without inventing a
cancellation receipt. A drain timeout reports an unconfirmed outcome and directs
the caller to durable status. Existing native security-lock termination remains
unchanged; these cooperative controls do not authorize work through a lock.

The diagnostic exposes entry/exit/failure phase observations, rejects observed
automatic retries even if a later attempt succeeds, and reports commit-specific
durable facts rather than counting the parser receipt as an accepted commit.
These observations improve diagnosis; they do not themselves establish a scale
or latency pass. The successor's only product change from the initial candidate
splits a string literal while preserving its runtime text.

## Verification provenance

This independent review inspected the exact committed diff, relevant source and
regressions, governing contracts, evidence notes and prior finding. The reviewer
performed read-only inspection, did not rerun the suites or scale diagnostic,
and did not modify source, tests, contracts or the ledger. This disposition is
the sole authorized evidence-note write after review; it does not change HEAD.

Owner-reported checks at the initial candidate, with HEAD and selected inputs
fixed: 65 selected hot-path/publication/activity/service/concurrency/diagnostic/
shared-repository cases PASS in 78.241 seconds; five existing queue/storage
regressions PASS in 0.716 seconds; mypy on nine changed product modules and the
architecture check PASS. Ruff format passed on 13 changed Python files. The
initial Ruff E501 failure is preserved in `publication-control-01.md`, not
represented as a pass.

At the final candidate, the owner reported all-changed Ruff lint/format PASS and
the affected drain-timeout/truthful API case PASS in 3.465 seconds. The preceding
65 and five cases were not rerun or relabeled as fresh successor checks.

The owner additionally reported a protected Windows 1,000-record pilot at the
final candidate: functional scope PASS in 16.470 seconds, atomic writer 3.055
seconds, identity verification 3.131 seconds and staged pages 0.690 seconds;
exactly 1,000 source records, one manifest, 1,001 members, one seal and one
accepted commit; attempt 1 succeeded without retry, replay/reopen passed, and
HEAD/selected inputs remained unchanged. These are owner-reported measurements,
not an independently executed benchmark or a 100k result.

## Remaining qualification

Actual protected 100k success, ordinary interactive-read latency during the
writer, remaining native/principal and packaging checks, and later task,
slice/Wave qualification remain open. The earlier protected 100k failure and
diagnostic limitations in `scale-01.md` remain adverse evidence. This approval
does not replace any of those obligations or demand unrelated full-profile
reruns for this bounded increment.
