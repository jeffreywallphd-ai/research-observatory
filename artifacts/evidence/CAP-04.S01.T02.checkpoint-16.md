# CAP-04.S01.T02 — summary API, generated client and renderer

Increment from approved `7975c54861fe7d266eaf627b2ccd1feab3829ef9`.
Task remains IN_PROGRESS. Five bounded authenticated routes read, explicitly
start, cancel and page complete-draft summaries/candidate members. They reuse
project/preview/queue guards and exact current revisions. Failed or absent results
are not zero. Cancelling summary leaves the draft editable. Immutable candidate
membership never merges Works or predicts CAP-04.S01.T03 commit effects.

Transport proof: strict request/response schemas, no raw exception content,
no-store, coherent counts, exact identity/cursor checks and owned async inputs.
The native allowlist accepts only these bounded operations. Raw candidate titles
remain inert text in the existing generated-client/renderer boundary. No renderer
filesystem authority, actor substitution, new queue engine, migration or UI token
system. Group member pages reuse current-rights record projection and final-head
validation; only complete accepted summary groups are visible.

Experience proof: explicit calculation; active status polling only; error and
cancellation help; coverage denominator and missing DOI; raw/DOI candidate reasons;
bounded group/member navigation; comparison and selection into existing correction
controls; clearing on draft change and stale async suppression. Shared panels,
tables, buttons and spacing follow reference 1.7. The built renderer test uses
real Core/project/parser/worker/review data in both themes with explicit native
chooser/host doubles; this does not establish Windows dialogs or production DPAPI.

First API tests failed with 404 before route implementation. Exploratory real
service tests now cover explicit summary, stale revision, cancellation and
noncontiguous candidate paging. Generated-client tests pass 20 cases including
owned async requests and response substitution. Initial TypeScript checking
required a precise owned-record intersection; an absent contracts Vitest shim
was bypassed using the existing desktop-installed runner, not a dependency change.
Mypy required the response algorithm's declared literal default. No assertion or
permission was relaxed. Commit-bound checks and independent review follow.

Selected: affected API tests, generated-contract drift/types/import client tests,
native import request test, desktop lint/type/affected renderer tests and the built
real-Core interaction path in both themes. Checkpoint-15 worker authority proof is
already reviewed; no unrelated W1 suites. Native-window, production packaging and
100k protected-project qualification remain the task's next integration work.
