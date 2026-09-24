# CAP-04.S02.T01 — independent pre-submission findings

Reviewer: `agent:/root/w2_s01_final_review`.
Candidate: `526d554d9b1067a2f867e050003894a4578fb1e7`.
Claim base: `02e613a5eda87d83fd73f125157395810e6ec2cc`.
Disposition: changes required; no controlled submission round was created.

- **F01, P2, blocking; AC2 / expired-cursor contract:** `assert_resumable`
  calls `_utc` without the model field's canonical-format check. A cursor
  expiring at `2026-01-02T00:00:00.000Z` accepts current time
  `2026-01-01T23:00:00.000-05:00`, although that instant is already expired.
  Naive timestamps also pass. Immediate cause: format validation was attached
  to the Pydantic field instead of the shared helper used by direct calls.
  Closure: enforce canonical UTC in that helper and regress offset/naive inputs.
- **F02, P2, blocking; AC1 / all-result license and terms metadata:** license
  and terms exist only on records. A complete empty or failed page therefore
  cannot retain page-level source terms or explicit absence. Immediate cause:
  the acceptance map covered empty-page query/time provenance but omitted its
  independent terms observation. Closure: required page-level source terms,
  explicit absence states, and empty/failed serialization tests; keep record
  observations distinct from page observations and from rights grants.

The reviewer ran small read-only reproductions without changing HEAD or inputs.
Other contract checks passed at this candidate; they did not establish these
missed boundaries. The portable scope, broker/authentication separation and
deferred runtime obligations were otherwise appropriate. Findings are retained;
closure and final evidence disposition must bind the subsequent candidate.
