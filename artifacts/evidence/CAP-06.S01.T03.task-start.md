# CAP-06.S01.T03 — search API and result view acceptance closure

Claim base `a6e2b9146f788d489006998fccb0669bfba91bc7`; owner
`codex-w3-implementation`. Authority is the immutable approved W3 packet
`d91e6b3b280e082f824498cbd06cfa5fd09b8f1d`, the four backlog criteria and
[approved S01 task](../../planning/slice-plans/CAP-06/CAP-06.S01-fielded-lexical-search-and-local-indexing.md),
Accepted ADR0025/0057, CAP06-D01/D06/D07/D08/D14/D15, and approved
RO-UI-ACADEMIC-MINIMAL-1.10. T02 is DONE and locally integrated. This is
implementation planning, not evidence that the prospective checks passed.

| Material outcome or boundary | Implementation and selected proof |
| --- | --- |
| Criteria 1/4: lexical rank, fields, filters and known items | Preserve item-level Boolean set membership across lawful rows. Version fixed field weights and sum the best row BM25 component per distinct positive leaf; repeated identical leaves do not multiply rank. Negative/filter-only matches have neutral score. Sort by descending finite relevance component then exact item ID. Explain actual leaf/field/filter contributions as method scores, never probabilities. Test cross-row AND/OR/NOT, repeated rows/leaves, missing years, pure negatives, field weights, ties and complete pagination. |
| Complete lawful statistical universe | Before BM25, validate every indexed row against the current permitted canonical projection, including nonmatching items; hit-only authorization cannot protect corpus-wide statistics. Reuse T02 complete capture initially. Bind current actor/Intent/policy/session, generation/selection/projection, source watermark, lifecycle/key and earliest whole-corpus rights expiry; fence again before commit/delivery. Test revocation, expiry without writes, substitution and delivery races. |
| Executed observation and durable ownership | Add a strict protected immutable SearchRun subtype using the existing canonical workflow-aggregate pattern, separate from queue job/attempt identity. Retain validated original/normalized/AST query, versioned rank/filter configuration, exact input identities and actual outcome digest/count. Use the existing admitted workflow queue/supervisor for preparation/execution that may outlive a request, with atomic accepted output/provenance/outbox completion. OperationRegistry remains a projection. Test durable acknowledgement, idempotency/lost response, cancellation versus commit, lock, expired attempts, restart and owned drain. |
| Input history and schema predecessor | Preserve v29 migration modules, imported DDL, target hashes and all outbox/search-change history. Any additive current migration introduces typed run storage and a narrowly authenticated observation classification, including actual non-NULL workflow completion outputs. Unknown/mixed/source/rights events still invalidate. Test Run A/Run B between pages, forged classification, genuine drift, exact v29 preservation and interrupted rollback/retry. |
| Exact bounded snippets and source return | Verify highlights against authenticated projection text and codepoint offsets. Bound snippet/explanation counts and serialized page bytes together. Never interpret FTS markers as HTML or invent node IDs. Only existing real-node-contained selections can become anchors; otherwise use an explicitly unanchored preview and exact source-revision inspection. Test repeated/adjacent/uncovered text, hostile markers/markup, diacritics, astral/combining/CRLF, large tokens, truncation and denied full text. Reader's distinct document-analysis rights remain required. |
| Stable page identity and current authorization | Cursor binds canonical executed run/configuration/input/result identity and the exact last score/item key. Recompute against unchanged inputs as necessary, validate actual last membership, and reject drift rather than mix pages. Test complete concatenation, ties, varying page size, modified/cross-run/project/actor cursors and rights changes. |
| API and real principal | Keep query/rank/run ports independent of the UI. Add strict bounded HTTP DTOs, generated TypeScript client and exact Rust request/response admission. Preserve all previous 102 operation identities. Prove current-user DPAPI/SQLCipher through authenticated loopback and generated client → real Rust supervisor → Core; include invalid and oversized requests. Fixtures alone do not prove this boundary. |
| Approved desktop journey | Separate draft/validation/explicit execution; disclose lexical-only, semantic-unqualified and rerank-not-run states and actual index/input identities. Parent-held, bounded authorized memory preserves query/filter/page/row/focus across exact Reader return. Cancel/replacement/lock/project change/expiry discard late private results. Test production-built renderer keyboard, paging/explanation, denied/stale source and return; declare controlled response fixtures separately from native proof. Preserve all 14 semantic workflow keys. |

