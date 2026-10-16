# W3 plan — Windows local evidence workbench

**Proposed planning only.** W2 and G2 completed at
`1cc8131d8b74cf6c536d48ce4badc25933981bbb`, with the owner's accepted initial
scope and disclosed limitations. See the [exit decision](../../artifacts/evidence/W2.exit-decision-20261016-01.md),
[normal recording receipt](../../artifacts/evidence/W2.initial-exit-recording-receipt-20261016-01.json),
[independent Wave disposition](../../artifacts/evidence/W2.initial-exit-independent-wave-disposition-20261016-01.json)
and [qualification summary](../../artifacts/evidence/W2.initial-exit-qualification-20261016-01.json).
These records do not claim every product proof passed. W3 implementation has not
been authorized; its complete Wave approval remains PENDING.

W3 gives researchers an offline, account-optional local workbench to search and
screen lawful sources, run explicitly admitted local models, extract grounded
candidates, independently inspect and verify evidence, adjudicate disagreements,
and export with source anchors, rights, uncertainty and human decisions intact.
An optional remote provider stays off until explicit policy and egress approval.

## Ordered work and estimates

The packet contains48 existing task IDs in16 slices. Estimates total **924
engineering-effort hours**, including **28 planned refactoring hours once**;
these are forecasts, not measured effort or calendar dates.

| Capability | Ordered W3 slices | Hours | Refactoring included |
|---|---|---:|---:|
| CAP-06 — search and screening | S01 lexical56 → S02 vectors64 → S03 hybrid48 → S04 Search Studio64 → S05 Corpus Canvas52 → S06 screening56 |340|4|
| CAP-07 — governed AI | S04 prompt/schema48 → S02 local runtime78 → S05 evaluation/operations54 → S03 optional remote60 |240|12|
| CAP-08 — extraction and evidence | S01 ontology52 → S03 evidence/status60 → S02 extraction60 → S04 verification56 → S05 matrix64 → S06 comparison/export52 |344|12|

The [task register](task-register-01.json), [slice-gate witness](ordered-slice-feasibility-witness-05.json)
and [shared contracts](contracts-01.md) define the exact dependency DAG and proof
ownership. Each later slice also waits for the preceding slice's independent
completion. Registry/schema qualification does not pretend to execute inference;
real runtime, prompt and evaluation integration remains in the runtime/evaluation
slices. Source-first return, missingness, adjudication and reversible bulk preview
remain part of the affected journeys.

## Resource and evidence boundaries

The [resource policy](aggregate-resource-and-selection-policy-02.json) proposes
whole-application2048MiB preferred and explicit3072MiB upper budgets, per-role
tiny/small choices, and one active model job. Protected parsing and model work
reuse the existing serial admission controller. A4096MiB private-commit ceiling
is an existing enforcement limit, not measured RAM use or a demonstrated fit.
Only actually installed, authenticated, role-qualified models may enter automatic
selection. Unknown, denied, unavailable-resource and remote-off states stay visible.
No model fit, quality, human annotation, licensing or benchmark result is invented.
Large-compute product work remains W5; no8GiB/16GiB model workload runs here.

The [target register](initial-target-register-01.json) distinguishes suggested
soft median latency targets from hard functional, security, rights, quality,
memory, method-deadline and cancellation/drain obligations. Under the
[post-W2 direction](../../artifacts/evidence/W2.post-exit-roadmap-direction-20261016-01.md),
a completed comparable-trial median overage strictly below7seconds against a
suggested target may be accepted with W10 optimization debt. Exactly7seconds or
more needs assessment in the unapproved/current Wave. Retain every raw outcome;
failed/timed-out trials remain failures, and assertions are not changed to pass.
Minor nonfunctional cosmetics go to W10. Functional defects and expiring security
authority are not cosmetic debt.

## Decisions and experience

The selected policy fixes extraction token/matching units, nonvacuous metrics,
support/refute recall and answered coverage, and preserves human promotion and
adjudication authority. See [gold/annotation strategy](gold-source-and-annotation-strategy-02.json)
and [decision summary](decision-summary-01.md). Existing W1 decisions remain
inherited; future work is not authorized by those approvals.

Three architecture proposals remain **Proposed**: ADR-0056 model-purpose authority
and isolated local execution; ADR-0057 protected rebuildable lexical/vector
projections; ADR-0058 scoped evaluation attestations and honest local-coder
authority. Their materialization does not accept them. Proposed reference1.10
contains the complete affected seven-page experience and supporting contracts;
active reference1.9 remains unchanged. The14 workflow IDs, catalog1.5 and existing
tokens are retained. Required architecture/design acceptance and complete Wave
approval remain separate prerequisites before implementation.

## Risks, verification and handoff

W2's100k protected-import commit qualification remains UNQUALIFIED; the qualified
initial1000 case creates no product cap. W3's100k metadata/vector workloads imply
no100k import-throughput claim. Unknown409, security-exception expiry and
platform/installer/hardware gaps retain their actual scopes and separate W9
functional/security follow-up; security expiry is not postponed.
Optional cosmetics, style cleanup and optimization move to the new W10; hosted
university/cloud outcomes are W11/W12. No earlier failure is relabeled PASS.

Plan implementation around exact-source/rights denial, migration/restart,
cancellation/drain, stale invalidation, adversarial inputs, real local-principal
boundaries, source return/focus/lock recovery, and task-specific evaluation.
Existing planning/ADR/reference checks and a genuine current content review
will assess this proposed packet; no such new result is claimed here. Ordinary
Wave approval at an immutable commit is still required before any W3 claim.

The [source manifest](source-manifest-05.json) and original private preparations
preserve the detailed authorship and review lineage. They are provenance, not a
second set of operative approvals or a publisher framework.
