# CAP-04.S03.T01 — independent pre-submission review 01

Disposition: **changes required**. This is an expanded independent review of the
committed candidate, not a taskctl review round or task approval. Both findings
below must be closed before approval; retain this adverse record unchanged.

- Reviewer: `agent:/root/w2_c02_review`
- Implementer/task owner: `codex-w2-implementation`
- Candidate: `157e6d3823979896f40d9ab183bf3c932f35fe08`
- Claim base: `e09d313fdb86ff6ea260f04a56fdaf7063198a57`
- Approved W2 packet: `c85a59f3a293f8e3f2eaf6454682c9a14b1efa55`
- Governing task: approved CAP-04.S03 section 9.1, with ADR-0013, ADR-0014,
  ADR-0024, ADR-0025 and ADR-0027 within their remits.

The reviewer inspected the implementation afresh after the earlier advisory
preflight, did not implement or commit the candidate, and kept the shared checkout
unchanged during qualification. Only this review record is authored after the
implementer reported the qualification process complete.

## F-S03-T01-01 — current canonical fields lack their current Work revision binding

Severity: **P2**. Blocking: **yes**. Acceptance criteria: **1 and 3**, specifically
audit-preserving immutable identities/revisions and the corresponding public
contract; approved slice section 5.2 and ADR-0013/0024 require exact revision
references rather than an unqualified stable identity.

At the reviewed candidate,
`reconciliation_repository.py:465-504` loads the immutable original reconciliation
receipt, then calls `_work_sources` with only its stable Work ID. That method
(`:169-185`) selects every contributor to the Work, including contributors linked
after the receipt's `workRevisionId`. The returned `ReconciliationInspection`
(`reconciliation/contracts.py:91-103`) contains the original receipt and these
assembled `canonicalFields`, but no identity for the current canonical Work
revision represented by those fields.

Concrete sequence:

1. Source A creates Work W, revision r1, with title Alpha.
2. Source B, with an equivalent compatible exact identifier, links to W and
   creates r2 with a competing title Beta.
3. Inspect A's assertion revision. The result still names r1, while
   `canonicalFields` includes B and reports the Alpha/Beta dispute. No field binds
   that projection to r2.

This finding follows directly from the public response model and SQL/read path;
the reviewer did not claim an independently executed reproduction. The
implementer confirmed that `canonicalFields` is intended to describe the current
assembled Work while `result` retains the historical receipt. That distinction
is therefore material for downstream consumers and must be explicit in the
contract.

Smallest remediation: retain the historical `result` unchanged and add an
explicit current canonical Work ID/revision binding for `canonicalFields`,
resolved consistently with the contributing-source set in the same read
snapshot. Keep review-required/no-Work behavior explicit. Do not rewrite old
receipts or use UUID lexical order as revision authority.

Required regression: inspect A before and after B is linked. Assert the original
receipt remains identical, the current projection binding advances from r1 to
r2, and its fields include the correct contributors. Repeat after reopen and
retain denial when any contributing source loses required current rights.
Regenerate and check the affected portable/API contracts.

## F-S03-T01-02 — new scholarly schemas are absent from the build-input inventory

Severity: **P2**. Blocking: **yes**. Acceptance criterion: **3**, relevant contract
and build metadata must be updated with the implementation.

`packaging/build-inputs.json:14` does not list the four new schemas:

- `packages/contracts/scholarly-records/normalized-identifier.schema.json`
- `packages/contracts/scholarly-records/reconciliation-inspection.schema.json`
- `packages/contracts/scholarly-records/reconciliation-result.schema.json`
- `packages/contracts/scholarly-records/source-assertion.schema.json`

The selected `build-manifest` check actually fails at the reviewed candidate:

```text
ERROR: build inputs schemaPaths must exactly inventory every repository schema
Build manifest: FAIL
```

Bound command: `.venv/Scripts/python.exe -B -s tools/build_manifest.py --repo .
--output artifacts/tmp/CAP-04.S03.T01-build-01.json`.

- Exit code: `1`; recorded elapsed time: `1.062` seconds.
- Raw log: `artifacts/tmp/CAP-04.S03.T01-build-manifest-qualification-01.log`
- Raw log SHA-256:
  `3ac922b8627a3a7d1b3a0440e4c3bd2099202309c77c04add55f68fc2c312846`

Smallest remediation: add the exact new schema paths to the governed inventory,
preserving existing entries and exact-inventory enforcement. Rerun the selected
build-manifest check at the committed remediation candidate. Do not exempt the
new directory or relabel this failed run as passing.

## Reviewed evidence and limits

The completed producer receipt is
`artifacts/tmp/CAP-04.S03.T01-qualification-01.json`, raw SHA-256
`eba06fb78516c0fb5833151570728b290e11e63dfbef2a0ebce0b8747c098453`.
The reviewer authenticated all 19 recorded raw-log digests and their candidate
binding: 18 selected checks report exit zero; build-manifest reports exit one.
The focused reconciliation log reports 26 tests in 31.179 seconds, `OK`, and has
SHA-256 `7e0fa2d6cf913d01fe118761c461366b48294a7f45c5494efe65f3d6c13345d3`.
Its path is `artifacts/tmp/CAP-04.S03.T01-reconciliation-qualification-01.log`.
Passing selected checks do not override either finding.

No further material blocker was identified in the reviewed normalization and
entity scope, full-candidate conflict/reassignment handling, immutable source
addresses, accepted Intent and available current-rights checks, lifecycle fence
across source resolution/publication, canonical transaction/idempotency,
provenance/dependencies, bounded failure paths, or literal populated-v13 and
SQLCipher migration/backup/reopen implementation. This is a bounded review
conclusion, not an assertion that unselected behavior is qualified.

The production-composition test uses real Windows DPAPI/SQLCipher, retained
imports, durable source workers and synthetic HTTP. It recreates an application
session and reopens the project; it does not spawn a separate operating-system
process or qualify live providers. Repository/pure-matcher fixtures prove their
own boundaries, not complete native GUI behavior. T02 review UI/fuzzy matching,
T03 version graphs, slice/checkpoint and Wave qualification remain separate.

No frozen task submission or final task evidence manifest has been approved by
this record. Incremental independent closure review should replay these two
findings, authenticate fresh affected proof at the remediation candidate, and
then review the actual frozen submission before any formal task disposition.