The synthetic technical lookup frame was authored before product implementation:
`tests/search/fixtures/synthetic-known-items.v1.json`, raw SHA256
`62f37a7259351dfa82c9ea1f2de8148d9e299c6c6db27cad16a903ee45a9ae32`.
Its 64 artificial records include 4 development records, 32 held-out records
and 28 distractors. All 64 held-out title/DOI queries remain in the denominator;
bind Core-minted IDs before lookup and preserve every failure. Recall@20 target
is >=0.90; report title/DOI strata separately. This does not qualify scientific
relevance, systematic coverage or semantic retrieval.

First checks target protected ranking/snippets and the actual canonical
authority/run lifecycle before adding transports and UI. Select affected search,
migration/rights, API compatibility/generation, native admission and supervised
Core, desktop build/types/interactions. Slice workload and broader packaging,
repository/profile and Wave qualification remain separate, with fresh checks
at their owning stages. No performance result is asserted here.

Both independent read-only preflights were incorporated: authority advisory
`artifacts/tmp/CAP-06.S01.T03.authority-preflight-01.json` SHA256
`f0a195ed2550221c2850e47ab58b82ce3f99a856394d5f65f85c6d1ce82d6508`,
query/experience advisory
`artifacts/tmp/CAP-06.S01.T03.query-experience-preflight-01.json` SHA256
`586126258852818d14474ace7e1655979dcace4c3be614fbba16706c79f73a76`.
These are advice, not formal dispositions. No mandatory human gate was found.

Non-goals: AI mode/launcher, semantic models, full hybrid replay (S03), branch
expansion/full Search Studio (S04), hosted deployment or release approval.
Frozen Wave estimate P=924 effort-hours includes planned refactoring 28 once;
prior supplemental R=0. T03 has approved 20/planned 0. No supplemental cleanup
is selected. These are allocations, not measured actual effort; any supplemental
allocation or overrun must be itemized cumulatively before commitment.

## Current-authority closure during implementation

Read-only advisory `artifacts/tmp/CAP-06.S01.T03.warm-read-authority-advisory-01.json`
SHA256 `eb5938476563c590dabe5138751632902a8791ccbdd2150f65ed15309d679be6`
identified current import draft and object-state writes without outbox events.
The implementation now selects a narrow append-only canonical source epoch,
advanced transactionally by draft, record-decision, preview-state and material
object-state writes. Audit verification timestamps alone do not advance it.
Query, commit and delivery bind that epoch alongside the actual lexical input
head. Trusted-time checks reject rollback and changes across recorded permission
activation or expiry. Add real non-outbox import/object regressions, preserve
all earlier failed checks, and freshly replay v29 migration/rollback checks for
the additive current schema. This is implementation closure inside the approved
rights and current-input contract, not a new approval or a warm-read certificate.

The initial delivery path retains complete current capture and exact result
comparison. No scale/latency claim follows from the small fixtures. Search is
exposed through fixed `/projects/search/` Core operations and generated client
contracts. Core resolves the accepted current Native session, as for corpus
operations; request bodies cannot claim an actor or session. The existing
document pump and admission controller own preparation/execution and shutdown.
The UI consumes these same API ports; future AI mode remains unplanned.

## Additional boundaries exposed by development checks

