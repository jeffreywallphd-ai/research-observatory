# CAP-05.S06.T02 — acceptance closure

Claim base: `4108a86d81b8b617939e20c5f9318db5e3e1f9e1` on the approved W2 campaign.
Dependencies CAP-05.S06.T01 and CAP-05.S05.T01 are DONE and independently approved.
Authority is the immutable W2 packet, CAP-05.S06 section 9.2, accepted ADR-0029,
the existing protected document/revision/anchor contracts, and the inherited
Parsing Quality page of Academic Minimal 1.9. This worksheet adds no scope or
approval. T03 owns batch parser-upgrade comparison and its broader reprocessing
workflow. Larger parser/model variants remain deferred to W5.

| Material boundary | Intended observable outcome | Planned proof |
|---|---|---|
| Typed correction | Section labels/order, block splits/merges, reference matches, original-page anchors and corrupted-region exclusion are bound to exact base IDs and expected old values. Draft undo restores the prior proposed operations. Original bytes, parser IR and history stay immutable. | Domain tests with authored structure, Unicode contributors and wrong-target/base substitutions. |
| Explicit acceptance | Saved drafts and previews leave the accepted head and downstream state unchanged. A confirmed, exact draft appends a new revision, human decision, provenance/outbox and scoped dependency change atomically. | Actual SQLCipher/encrypted-object integration; inspect before/after canonical heads and immutable records. |
| Identity/read-back | Source, base, draft revision/digest, operations, author/rationale, authenticated acceptor and deterministic result remain bound. Reopened accepted corrections reject missing/substituted records or a mismatched result. Every successor receives fresh canonical element IDs. | Protected repository substitution and close/reopen tests; retained original and original-anchor checks. |
| Failure/recovery | Concurrent-base or draft conflicts refuse publication. Interrupted save/accept rolls back. Exact retry does not duplicate revisions, decisions or dependency events; a changed command cannot reuse an outcome. | Existing deterministic publication fault seam, concurrent CAS and exact-retry integration tests. |
| Real authority/resources | Native owns root/session/principal. Current project/Intent/privacy and exact source inspect+derive authority hold through save, acceptance, materialization and delivery. Lock/stop discards late protected output. Reads and output are admitted and bounded before allocation. | Actual Native/Core and encrypted persistence tests; wrong project/session, denied derive, lock/stop and bounded request/response cases. IPC doubles remain explicitly limited evidence. |
| Source relationships | Reorder, split, merge and exclusion preserve authenticated source intervals. Native/Docling relationships authenticate against their original machine structure before mapping to corrected IDs. Human rematches remain distinct from machine assertions or verification. | Authored JATS role/identifier/citation/table fixtures and retained Docling relationships; changed ordering, repeated markers, Unicode and ambiguous multi-origin cases. |
| Approved experience | Real quality dimensions and queue, structure/anchor/table/figure/reference checks, source Reader, proposed-versus-accepted correction ledger and truthful impact preview use the shared shell/workflow. Keyboard/focus, both themes, loading/empty/denied/conflict/recovery and supporting return preserve saved drafts only under fresh authority; lock clears private state. | Focused component/interaction/accessibility checks plus the narrow actual renderer→Native→Core save/accept journey and durable outcome. |
| Compatibility/audit | Closed additive schemas and protected records preserve accepted revision v1, original source and literal migrations/storage profile. Content/rationale remain encrypted; diagnostics carry bounded codes. | Schema checks, original document/revision/reference/citation/table regression selection, immutable migration blobs, actual audit/outbox inspection and independent review. |

First product tests will cover typed transformations and wrong-old-value refusal,
then protected draft/non-acceptance and explicit acceptance with rollback/reopen.
The independent read-only design preflight has been incorporated, including
the source-order trap in existing native enrichment consumers. No new database
migration is planned: protected correction records use the existing document
aggregate and object-store facet with an exact new MIME and bounded admission.

Verification selects affected domain, protected repository/service, Native IPC,
desktop interaction, schema/type/style and architecture-delta checks. Unchanged
full profiles and cross-capability packaging/recovery/performance remain at S06
integration and fresh W2 qualification. Existing adverse evidence is retained;
no partial producer or isolated double is a real-principal PASS. No new shared
automation/framework source work is authorized or planned.

Development preflight found that an excluded citation child could reappear when
its surviving ancestor was scanned. Added authenticated original exclusion masks
and a failing authored JATS regression before remediation. Downstream scans must
not rediscover excluded source intervals; ancestor quote/context overlap remains
unavailable without exact independent coordinate proof. Regression includes a
distinct retained marker and a later correction generation. Human rematches are
consumed as separate accepted relationships in the Reader and quality workspace,
preserving original machine matching assertions and unverified claim state.

The actual rematch success regression exposed an incorrect extra permission
assumption: Reconciliation deliberately records Work aggregate rights metadata
as unknown, while its current exact-source resolver establishes permitted use.
Keep that real resolver, active-state/exact-head and document inspect/derive
checks; aggregate summary metadata cannot replace or contradict them. Preserve
the refused valid target case and verify wrong-head refusal before remediation.

Independent pre-submission review at `bbd00cb8f8d604e00058fb571ffcb471fb01d48f`
found three missed acceptance boundaries. Guided stage/Return callbacks bypassed
the correction navigation guard; test the actual ApplicationRuntime callbacks
with dirty, busy and unknown-outcome blocking signals before changing them.
Reference fallbacks rescanned a retained ancestor after child exclusion; test
excluded title/identifier spans, a distinct retained reference and a later
correction generation. Preview paging used only the accepted node count; test
a split that adds a preview-only second page while preserving the accepted head.
These are restorations within the original experience and integrity contract.
