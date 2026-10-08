# CAP-05.S03.T01 — immutable normalized document revisions

Claim base: `d0752c3d0aac0162ada79effc41b88c9d2978bcf` on the existing
`codex/w2-implementation` campaign. Dependencies CAP-05.S02.T03 and
CAP-02.S02.T03 are DONE and independently approved; CAP-05.S02 is also approved.
Authority is the W2 packet at `c85a59f3a293f8e3f2eaf6454682c9a14b1efa55`,
the approved CAP-05.S03 plan section 9.1, and ADR-0013/0024/0025/0029.
This worksheet is prospective implementation planning, not approval or proof.

The current implementation retains encrypted raw parser artifacts and validates
an in-memory neutral IR. It does not durably retain accepted normalized structure
or advance the original document through explicit structural acceptance.

| Material boundary | Required behavior | Selected proof |
|---|---|---|
| Reparse, identity and restart | Only explicit trusted human acceptance appends the original document aggregate. Keep its source revision distinct; prior accepted revisions remain queryable. Core mints revision-scoped UUIDv7 element identities and remaps hierarchy, projections, references, citations, tables, figures and quality links. | Two accepted parses, reopen, stable exact-revision IDs, disjoint IDs between revisions, preserved raw/NFC/code-point mapping and source geometry; stage/reject do not advance the head. |
| Complete protected result | Persist encrypted normalized output bound to exact source, request, producer/config/assets, physical job attempt and raw receipts. Accept only the authenticated successful output. Inspection-only, partial and missing-text results cannot become accepted structure. | Durable output/restart without reparse; partial, textless, inspection, cancelled/failed, changed producer/source/job/attempt, missing receipt and corrupt ciphertext denials, preserving the head. |
| Human authority and semantic replay | Recheck current rights, Intent/privacy, actor and native session before any protected read or replay. Bind the complete retained result and expected base to acceptance. | Exact retry returns the same revision/decision/IDs and no extra events; changed semantic command conflicts; concurrent equal-base acceptance has one winner; worker/model and stale authority denials. |
| Atomic publication | Accepted structure, nodes, decision, canonical revision, provenance, dependencies, scoped change event and outbox commit together. | Inject precommit failure and verify no partial head, nodes or events; valid retry succeeds. Protected object cleanup preserves pre-existing shared bytes and older attempts. |
| Live parse workflow and admission | Reserve actual parser resources before the exact fixed eligible activity claim; retain lighter metadata demand and one shared controller/policy. Enforce one parser across projects. Heartbeat/poll outside canonical writers; inside writers use only latched stop plus current durable lease/rights/session fences. | Focused immutable map/filter/max-demand/no-claim/release/two-project tests; actual eligible-host native parse exceeding 30 seconds with live heartbeat and an intervening canonical write. This is workflow composition proof, not a timing-budget rerun. |
| Literal predecessor and recovery | Capture populated literal v25 before schema edits. Preserve all old rows/history and ciphertext. Apply a forward-only additive migration with verified backup and deterministic interruption rollback. | New v25 fixture capture and extracted-byte/row authentication; interruption at each material v26 step, unchanged literal v25 and ciphertext after failure, successful retry/reopen. Existing v24 fixtures and historical adverse evidence remain unchanged. |

Read-only adversarial preflights are retained in ignored local artifacts:
`artifacts/tmp/CAP-05.S03.T01.security-design-preflight-c11-01.json`
(SHA-256 `e8e824d67905737cd9f4e028dc15f3548e144dddaa5d580dddc847f07d7c2261`)
and `artifacts/tmp/CAP-05.S03.T01.admission-preflight-c11-02.json`
(SHA-256 `940ac3096899741afce017e25a5a13a08c77fef7a1f4b86e66892fc1fd2782a5`).
Their material rows are incorporated above; neither is independent disposition.

The conservative current-host policy requires four parser CPU slots plus one
interactive slot. A four-slot capacity observation must safely leave parsing
unclaimed. Qualification of the planned four-core tier remains an explicit
unresolved W2 obligation; this task must not imply that it is qualified, invent
smaller accounting, tune the native runtime or repeat the accepted overage.

The owner accepted exactly the prior 62.5333542-second warm p95 observation on
October 7. Its original aggregate FAIL and thresholds remain preserved. No work
in this task is selected to investigate, optimize or remeasure that deviation.

First checks cover new persistence/authority rules and existing admission
behavior before product edits where practical. Selected follow-up checks include
affected parser/workflow/repository/migration integrations, contract/schema,
lint/format/type and architecture checks. Full documents/data profiles, clean
packaging and the broader cross-capability matrix remain slice/checkpoint/W2
qualification coverage unless a concrete failure requires earlier expansion.

Governed experience: no visual or interaction reference change in T01; native/Core
commands and protected backend persistence implement the already approved
acceptance boundary. Anchor interaction/resolution belongs to S03.T02/T03;
viewer and quality workspace delivery belongs to S04. No new parser, OCR,
cloud service, scholarly-verification decision or automation-framework work.

Required expanded independent task review remains pending. No new mandatory
approval gate was discovered for implementation on the actual eligible host.

Independent pre-disposition finding F01 at candidate
`a323add851fd2c3882e9b5a35b328d4d2577c3e7` exposed a missed bounded-writer row:
the element-index routine rescanned and removed pending nodes although the IR
already guarantees parent-before-child order. A valid chain caused quadratic
parent visits during acceptance and each protected read. Preserve the finding
and the reviewer's adverse setup observation in
`artifacts/tmp/CAP-05.S03.T01.independent-pre-disposition-finding-56.json`.
Add a large valid chain/flat counting regression before changing the routine
to one validated-order pass; replay real persistence and atomic-failure checks.
This corrects the new product writer, with no parser timing or framework work.