The public API compatibility check compares every predecessor schema and all
102 earlier operations against claim base `a6e2b9146f788d489006998fccb0669bfba91bc7`.
It caught a new search score alias renaming an earlier reconciliation schema;
the search-specific `LexicalScore` name restores that compatibility. Six search
operations are additive. Regeneration and the complete comparison are required
again for the committed candidate.

The production renderer journey must also cover lost execution acknowledgement
with exact-command replay, failed pending-status polling with an explicit retry,
an already-completed execution acknowledgement, and delayed anchor replies after
navigation or lock. These material paths supplement the original journey row;
controlled browser replies are not proof of actual Native/Core authority.

Actual Native development checks exposed a project mutex held across the entire
indexing activity. Search orchestration now leaves long work outside that mutex;
individual canonical reads/writers and final publication retain current Native,
actor, source, cancellation and lifecycle guards. The existing admitted runner
continues to own real drain. A protected Core phase barrier tests foreground
same-command replay, status and cancellation, rejection of late output, and a
fresh successful command. Existing direct index callers retain their original
whole-command guard.

A later actual Native check still timed out. The content-free diagnostic
`artifacts/tmp/CAP-06.S01.T03.native-phase-diagnostic-03.jsonl` measured the
explicit TRUNCATE checkpoint at 0.00131 seconds, SQLCipher connection close at
2.91208 seconds and a concurrent Python heartbeat gap of 2.92212 seconds.
Those are diagnostic observations, not qualification or a performance waiver.
They require a bounded close-path correction and fresh actual Native replay;
the existing exact file/sidecar lifetime protections, key ownership, normal
cleanup and transport deadline remain the current test conditions. No human
gate or successful Native boundary is asserted from this failed trial.

The close correction uses a temporary genuine read-only SQLCipher companion
after a successful TRUNCATE checkpoint. It holds a real reader under the same
file identities and current key lease; writer and companion both close before
the existing guard/key cleanup. Persistent WAL mode, dependency and transport
deadline remain unchanged. Add real foreground-progress/reopen, read-only-write
denial, rename denial during consumption, setup/read failure drain and revoked-key
tests. Preserve the earlier failures and diagnostic limits. The unwrapped Native
development journey subsequently passed, but exact-candidate proof is still due.

The architecture check exposed concrete storage dependencies in unfinished
business/API modules. Pure command/activity ports now separate HTTP and worker
orchestration from the six exact new root adapters; only `main` composes the
Native-scoped repository. Move the SQL input-history helper out of the pure
query domain. Keep one pure failure class with the identical prior re-export.
Root-only positive and business/port/alias/nested-impostor negative tests preserve
the existing detector. Documentary ADR0061 records this implementation under
Accepted ADR0001/0010/0025/0057, without granting new authority.

Storage compatibility checks also exposed a stale current-version guide and
generic column names in the unpublished schema30 prototype. Preserve the existing
scalar/domain-subtype assertion. The new typed columns are `manifest_json` and
`run_json`, with the same closed-body and source/principal bindings. Refresh only
current30 fingerprints; published29, all frozen fixtures and58 historical recovery
branches remain unchanged. Extend predecessor-to-current expected chains/history
through30 while retaining exact29 hashes, rows/cells/objects and failure assertions.

Task proof includes the actual204-artifact production build, all185 pinned PDF
resources, current approved1.10 binding and real assembler rejection of missing,
extra, obsolete, changed pinned-resource and leaked fixture artifacts. Preserve
the unchanged shared desktop helper's stale inventory/reference failures as FAIL;
the separately named task-owned checks do not claim a shared profile PASS.
Actual browser journeys and Native authority remain separate required proofs.

Full100k metadata and100k permitted-passage measurements remain S01 slice
obligations. The scale advisory identifies repeated canonical opens and complete
policy scans as static risks, not measured infeasibility. No warm certificate,
latency result, resource-fit claim or performance waiver follows from small
fixtures. All qualifying task checks will bind the committed candidate freshly;
broader slice/checkpoint/Wave checks remain at their owning stages.
