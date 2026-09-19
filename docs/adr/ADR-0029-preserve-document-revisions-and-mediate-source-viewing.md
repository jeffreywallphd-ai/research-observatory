---
id: ADR-0029
title: Preserve document revisions and mediate source viewing
status: Proposed
date: 2026-09-13
deciders: []
linked_tasks:
  - CAP-05.S02.T01
  - CAP-05.S02.T02
  - CAP-05.S02.T03
  - CAP-05.S03.T01
  - CAP-05.S03.T02
  - CAP-05.S03.T03
  - CAP-05.S04.T01
  - CAP-05.S04.T02
  - CAP-05.S04.T03
  - CAP-05.S06.T02
  - CAP-05.S06.T03
decision_scope: W2 parser/runtime selection, document IR, immutable source selectors, human corrections and protected viewer transport; no evidence acceptance by parsing.
affected_paths:
  - services/core-api/src/research_observatory_core/documents/**
  - services/core-api/src/research_observatory_core/anchors/**
  - services/core-api/src/research_observatory_core/parsing/**
  - apps/desktop/src/**
  - packages/contracts/documents/**
  - packages/contracts/anchors/**
supersedes: []
superseded_by: null
---

# ADR-0029: Preserve document revisions and mediate source viewing

## Context

W2 must turn lawful originals into inspectable structure without losing original
bytes, source locations, rights or researcher decisions. Reuse ADR-0013/0024
identity/provenance, ADR-0016/0017 protected object reads and ADR-0025 jobs.
The current object port exposes verified sequential reads, not paths or seek.
It authenticates the entire source before returning a stream and holds a metadata
transaction until close; a long-lived viewer must not hold that transaction open.

The [Docling 2.126.0 package definition](https://github.com/docling-project/docling/blob/v2.126.0/pyproject.toml)
supports modular PDF/local-model dependencies. A planning-only Windows x64,
Python 3.14.6 wheel resolution succeeded for the selected extras with CPU Torch;
no package/model was installed or executed. See the W2 assessment for probe scope.
Docling's [offline options](https://docling-project.github.io/docling/usage/advanced_options/)
require deliberate asset preparation; disabling remote services alone does not
prove that first use will avoid model downloads.

## Candidates

1. Native structured parsing plus pinned local Docling and a versioned neutral IR:
   retains scholarly layout and a replaceable parser port, but needs model/runtime
   packaging, resource and quality qualification.
2. Lightweight PDF text extraction only: smaller runtime, but discards the planned
   table/layout outcome. Not selected as a hidden scope reduction.
3. Hosted document conversion: reduces local inference cost but conflicts with
   offline/default-private operation and adds service/egress authority. Not selected.

For viewing, compare a Core-authenticated range adapter over verified sequential
reads against a new seekable encryption format. The former preserves existing
bytes and migration guarantees but can repeat full-file work; the latter would
expand storage/migration scope substantially. Direct decrypted paths are invalid.

## Decision

Recommend candidate 1. This **Proposed** record is not execution authority.

### Parser and immutable structure

Use secure native JATS/TEI/XML/HTML parsing where available; retain unsupported
blocks and format warnings. Disable external entities, network resolution, active
HTML, macros and unbounded archive expansion. For PDF use
`docling-slim[convert-core,format-pdf,format-docx,models-local]==2.126.0`, initially constrained
to `docling-parse==7.16.0` and `docling-ibm-models==4.0.2`, in the separate
ADR-0028 CPU worker. This is the modular distribution of Docling, not a replacement
parser or a new dependency in Core. Pin the complete qualified worker lock.

Package only selected layout/table assets with exact upstream revision, digest,
license and notice inventory. Runtime uses a read-only artifacts directory,
offline hub settings and denied network; missing assets return an actionable
local error, not an implicit download. OCR, VLM, remote serving and document-provided
plugins remain disabled by default. A scan with no usable text remains visible
as incomplete, not an invented extraction. Select Heron layout and TableFormer
accurate with cell matching; disable picture/code/formula enrichment. The exact
revision/file/digest/license inventory is in
[W2 feasibility](../../planning/W2-feasibility.md#cap-05s02t03--offline-asset-selection).
Those publisher-reported digests must be checked against downloaded build inputs;
they are not a claim of locally verified weights or distribution qualification.

The planned CPU parsing tier is Windows x64 with 16 GiB RAM and 4 logical cores;
8 GiB remains the metadata/review tier, not an unqualified parsing promise.
Admit one parser at a time, at most 4 CPU threads, 4 GiB private committed memory,
128 MiB input, 500 pages, 40 million decoded pixels per page and 64 MiB serialized
IR (binary derivatives separately bounded). Limit wall time to 15 minutes; reject
oversize input safely and retain usable metadata/original without partial canonical
structure. Cancellation requests cooperative stop, then terminates the owned job
within 5 seconds if it cannot stop; a later retry creates a new attempt.
Benchmark 10-page born-digital two-column/table fixtures: planned p95 <= 60 seconds
warm and <= 90 seconds cold, with actual hardware, sample count and resource peaks
reported. These are qualification targets, not measured performance. The limits
must be enforced by job admission/containment, not merely parser flags.

The neutral IR records original object digest, parser/config/asset versions,
ordered blocks/sections, raw text, references, tables/figures, source page dimensions
and rotation, coordinates and separate quality warnings. Define one normalization
version and half-open Unicode-code-point text offsets; no offsets into an
unstated normalization. Preserve raw text alongside the normalized projection.
Downstream canonical IDs are Core-generated, not Docling node IDs.

Anchors bind immutable revision ID, structural block identity, page/region,
text position and quote/context selectors where available. Exact revision is
authoritative; candidate matches on a later revision are suggestions. Missing or
ambiguous matches stay visible. Correction drafts and reparses create new versions;
only explicit human acceptance advances the accepted head and emits scoped
staleness. Preserve original/machine/corrected views and prior deep links.
The already forecast minimal text/page fallback is inspection-only, also isolated
and explicitly degraded; it is not a substitute for qualifying Docling or a path
to accepting incomplete structure. No additional fallback runtime is selected.

### Source viewer

Use a locally bundled, pinned PDF.js worker and inert structured-text view.
[PDF.js range transport](https://mozilla.github.io/pdf.js/api/draft/api.js.html)
permits a custom byte provider. Renderer requests contain opaque revision IDs
and bounded ranges through the authenticated local Core gateway, not a raw URL,
filesystem path, source credential or unrestricted Tauri command. Core resolves
project/session/document authorization and current rights for every request.
Validate integer ranges/length, response limits, cancellation and stale sessions.

The smallest candidate opens the protected source, discards any prefix in bounded
chunks, returns the requested bytes and closes promptly. It preserves full-source
authentication and encrypted-at-rest format; it does **not** provide O(1) seek.
Disable automatic whole-file prefetch and streaming in the PDF.js range integration;
virtualize page/text rendering, cancel obsolete requests and release buffers at
project close/lock. No long-lived database read lease, plaintext disk cache,
eager whole-file fetch or duplicate source-sized application buffer is selected.
Range fetching does not eliminate PDF.js's worker source-length allocation:
the [v5.4.149 implementation](https://github.com/mozilla/pdf.js/blob/v5.4.149/src/core/chunked_stream.js#L19)
allocates it independently of automatic fetching. Permit that allocation only
within the source cap and aggregate budget below. This inspected version is
evidence of allocation behavior, not the selected shipping dependency pin;
qualify the exact pinned build and terminate its worker on project close/lock.

Select that adapter first, informed by the bounded real-storage
[probe](../../planning/W2-feasibility.md#cap-05s04t01--protected-range-cost), not an
encrypted derivative cache. Admit sources <= 128 MiB and ranges <= 1 MiB, with one
active source read per project and a bounded queue of 8 requests; coalesce duplicate
ranges and cancel obsolete work before admission. Copy only the requested bounded
range, close the stream/transaction, then deliver to the renderer. Interleave
metadata writes between range operations; a viewer cannot monopolize the writer.
Larger or over-budget sources show an actionable limit, retaining their metadata
and original; never add an unaccounted main-thread source copy.

The current verified-open implementation has no cancellation checkpoint during
full authentication. CAP-05.S04.T01 includes a backward-compatible cancellation
hook in that read loop and prefix discard, checked between bounded chunks with
rollback/close on cancellation. No bytes may be exposed before authentication
completes. Do not pretend dropping a renderer promise cancels Core work, forcibly
terminate a database thread, or release an in-use lease. Lock/close cancels queued
work, denies delivery immediately and drains owned reads; qualify <= 1 second
cancellation/lease release at the supported maximum with concurrent writes.

Retain the representative open-to-first-page target <= 1.5 seconds after Core
readiness, using a 10 MiB / 50-page born-digital PDF on the declared Windows tier.
Measure cold/warm p95 over at least 20 opens, and a 128 MiB / 500-page stress fixture,
including full authentication, renderer/gateway and memory. Enforce bounded
page/thumbnail rendering and a 256 MiB aggregate viewer-owned buffer budget,
including the worker source allocation, in-flight range/transfer copies, decoded
page surfaces and thumbnails; no eager per-page rendering. Reject or release
owned work safely before exceeding admission limits. Measure the complete viewer
and worker resource footprint, not only application-side arrays. The synthetic
storage observation does not pass these checks.
If the adapter cannot meet them, stop only that design boundary and propose an
explicit successor (for example encrypted derivative chunks with recoverable
eviction), not an unapproved cache/cryptosystem or relaxed target.

Disable PDF scripting/XFA/actions/attachments and remote asset fetches. All copy,
print, external-open and export commands go through action-specific rights checks
and explicit destination selection where required. Keep copied text out of audit
logs; permitted quotations carry source identifiers. Application controls do not
prevent a researcher taking a screenshot or using an already authorized export.

### Acquisition, normalization and quality decisions

- Core receives local selections as validated streams, never renderer-selected
  unrestricted paths. Encrypted staging is quarantined until bounded format checks
  complete in the qualified ADR-0028 worker. Use an explicit signature/MIME allowlist
  plus format structural checks (PDF header/trailer, ZIP inventory for DOCX, secure
  XML root, bounded text decoding), not extension or remote Content-Type alone.
  Prefer these bounded checks over a new general-purpose libmagic runtime. Reject
  executables, encrypted/password-protected documents and unsafe archives with a
  safe error; no password retention or macro execution. Rejected content has no
  canonical association; clean only the owned staging object through existing GC.
- Acquisition uses the same DNS/redirect/TLS broker boundary, no browser cookies,
  paywall bypass or credential forwarding. Apply the 128 MiB source cap to both wire
  and expanded content, at most 5 redirects and a 120-second transfer deadline.
  Select a permitted location explicitly; preserve source, license, content digest
  and human-confirmed uncertain associations. Resume with validated ETag/range
  identity or discard the owned partial and restart; never concatenate changed
  content. A failed acquisition leaves its metadata record usable.
- IR normalization `ro-text-nfc-1` applies Unicode NFC and CRLF/CR → LF only;
  preserve whitespace and raw text with a source-offset mapping. Half-open offsets
  count Unicode code points, not UTF-16 units or bytes; renderer conversion is
  explicit. No implicit dehyphenation, case-folding or ligature rewrite in anchor
  identity. Structured selection is native JATS/TEI/XML/HTML first, PDF Docling next;
  DOCX uses the isolated Docling conversion path, TXT bounded decoding. Unsupported
  elements retain type, source location and raw text rather than being dropped.
- Same-revision structural/text/page selectors resolve deterministically. A later
  revision offers an exact-quote/context candidate only if unique; fuzzy matching
  is advisory and cannot move accepted evidence. Missing/ambiguous context is a
  visible repair state. A correction is a typed patch over an exact base revision
  with expected old values, actor and rationale; conflicts refuse an in-place edit.
  Acceptance atomically appends the new revision, accepted-head decision and scoped
  dependency event. Select batch preview with independent explicit per-document
  acceptance, rather than a batch-wide head-switch transaction. Each acceptance
  revalidates its exact base, current rights and researcher authority and commits
  revision/head/event atomically. Interruption preserves completed acceptances;
  failed or unaccepted items retain their old heads. Resume revalidates remaining
  items and surfaces changed-base conflicts, never silently retries acceptance.
  Show per-document outcomes; no implicit or automatic bulk acceptance. Verify
  cancellation between acceptances, failed acceptance rollback, concurrent-base
  conflict and restart without duplicate dependency events. This avoids a large
  batch transaction while retaining deliberate, inspectable partial completion.
- Reference entries retain ordered raw strings and identifier assertions; exact
  unique IDs may link under ADR-0027, all other matches remain review candidates.
  Citation contexts bind the marker, target candidate set and exact source range;
  unresolved styles are explicit. Tables preserve row/column indices, spans, raw
  cell text and anchors; figures retain caption/page-region and protected preview.
  No OCR/picture interpretation is selected in W2; scans remain incomplete and
  inspectable. A visual preview or extracted numeric cell is never verified evidence.
- Quality reports separately expose missing text/pages, replacement characters,
  reading-order warnings, anchor coverage, unresolved references and table-cell
  confidence/geometry warnings. Missing text on a page, broken/ambiguous anchors,
  absent expected blocks or parser failure route to review; unavailable model
  confidence remains unknown. Numeric extraction confidence < 0.8 is a triage signal
  only, not a cross-model probability or acceptance threshold. Reference/reading-
  order/table correctness uses human-labeled fixture expectations; no aggregate
  score automatically advances scholarly state. Human inspection/correction remains
  available regardless of the score. Freeze fixture labels before tuning thresholds.

## Consequences

Originals and accepted evidence survive parser replacement. Additive Core
schema migrations retain original revisions, provenance and rights; rollback
retains verified ciphertext and never relabels a new revision as an old one.
An incompatible IR/selector change needs a versioned migration and ambiguity
report, not silent offset repair. Parser failure or cancellation discards only
uncommitted outputs; source and metadata remain usable.

Local CPU dependencies/assets add installation size and cold-start cost. Windows
wheel resolution is not runtime, LPAC, packaging, licensing or performance proof.
The bounded probes support the selected planning direction, not implementation
qualification. Independent architecture/packet review and human acceptance are
still required; production qualification is not waived by G1.

## Verification

Use versioned lawful/synthetic fixtures for two-column text, tables, citations,
rotated/scaled pages, Unicode normalization, structured unknown blocks, scans,
malformed/hostile inputs and oversized resource requests. Verify offline packaged
conversion, no plaintext temporary output, missing-assets behavior, cancellation
and restart under ADR-0028. Compare deterministic structure/anchor expectations
and publish separate quality dimensions; no fabricated gold labels.

Viewer proof covers first page and distant ranges, exact revision/deep links after
relocation, cross-project/session denial, changed rights, corrupt/missing source,
closing during requests, inert active content, accessible focus/keyboard/reflow,
and alternate action paths. Report representative and large-file warm/cold timing
and peak memory with full source verification included. No mocked stream or
screenshot alone proves the protected boundary.

## Task links

- `CAP-05.S02.T01`
- `CAP-05.S02.T02`
- `CAP-05.S02.T03`
- `CAP-05.S03.T01`
- `CAP-05.S03.T02`
- `CAP-05.S03.T03`
- `CAP-05.S04.T01`
- `CAP-05.S04.T02`
- `CAP-05.S04.T03`
- `CAP-05.S06.T02`
- `CAP-05.S06.T03`
