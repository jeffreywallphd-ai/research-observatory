# CAP-04.S03.T02 — review, cache and inventory foundation

This is an implementation checkpoint in the existing W2 campaign, not task
submission, integration approval or qualification evidence. T02 remains
IN_PROGRESS. The claim base and immutable approval remain those in the task-start
worksheet. All checks below ran during development on the working candidate.

The schema-15 proposal now preserves schema-14 history while adding sealed full
Work membership, append-only human decisions and aliases, and an immutable
derived feature cache. Review publication creates dependency-impact intent in
the same transaction. New derivations reject already affected material inputs;
historical inspection and identical authorized replay preserve original receipts.
The additive Core review routes and generated portable contracts are present.

Accepted workflow-output inventory now freezes exact provenance checkpoint
bounds and binds cursors to a snapshot fingerprint. It covers older succeeded
jobs and accepted continuations independently of the recent Task Center window.
Each acceptance binds job, attempt, output manifest, canonical revision,
completion event, outbox and command/output digest.

Development verification:

- `CAP-04.S03.T02-review-cache-04.log`: 29 tests passed, including actual populated
  v14 migration, rollback, SQLCipher backup/reopen, reversible review, exact
  current routing, source and prior-decision freshness, and cache authorization.
- `CAP-04.S03.T02-workflow-inventory-03.log`: 39 tests passed across initial
  inventory and the existing local executor's lease, cancellation and recovery
  boundaries. Later inventory remediation received the focused checks below.
- `CAP-04.S03.T02-inventory-corruption-before-01.log`: both new corruption
  regressions failed before remediation. A substituted completion event or
  attempt could hide an accepted job during paging. The row-filtering cause is
  retained in the worksheet.
- `CAP-04.S03.T02-inventory-remediation-04.log`: all three inventory tests passed
  after explicit failed-join and completion-binding denial. Read-only independent
  replay by `agent:/root/w2_c02_review` closed both original findings and rejected
  missing outputs, substituted outbox, inconsistent state and changed command
  bindings. This advisory review is not a formal task disposition.
- `CAP-04.S03.T02-inventory-continuation-01.log`: accepted continuation enumeration
  passed while the failed predecessor remained excluded.
- `CAP-04.S03.T02-cache-benchmark-01.log`: both scoring-freeze and known-corpus
  regression tests passed. The cached-input entry point retains frozen feature
  normalization, blocking, scoring, configuration and thresholds. The qualification
  split returned 1,092 true positives among 1,142 pairs against 1,115 gold pairs,
  with 20 overmerged and 23 fragmented derived components. The original unseen
  qualification occurred at `0d60a12d48d1807539f30499491aeec7ac4222e0`; the new cache
  bridge explicitly discloses that later runs use a previously observed corpus.
- Affected Ruff and six-file mypy checks, Core API generation and architecture
  checks passed. Logs named here are retained under ignored `artifacts/tmp/`.

The encrypted migration test uses actual SQLCipher with in-memory test key
authority. It does not substitute for the still-required real Windows principal
proof. Inventory metadata scanning has no large-history performance claim yet.

Remaining T02 work: accepted-source owner adapters; persisted batch authority,
durable reconciliation and candidate processing with cancellation/recovery;
candidate inspection and strict generated client/native routes; the approved
merge/split desktop journey; fresh real-principal and criterion-linked checks at
a stable committed candidate; independent task disposition and local integration.
S03 integration, checkpoints and fresh full W2 qualification remain required.
