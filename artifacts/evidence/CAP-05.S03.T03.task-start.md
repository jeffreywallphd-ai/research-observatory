# CAP-05.S03.T03 — anchor resolution and citation-link APIs

Claim base: `c1899e0de48e79221ff0335a31c976ef87e02db5`.
CAP-05.S03.T02 is DONE, independently approved and integrated locally. The
approved S03 section9.3 and accepted ADR0013/0024/0029 govern this task. Reuse
canonical Document revisions, accepted structure, protected artifacts, current
native/session/Intent/privacy/exact-copy rights and material-dependency records.
No lighter parsing tier, parser benchmark tuning, automation-framework work,
source-byte PDF activation or scholarly verification is included.

| Material outcome/boundary | Planned proof |
|---|---|
| Evidence resolves to its exact accepted source revision, readable retained context/adjacent text, document metadata and canonical reference targets. | Authored synthetic structural/reference/citation fixtures through actual Core, SQLCipher and envelopes; reconstruction/reopen and later accepted-head cases retain old exact targets. Candidate/ambiguous/unresolved reference states stay explicit; no invented scholarly match or silent migration. |
| A broken anchor conservatively marks exact downstream revisions stale using existing durable dependency propagation. | Damaged/missing protected anchor and selector mismatch cases; authenticated canonical anchor/source and current rights before classification; existing append-only provenance/outbox/stale state, exact/idempotent retry and reopen. Unknown IDs, foreign sources and denied requests do not mutate staleness. |
| Current principal and source authority remain valid through delivery and side effects. | Actual lock/session, actor/Intent/privacy and rights-denial composition; substitutions and late changes deny with no research-bearing diagnostics, URLs or unrelated writes. |
| R01 F01: native stop inside publication rolls back before commit. | Signal the trusted native stop at the broken-anchor publication seam; require bounded denial and unchanged invalidation/run/stale/provenance/outbox counts. Explicitly close/reopen to obtain a new native session, reject the old session, and prove the valid retry publishes exactly once. Replay the same live actor scope on anchor creation. |
| Performance work preserves live authority and transaction ownership. | Exact immutable compiled catalog alone reuses full validation; foreign/malformed catalogs still fail. A fresh detached read-only Intent/bridge/workflow snapshot closes its coherent read transaction. Nested project scope expires and denies cross-thread/root/profile substitutions while retaining fresh metadata/access assessment. In-writer Intent content hashing detects corruption with unchanged declared hash. One context writer resolves source identity before exact-copy checks; lookup failure/foreign identity close before protected context, rights denial remains durable, and original verified_at/storage state stay unchanged. |
| Common structural/page resolution avoids full PDF/IR reads and meets the local100ms p95 budget. | Instrument forbidden whole-source reads; fresh actual API measurements with declared synthetic fixtures, warm state, sample method and runtime/hardware facts. Preserve T02 observations282.8404/291.2944/279.44ms as over-target. Use scoped existing transactions/authority checks; no privilege cache or weakened integrity assertion. |
| Public contracts and exact native commands are bounded, portable and strict. | Generated schemas, malformed/mixed-identity/body/Origin cases, native opaque-argument tests, selected lint/types and package/architecture coverage when impacted. Research content stays in protected artifacts and authorized responses. |
| Documentary architecture, audit and compatibility match the final change. | Append the implementation mapping/task link/precise affected paths to existing Proposed ADR0046 and index; exact claim-base-to-candidate ADR check. Preserve accepted decisions, frozen approvals, T02 R01/F01/R02 and the accepted S02 warm observation. |

Add the smallest behavioral failing/characterization tests before product edits
where practical. A short read-only independent design preflight targets canonical
reference identity, broken-versus-denied classification, atomic stale propagation
and the current-authority/performance boundary. Root implements the product work.
Select affected contract/repository/API/graph/native checks; broader integrated
S03 performance/restart/recovery review, S04 activation and installed desktop,
minimum-tier and fresh full W2 qualification remain separate required coverage.

Development timing is diagnostic, not task qualification. The first measured
breakdown averaged155.6ms (p95158.6ms), with nine database opens. After the scoped
authority and single-writer changes, one focused check measured86.6ms p95. The
instrumented phase run averaged89.5ms (p95105.2ms), with four database opens;
its slower responses were concentrated in authorized context access, not lookup
or database opening. A targeted commit diagnostic averaged84.5ms (p9587.5ms),
with durable context commits averaging2.5ms. These observations and all earlier
failures remain in task-owned development logs. They do not establish performance
on a committed candidate or waive the unchanged100ms criterion. Parser inference,
whole-PDF/IR reads and8GB/16GB hardware-tier qualification were excluded.

Independent R01 review found one blocking authority defect at candidate
`c2e92e7575a04aa8f8e5642623868e3b9adfdc1d`. The service supplied a frozen actor
callback, so the repository's in-writer final actor/authority check did not see
the trusted native-stop latch. The delivery-only late-detach test missed this
publication window: the response denied after stale/provenance/outbox facts
committed. Record R01/F01, add the exact failing regression before product
edits, and make actor delivery use the existing live scoped guard. Preserve the
existing delivery fence and durable rights-denial audit. This restores the
approved product cancellation boundary; no scope, criterion or framework change.

The same failing characterization exposed a second publication route: anchor
creation owns its protected-object writer and did not recheck the actor after
the canonical append seam. Its publisher now uses the existing current-actor
and durable-authority check immediately before returning to the owning commit.
Both regressions failed before these source edits. The first guarded-actor fix
closed invalidation but left creation failing; that partial result is preserved.
The complete development correction passes both cases, including actual
close/reopen, old-session denial and exactly-once invalidation retry. Fresh
committed-candidate checks and R02 independent disposition remain required.
