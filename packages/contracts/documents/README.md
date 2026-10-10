# Document contracts

Acquisition location, selection and receipt schemas retain exact original-copy
provenance. The parser schemas below add staged structure under ADR-0028/0029:

| Schema | Value |
|---|---|
| `document-ir.v1.schema.json` | Ordered raw-preserving DocumentIR and quality dimensions |
| `parser-selection.v1.schema.json` | Deterministic recorded source/parser preference |
| `parse-request.v1.schema.json` | Exact protected source, producer and job/attempt binding |
| `parse-result.v1.schema.json` | Staged success, content-free failure or cancellation |
| `native-structure.v1.schema.json` | Native source element/attribute hierarchy, original byte anchors and owned decoded-text runs |
| `retained-parse-result.v1.schema.json` | Encrypted successful output receipt bound to its source and physical attempt |
| `document-structure.v1.schema.json` | Lossless structure with Core-generated revision-scoped element UUIDs |
| `document-revision-acceptance.v1.schema.json` | Exact result confirmation and expected head, with no caller-supplied actor or structure |
| `document-revision.v1.schema.json` | Immutable human-accepted structural revision, decision, source binding and identity map |
| `viewer-source-selector.v1.schema.json` | Opaque exact attachment/original and optional accepted normalized revision |
| `viewer-source-metadata.v1.schema.json` | Current full source identity, with original and normalized revisions kept distinct |
| `viewer-text-chunk.v1.schema.json` | Exact accepted element and bounded Unicode text chunk; separately governed derivation |
| `parsing-quality-report.v1.schema.json` | Read-only durable job/attempt/source/result-bound quality and review triage |
| `parsing-quality-dimensions.v1.schema.json` | Versioned separate observations; no aggregate correctness or acceptance |

Generate with `python packages/contracts/documents/generate_parser_schema.py`;
`--check` rejects drift. JSON Schema proves shape. The additional graph, mapping,
geometry, selection, producer and current authority rules are checked by Core.
The `x-research-observatory-semanticRules` inventory describes that distinction.

All values are protected research data. Worker echoes and selection records are
never grants; callers cannot name paths, repositories or parser loaders. IDs in
the IR are staged local IDs, not canonical element identities. Failed/cancelled
results contain no IR. Inspection-only fallback cannot silently become canonical.
The revision service advances the original document head only through explicit
human structural acceptance. It keeps the source-copy revision distinct from
the retained parse result and accepted normalized revision. Existing IDs and
deep links stay attached to their immutable revision; a reparse never overwrites
an earlier acceptance. Structural acceptance remains scholarly `unverified`.

See [document parsing](../../../docs/architecture/document-parsing.md) for
normalization, offset mapping, selection and protected-source boundaries.

The private native viewer protocol is described in [source viewing](source-viewing.md).
Its schemas describe values; they neither expose a public Core route nor grant
source access. Native/Core current-authority and exact-source checks remain
required at read and delivery.

Reference enrichment appends a separate encrypted `reference-collection.v1`
revision, preserving the accepted document and ordered raw reference spans.
Fields carry source spans and extracted/inferred status. Unavailable native
attributes stay missing; reported author roles require authenticated retained
native output. Identifiers reuse the existing normalizer. Exact automatic links
require agreement between the complete current sealed Work catalog and indexed
assessment; uncertain matches retain component scores and human-review state.
No enrichment creates a Work, changes a verification state or opens a URL.

`reference-enrichment-command.v1` carries opaque document/command/expected-head
IDs. Publication atomically binds ciphertext, canonical revision, human
provenance, outbox and all material inputs, including traversable manifests
beyond 64 inputs. Refresh appends a new revision and replacement propagation;
exact retries do not create duplicate history. Read/retry recheck current
Native/project/human/Intent/privacy, inspect/derive, target-source rights and
material-input freshness. The original remains transitive provenance through
the later explicit acceptance; an earlier original impact is never erased.

`reference-reader-page.v1` exposes one entry per page: at most 1,024 raw
codepoints, four identifier previews and four field previews of 256 codepoints,
four scored candidate previews and a bounded exact source anchor. Truncation
and total counts are explicit; the UTF-8 page is capped at 64 KiB. Pagination
pins the collection revision. All complete data remains encrypted. A
`reference-reader-notice.v1` contains only a current rights-fenced opaque head
and content-free unavailable/resource-limit status, allowing an explicit CAS
refresh without exposing a stale collection. Reader admission includes these
artifact, catalog and publication allocations. Unknown issued Native failures
retain admission until physical settlement; lock/close clears visible previews.

[Citation contexts](citation-contexts.md) describes `citation-collection.v1`,
the opaque enrichment command and bounded Reader page/notice schemas. Contexts
bind exact current references and accepted source locations; reported,
inferred, ambiguous and unresolved observations remain distinct and unverified.

[Tables and figures](table-figures.md) describes protected collections,
extraction/exclusion commands and bounded Reader page/notice schemas. Exact
source relationships, sparse cells, original-page previews and uncertainty stay
unverified; explicit human exclusion appends history and preserves the parse.

`parsing-quality-report.v1` is a read-only projection for the Native-only
`/native/document-revisions/parse-quality` query with an opaque job ID and current
project session. It separately exposes retained text/page coverage, encoding,
reading order, section/reference/block expectations, anchors, unresolved
references, node/cell confidence, geometry and parser warnings. The exact source,
selected producer/input/selection digests, current physical attempt and nullable
retained result are bound; pending, failed and cancelled jobs never invent IR.
Partial retained output can be diagnosed before any human acceptance.

Coverage of normalized projection codepoints measures representation within
the retained IR, including its overlapping native projections. It does not prove
recall of original source text. Source-page coverage uses retained page geometry
and nonempty text-bearing page locators; no-page formats report not applicable.
Expected sections/references/blocks require namespace-aware observations in the
exact authenticated native artifact. Without that basis expectations stay
unknown; absent sections or references alone do not imply a broken document.

