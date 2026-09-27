# CAP-04.S03.T02 — effect retention and final candidate preparation

This continues the same approved task. It is development history, not a task
disposition, slice completion or release approval. Historical evidence remains
unchanged.

## Qualification 02 and retained failures

The clean fixed candidate `b3cba265425505abaaac800d2f83f2057d2d41d5`
passed 144 reconciliation tests (374.433 seconds), 15 dependency-impact tests,
59 upstream-authority tests, 31 migration-chain tests and 37 shared-contract
tests. Affected Python formatting/lint passed 64 files and narrow typing passed
60; generated contracts, client checks (135 tests), desktop checks (159 passed,
three existing conditional skips), build, native formatting, inventories,
architecture, repository structure, fixture corpus, ADR range and backlog views
passed. Native tests under the actual Windows principal passed 152 cases with
one existing ignored witness exercised separately by the renderer harness.
Planning review passed 492 generated pages. Machine records and raw outputs
remain under `artifacts/tmp/CAP-04.S03.T02-*-qualification-02.*`.

The unchanged UI gate correctly failed because `3998d9c6` mixed additive quality
inventory and UI implementation. The [independent reconstruction review](W2.unintegrated-tail-reconstruction-01.md)
records the bounded remedy: preserve the complete original branch at
`codex/w2-unintegrated-original-b3cba265`, split only that unintegrated mixed
commit into `18d2d8ae8ac8da3beff8612d49aaa8e4f840ca6f` (inventory and non-UI
support) and `69653c728e30dcf39430e71a3d45236de59c2c13` (UI implementation),
then replay the recovery commit as `531ff646aae5119afcf202f0e5883b74832489c2`.
The resulting tree exactly matches original `b3cba265`:
`ffc54f55af05ab25dd766a948f314b5b4183753b`. Normal commits and branch renames
preserved all history; local main and approvals were untouched. Promotion to
the canonical campaign branch completed after the independent review. The
unchanged UI gate then passed (`W2-reconstructed-ui-gate-01.log`). Its original
failure remains preserved; neither the gate nor its assertions changed.

## Adverse edge evidence and repair

The [second independent adverse review](CAP-04.S03.T02.pre-submission-review-02.md)
preserves F-IMPACT-EDGE-03. Removing a material edge allowed recovery to cancel a
pending root and complete an empty child. Original impact items still denied
fresh reads, but the intended stale effects were not materialized. The worksheet
now identifies this missed effect-retention boundary. An initial development
test had a wrong storage-column name (`effect-retention-before-01`, two setup
errors); after fixing only the fixture, `effect-retention-before-02` reproduced
both edge removal and weakening as two actual failures.

Recovery now requires every authenticated historical run's output, kind,
disposition, confidence and review duty to survive in the new preview before
publishing a child, link or cancellation. Additional effects remain allowed.
This protects pending effects; it does not claim full forensic detection of
unrelated graph corruption. `reconciliation-effect-retention-after-01.log`
passes five targeted cases in 13.704 seconds: both denials, repeated graph growth,
partial propagation with transaction fault seams/lost acknowledgement, and exact
batch worker restart. Final independent disposition remains required.

## Accessible synthetic report publication

Qualification 02's actual native and protected-Core tests passed, but a later
attempt to read the native report hit filesystem permission denial even under
the normal user execution context. No ACL or protected-storage control was
changed. Both test producers now print their synthetic boolean/count report
and exact UTF-8 report digest into the retained runner output when writing the
report. Assertions and actual principal boundaries are unchanged. Fresh tests
will establish the successor's result; a report hash alone is not execution
proof, and the unreadable prior report is not represented as independently read.

Fresh qualification will bind a new clean committed candidate. Full S03,
checkpoint and W2 qualification remain required. Existing historical Python
typing errors, the four pre-existing native Clippy warnings, conditional native
settings fixture coverage and Windows symlink-token obligations are not waived.
Browser CSS scaling evidence remains distinct from full native-DPI evidence.
