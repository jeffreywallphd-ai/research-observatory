# CAP-04.S01.T03 — durable requests and service execution

Uses a reserved revision-zero typed settings record for exact commit requests,
following existing immutable parser configuration/command receipt patterns.
Read-only independent advisory selected this smaller lawful route over another
schema migration. No v13 history or DDL changes; no configuration encoded into
labels, shortened hashes, paths or in-memory-only state.

Adds bounded manifest header/member reads, exact accepted-output authentication,
current/historical rights checks, and service scheduling/reconstruction. Worker
authorization compares saved commands to current exact authority. Existing
idempotency lookup precedes admission; a concurrent winner is authenticated on
conflict. Ordinary restart and explicit terminal continuation preserve original
inputs, while security-epoch changes cancel prior work.

Exploratory checks passed: immutable request reopen/payload/actor/revision guards
(2, 1.842s); manifest paging/revocation and scientific replay (3, 3.979s); service
restart/admission gap/duplicate request/changed command/security epoch
(5, 7.309s); preview cancellation (1, 1.016s); stale draft and explicit cancelled
continuation (2, 3.110s). Affected mypy and lint passed after routine formatting.
No failing product assertions occurred in this increment; these targeted tests
were added alongside implementation, not presented as a pre-edit RED proof.

Select fresh affected publication, service, request and ordinary-summary checks
for the committed candidate. No unrelated full profiles. API/generated/native/
renderer actions, large imports and final guard/transaction lifetime remain
unqualified. Task stays IN_PROGRESS. The request is not itself an accepted
canonical import, and manifest IDs never imply Work reconciliation.
