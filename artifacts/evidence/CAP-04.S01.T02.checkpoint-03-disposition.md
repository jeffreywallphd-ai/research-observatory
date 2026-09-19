# CAP-04.S01.T02 — checkpoint-03 closure and integration

Candidate: `904a92d1be26ce7a9d343d609daa46e5e12514a3`.
Adverse predecessor: `a6219124afd9165414b4ccefd0e0ff9cb714aa76` and
`CAP-04.S01.T02.checkpoint-03-review-01.md` remain intact.

The exact P1 denial → undo → raw/historical read regression failed before the
fix. Restoring history now checks all eight action permissions against current
defaults and effective per-record permissions before inserting anything. It
streams all historically changed ordinals, not only the visible page. The new
tests also cover export restrictions beyond a page and default-rights changes.

At the fixed candidate, all 10 draft tests passed in 2.633 seconds; changed-file
Ruff, formatting and Mypy passed. The earlier 28-test checkpoint run is historical,
not relabelled as a fresh remediation run. The initially moving-HEAD site check
was excluded; a fresh check with HEAD and all selected planning inputs fixed
passed for 19 capabilities, 111 slices, 337 tasks and 492 HTML pages. New activity
source/tests were outside that planning input boundary.

Independent reviewer `w2_source_packet_preflight` approved the combined checkpoint
at this candidate: P1 closed, no incremental blockers, three fresh focused tests
passed in 0.871 seconds. Its checkout/HEAD remained unchanged during execution.
This exact candidate was fast-forwarded into local main without push or checkout
change. CAP-04.S01.T02 remains IN_PROGRESS; no formal R01 or whole-task approval.
