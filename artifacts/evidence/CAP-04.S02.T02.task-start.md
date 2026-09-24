# CAP-04.S02.T02 acceptance closure

Claim base: `6316b14d439c10f85fea6557e141d6f04111f17b`.
Authority: the approved CAP-04.S02 plan section 9.2 at W2 packet
`c85a59f3a293f8e3f2eaf6454682c9a14b1efa55`; ADR-0027, ADR-0017,
ADR-0019 and the existing canonical identity/provenance/storage contracts.
CAP-04.S02.T01 is DONE and independently approved.

## Material proof map

| Criterion / boundary | Required outcome and selected proof |
|---|---|
| AC1 provider semantics | Synthetic known-item OpenAlex/Crossref fixtures produce source-preserving identifier/title/author/date/venue/reference candidates, not canonical Works. Exact field/filter/sort/projection compilation; reject unsupported semantics without widening. |
| AC1 pagination/replay | A page binds the scientific request, provider, versions and current cursor. Failure does not advance it. Duplicate publication is idempotent; changed request/invocation collisions fail. Fresh repository/service instances resume the retained checkpoint and replay the sanitized response. |
| AC1 rate/cache | One in-flight request per provider, at least one second spacing (or stricter advertised rate), at most three attempts, bounded jitter/Retry-After, observable circuit recovery. Exact project/page cache identity, current authorization on hits/revalidation, ETag/Last-Modified, explicit expiry and no cross-project reuse. |
| AC2 broker authority | Core-owned admission compiles the wire request from the validated scientific request. Current open session/project, Intent, policy and exact researcher-authorized payload are checked before dispatch/retry/cache/publication. Offline, changed/revoked authority, unsupported query and cancellation deny without dispatch or publication. A request DTO is not consent. |
| AC2 network/secret boundary | HTTPS provider allowlist, DNS-address binding, private/loopback/link-local denial, normal TLS verification, no environment proxy or unchecked redirects. ADR-0017 leases remain broker-only. Bound wire/decompressed bytes and parsing; test malformed JSON/schema drift, timeout/reset, 429/5xx, terminal auth, hostile cursors and echoed credential/contact values in arbitrary fields/errors/headers. |
| AC2 durable principal | Use the existing encrypted project/object/repository/provenance boundaries, not a source-only database. Atomic accepted page, response references and checkpoint; injected publication failure/restart leaves no false completed page. Focused actual local persistence/transport proofs supplement unit doubles. |
| AC3 compatibility/audit | Preserve CAP-04.S02.T01 schemas and source-specific observations. Any necessary additive persistence change uses the existing migration authority and exact predecessor tests. Content-free audit, protected replay data, explicit unknown rights and unavailable-body state. Update only affected inventories/docs/fixtures. |

First tests precede product code: compilation/known-item mapping and malformed or
unsupported response cases; then broker admission/rate/redaction and durable
publication failure/restart tests at their implementation boundaries.

No account provisioning, live provider query, credential inspection, real project
access, full-text acquisition, automatic canonical reconciliation, or new UI
pattern is authorized here. The adapter seam is consumed by subsequent source
and search work. Any user-facing wiring must use the existing approved reference.

Focused checks cover new connectors, affected contracts/runtime packaging and
persistence. Completed import/performance suites are not replayed. Integrated
four-provider slice checks, optional explicitly authorized live smoke and fresh
Wave qualification remain separate; mocks are never labelled live success.

Read-only adversarial preflight: incorporated. Backend Intent destination
authoring and exact-request consent fit ADR-0019/ADR-0027's approved provider work;
this does not authorize a new governed UI interaction. Source-package trust is
not exact-query consent. Existing canonical protected documents/settings indexes
can retain source observations without introducing a parallel database.

The second bounded preflight exposed a missed AC1/AC2 boundary: generic Task
Center cancellation does not revoke connector consent, so polling before page
publication is insufficient. Add current workflow claim/lease/cancellation to
the publication transaction, atomically with page/checkpoint/output completion.
Retain the failing `test_queue_cancellation_at_publication_boundary_cannot_advance_checkpoint`
regression and add expired-claim plus crash/restart proof before remediation.
This is ordinary in-scope debugging, not a new human approval gate.
No mandatory new human gate identified at task start.

## Work-in-progress backup checkpoint

The owner permits unfinished work on `codex/w2-implementation`; only reviewed,
verified units may advance `main`. This checkpoint preserves the partial
implementation and the known failing cancellation-publication regression. It
is not qualifying evidence, an independent disposition, or task completion.
Resume with the atomic publication remedy described above, then finish the
affected verification, inventories and review. No completed product test suites
were rerun merely to consolidate the branch checkout or create this backup.

## Resume findings and focused closure

The 2026-09-24 resume retains the original claim base and all adverse logs in
ignored `artifacts/tmp/`. Taskctl reopened the owner-stopped task. The initial
readiness check validated the immutable capability/slice approvals but its final
site check overlapped that transition and found stale task projections. Site
regeneration followed by `plan_review_check` passed all 492 pages; no approval or
frozen packet was changed.

- Publication: preserve the original cancellation failure. New expired-lease and
  interrupted-completion regressions failed before the remedy. Page/checkpoint,
  provenance and workflow completion now share the existing canonical writer;
  replay authenticates the exact attempt. Include lost post-commit acknowledgement.
- Independent incremental review found sliding cache freshness, lost redaction
  labels on hits/304s, and JSON exponent overflow escaping typed errors. The
  protected-cache and broker regressions reproduced each before remediation.
  Keep remote-validation time and body redaction provenance; reject non-finite
  decoded numbers. No live-provider success is inferred.
- Actual runtime composition exposed conflicting import/connector project
  resource policies and a receipt-read lock inversion. Share the conservative
  document-lane policy and preserve project-before-object lock ordering. The
  timed diagnostic and interrupted test remain adverse observations. Qualify
  the real runtime factory with protected storage and synthetic HTTP, plus the
  two affected import-runtime cases (not the completed import/performance suites).
- Bounded test maintenance: the inherited Intent test asserted schema v10 while
  bootstrapping current v13. Reuse the fingerprint-checked historical v10 builder,
  insert the unchanged hash-bound Intent bytes, migrate, then assert legacy
  preservation and current authority. Keep the original schema/fixture assertions;
  no migration or product acceptance rule is weakened.

Development passes are diagnostic, not committed-candidate qualification.
Final selected checks cover connector mapping/broker/transport/TLS/persistence,
consent/workflow/API/runtime, affected Intent and generated clients, build/module
inventories and quality. Full profiles, native UX, packaging execution and the
four-provider slice matrix remain their later integration/Wave obligations.
