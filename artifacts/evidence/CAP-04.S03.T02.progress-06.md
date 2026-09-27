# CAP-04.S03.T02 — recovery and qualification remediation

This continues the owned W2 task at `3998d9c68800d06b4e9400a99e785f3dd2005a01`.
It records development and adverse results, not a task disposition or completion.
Approved scope, frozen W2 approval, reference 1.7 and historical migrations remain
unchanged. The [independent adverse review](CAP-04.S03.T02.pre-submission-review-01.md)
preserves both blocking findings against that candidate; final closure requires
independent review of the successor and its fresh evidence.

## Preserved committed qualification

The fixed-candidate `CAP-04.S03.T02-*-qualification-01` logs and machine records
remain in ignored `artifacts/tmp/`. Reconciliation passed 137 tests in 338.232
seconds; upstream authority passed 59 tests; the migration chain passed 31.
Shared contracts had two failures: three new tables used prohibited generic
JSON columns, and five new triggers were missing from the expected inventory.
Python format/types, ADR association, UI evidence invocation/metadata and build
schema inventory also required repair. Native tests under the actual Windows
principal passed 152 cases with one existing ignored case. Full Clippy failed
on four warnings already present at the claim base: an unused import action,
two parity expressions and one collapsible conditional. These remain explicit
W2 quality debt; no lint rule, test or approval was weakened.

## Repairs and development proof

Dedicated `feature_json`, `candidate_set_json` and `explanation_json` documents
now have closed fields, exact versions, scalar types and collection/score bounds.
Direct SQL malformed-document checks retain the original general scalar-storage
assertions. The 15-case typed-storage pass is preserved in
`reconciliation-typed-storage-02.log`. Expected trigger inventory, build schemas,
test annotations, the proposed documentary ADR-0032 and approved-reference UI
implementation metadata are repaired. A subsequent task-range type check passes
60 files; historical migration-test typing remains separately deferred.

The two independent dependency findings each received a failing regression before
implementation (`reconciliation-impact-continuation-before-01.log`). Exact
commands now bind their root runs durably. The worker authenticates either an
exact command or a review outcome and the corresponding historical Work states.
Graph growth creates a fresh same-semantics preview and run, sealed snapshot,
ordered owner continuation and predecessor cancellation in one writer transaction.
Original runs, impact items, stale causes and audit history remain immutable.
The global graph validator, checkpoint comparison and manual terminal states
remain intact. Depth 128 is an explicit resource-denial bound; the code does not
promise completion under indefinitely continuing graph changes.

Incremental independent advice added saved-snapshot corruption checks. First,
substituted preview/authority/item/checkpoint values with real graph growth were
reproduced and then denied. Next, substitution of the graph digest alone was
reproduced without graph growth. An owner-controlled digest now binds the complete
typed run snapshot, including graph, preview, authority and limits. Historical
continuations also validate saved item hashes and complete checkpoint chains.
The failure logs `reconciliation-continuation-corruption-before-01.log` and
`reconciliation-continuation-graph-seal-before-01.log` remain preserved. The final
three-test focused pass in `reconciliation-continuation-graph-seal-after-01.log`
covers those denials, 100-of-102 partial propagation with all transaction failure
seams and lost acknowledgement, and actual exact-batch restart. It passes in
10.121 seconds. An earlier 50-case dependency/review/worker development pass is
retained separately and is not represented as final sealed-schema qualification.

Unreleased schema 15 now has 70 canonical tables. Only its current fingerprints,
profile and migration targets change; frozen v14 bytes remain unchanged. The
14-case schema/migration development pass before the final snapshot-seal addition
is retained in `reconciliation-continuation-schema-01.log`. The successor
`reconciliation-continuation-schema-02.log` passes all 14 cases against the final
70-table schema in 31.195 seconds. The fourth task-range quality development log
passes format/lint for 64 Python files and narrow typing for 60. Fresh committed
qualification remains required. The independent incremental source advisory
closes the saved-snapshot/graph-digest gaps without another material finding;
it is explicitly not a formal task disposition.

Browser scaling checks now measure rendered text ranges at 1x and 2x, verify
focused controls remain usable, and cover 1440×900, 1280×720 and 720×1000 in both
themes. `reconciliation-measured-scaling-02.log` passes. CSS zoom is explicitly
browser evidence, not a full-shell/native-DPI qualification claim.

Fresh committed-candidate checks, criterion mapping, independent task disposition
and local integration remain required. Full S03/checkpoint/W2 profiles, existing
historical Python type errors, native Clippy warnings and Windows symlink-token
obligations remain outstanding; none are waived by these focused repairs.
