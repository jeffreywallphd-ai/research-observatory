# CAP-04.S01.T01 — adverse pre-submission review

Candidate: `9cd11940a84a5ea088f099db2a42cf4e6da73ed3`.
Independent reviewer: `w2_ux_plan_review`. Disposition: changes required.
This records actual pre-submission findings, not an invented taskctl review round.

- **F01 / P2 / AC1 malformed isolation:** With `max_field_bytes=20` and
  `max_macros=1`, a 25-character `@string` name is malformed but consumes macro
  capacity. A following valid `q="Good"` definition then fails. Stage state until
  complete record validation. Regression: `test_rejected_macro_name_does_not_consume_capacity`.
- **F02 / P2 / AC1 and ADR-0027 fidelity:** `@string{p="old"}` followed by
  `@string{p=unknown}` and `@article{a,title=p}` produces stale `old` without a
  warning. Retain unresolved shadowing and suppress invented candidates.
  Regression: `test_unresolved_macro_redefinition_shadows_stale_value`.

Reviewer used synthetic BytesIO reproductions, made no edits, and did not replay
broad suites or the benchmark. Both findings were open at this disposition.
Later closure must reference these IDs and exact remediation candidate.

Qualification at this candidate: 23 focused service/contract/streaming tests
passed (47.633 seconds), lint/format/types, quality inventory, build manifest
and backlog views passed. Planning-site validation failed on four historical
absolute-link renderings after clone relocation; it is not a passing check.
Raw machine outputs remain ignored under `artifacts/tmp/`.

Follow-up independent contract clarification by the same reviewer identified
**F03 / AC3 / ADR-0027:** record-level-only warnings do not satisfy the explicit
per-field warning handoff. A rejected normalized candidate has no candidate index,
so attribution must accompany ordered raw fields. This omission also exists at
the original candidate above. Add bounded field warnings for normalization,
unresolved macros and formula-like cells, with focused attribution/schema tests.
This is still pre-submission feedback, not another controlled review round.
Acceptance-map extension: retain source-indexed field warnings on ordered raw
fields, with a repeated DOI, unresolved macro and one formula-like CSV cell.
The regression failed before the change because RawField lacked warnings.
T02 presents/resolves this information; it must not reconstruct lost attribution.