Confidence state counts preserve reported, unknown, not reported, not applicable
and unavailable observations. Parser table observations remain separate from
cell observations. Reported values below 0.8 only trigger versioned review
reasons, and no combined correctness score is returned. Human inspection and
explicit acceptance retain authority. Warning codes/counts exclude raw details.
Re-evaluation uses `parsing-quality-definitions-1`/`parsing-quality-triage-1` and
does not modify source, original IR, accepted revisions, heads or provenance.

Current Native/human/Intent/privacy and exact-copy inspect/derive rights span
report construction and delivery. Existing cumulative artifact admission runs
before reads, the diagnostic limit of 10,000 items runs before flattening,
the operation has a five-second cooperative deadline and reports are capped at
64 KiB. Resource, stale-session, stop-latch and authority failures are content
free. Desktop display/correction integration belongs to CAP-05.S06.T02.

The additive `document-correction-*` v1 schemas describe closed typed patches,
save/discard commands, exact explicit acceptance, protected human drafts and
bounded queue/page/impact/current-Work projections. Native owns all runtime and
principal authority. Expected base/old-value hashes are selectors and CAS inputs,
not permissions. Saved or previewed operations do not update the accepted head.
Only explicit acceptance appends fresh canonical identities, human provenance,
dependencies and an impact event while preserving original parser observations.

Human labels and reference selections remain separate accepted metadata in the
Reader and Parsing Quality. Work targets retain their exact current revision and
unverified state. Corrected source lineage authenticates original parser
relationships before remapping identities; excluded source intervals cannot be
rediscovered by ancestor scans. Citation `excluded-region` context denotes an
unavailable quotation/context, not an empty or verified passage. Historical
source anchors remain immutable. Protected accepted read-back replays the exact
proposal, result, author/rationale and acceptor binding under current authority.

Requests admit at most 32 operations within 64 KiB; protected records and responses
are capped at 128 KiB. A page exposes 20 nodes with 160-codepoint previews, ten
saved proposal selectors and ten current permitted Work choices per target page.
Impact is prospective and rechecked at acceptance; recalculation is separate.
Transformation/read bounds include 10,000 items, one million text codepoints,
32 generations and a five-second cooperative deadline. Unknown issued outcomes
retain exact command identity for reconciliation. Component doubles establish
UI behavior only; task-owned synthetic Wry/Core checks do not qualify parser
models, a packaged installation, hardware tiers or Wave release.

The additive `document-reprocessing-*` v1 schemas describe batches of at most ten
documents, bounded old/new comparison pages, complete correction obligations and
separate explicit per-document acceptance. Batch submission and comparison do
not accept parser output. Every new replacement of a normalized head uses this
path; initial ordinary acceptance and exact historical retries stay compatible.
Each retained correction generation must be explicitly mapped to the exact new
candidate nodes/references. Original operation digests, new result/job/physical
attempt/selection, all mapped values, rationale and current actor bind the saved
plan and its confirmation. Complete server counts block acceptance despite
pagination or unseen candidate nodes. No aggregate scholarly confidence exists.

Canonical IDs are fresh. Exact quote and context candidates are advisory:
unchanged/moved, missing and ambiguous anchors stay distinct, and old anchors
never move. Original source, parser output, accepted revisions and human history
remain immutable. One current-source-fenced writer publishes the machine base,
mapped saved corrections, human decisions, final head and graph impact. Normal
accepted and correction readers authenticate that compound result after reopen.
Historical inputs are non-material, so new accepted objects do not stale
themselves; only graph-connected material consumers receive stale/unknown facts.

Small impact completes in the writer; larger impact exposes a run/checkpoint
for explicit resume. Read-impact recovers an accepted item's original batch
binding from a later cancelled/continued batch. Retrying an already-advanced
authenticated checkpoint returns current readback without applying another chunk.
Cancellation stops future items and retains completed per-document decisions.
Unfinished old-session work needs a new explicit immutable command/job under
current Native authority; no security-lock continuation or acceptance is automatic.
Unknown issued mutations keep their exact payload for explicit reconciliation.
Exact create/continuation retries authenticate the current batch successor and
return its immutable facts without resubmitting superseded inputs. Each missing
job is admitted only after its exact active batch/item/input and current base are
checked in the same source-fenced queue writer. Cancellation cannot win that
check and leave a later unsubmitted job silently admitted.

Known pre-publication denials return content-free 409 responses. Once publication
may have completed, an unconfirmed commit, projection, attachment or delivery
returns content-free 503; Native treats that issued mutation as unknown and keeps
the exact payload. Explicit retry authenticates the retained result and creates
no duplicate plan, decision or job.

Current human/Intent/privacy, original-copy inspect/derive, exact Work authority,
stop and resource fences apply through response delivery. Protected reprocessing
records have an 8 MiB cap; commands 64 KiB and responses 128 KiB. Comparison is
bounded to 10,000 retained model/collection items, one million retained string
codepoints and one million cumulative span codepoints before detached copies
(including nested cells, warnings, contributors and overlapping spans), 32 correction
generations, 32 operations per generation and five-second cooperative work.
Retained-IR text comparison is not proof of extraction recall from the source.
One cumulative protected-artifact read ledger starts before source discovery,
including queue pages. Discovery and queue reserve no source decoder; selected
document actions tighten the existing allowance to the authenticated source
size while retaining every prior artifact charge. Admission precedes each
protected adapter read, and nested validation cannot reset that spent budget.
Authored parser fixtures plus real Native/Core/vault/SQLCipher checks establish
these boundaries without claiming installed parser, hardware or shipping proof.
