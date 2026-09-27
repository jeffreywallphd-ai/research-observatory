# CAP-04.S03.T02 — atomic candidate publication checkpoint

This is development progress on the existing approved claim, following commit
`00545611`. It is not qualifying task evidence or independent disposition.
CAP-04.S03.T02 remains IN_PROGRESS; local main has not advanced.

The repository now publishes exact reconciliation, immutable cached features,
the candidate-set manifest and ordered pair metadata, provenance/dependency facts,
and accepted workflow output in one SQLite transaction. Current source rights
are collected before the writer and rechecked against index decisions during
publication. The current attempt capability, live lease and cancellation state
are validated, with preparation and same-connection publication heartbeats.
Stop hints only abort; durable cancellation remains a worker/API responsibility.
The canonical SQL progress hook also polls that stop hint during long statements;
rollback runs after the hook is removed. A failing SQL-interruption test preceded
the fix and now proves that neither partial facts nor accepted output survive.

Strict candidate explanations preserve the frozen kernel's component scores,
weights, missing/disputed states, identities, configuration and review-only
disposition. The canonical set digest binds each pair's ordinal and digest.
Members bind final Work heads after the batch's exact additions, avoiding material
dependence on superseded intermediate receipts. Fuzzy similarity does not merge.
The unreleased schema-15 proposal now has 67 tables, retaining the literal
schema-14 predecessor and verified rollback behavior.

The read-only advisory found F-BATCH-01: a single provenance packing pass could
still exceed 64 inputs for over 4,096 leaves. Repeated packing preserves material
and historical branches. Its structural regression traverses 4,097 material and
65 historical leaves; this is not a real large-corpus performance claim. The
advisory also led to preparation heartbeats and an advancing-clock continuation
test. Complete source enumeration remains an explicit worker integration duty.

Independent read-only replay by `agent:/root/w2_t03_review` closed F-BATCH-01
and the preparation condition: both focused tests passed in 4.095 seconds.
The subsequent batch enumerator exhausts the bound queue snapshot and source
owner streams, validates exact output/job identity, page continuity and selected
totals, and rejects partial/substituted streams. A real import-owner test proves
that later changed-draft arrivals stay outside the original snapshot and appear
in a newly collected one. Publication still needs its worker wiring to this
enumerator before claiming an integrated complete-inventory result.

Development observations are retained in ignored `artifacts/tmp/`:

- `CAP-04.S03.T02-batch-publication-before-02.log` records missing publication
  behavior before implementation; the earlier fixture setup error is retained.
- `CAP-04.S03.T02-batch-publication-03.log`: four initial contract/publication
  tests passed in 4.217 seconds.
- `CAP-04.S03.T02-batch-publication-05.log`: seven batch cases passed; the
  continuation fixture used a nonexistent Task Center field and errored.
- `CAP-04.S03.T02-batch-preparation-06.log`: the corrected focused continuation
  and advancing-clock preparation test passed in 2.151 seconds.
- `CAP-04.S03.T02-batch-final-dev-01.log`: all ten candidate/publication
  development tests passed in 16.808 seconds.
- `CAP-04.S03.T02-batch-inventory-01.log`: all three real queue/import-owner
  enumeration tests passed in 10.253 seconds, following a missing-module red test.
- `CAP-04.S03.T02-batch-sql-stop-02.log`: the SQL interruption/rollback
  regression passed in 2.061 seconds after its retained failing run.
- `CAP-04.S03.T02-batch-regressions-01.log`: 28 existing exact/review/cache and
  predecessor/protected-migration checks passed in 73.603 seconds. This development
  group began before the subsequent recursive packing/heartbeat remediation;
  final qualification must run at one committed candidate.

Remaining integration includes exhaustive source enumeration, persisted request
and worker wiring, authenticated stop/cancel/close behavior, historical-versus-
current coverage projection, generated client/native and governed desktop review,
fresh criterion-linked qualification, independent task disposition and local
integration. Required S03 and W2 qualification remain outstanding.
