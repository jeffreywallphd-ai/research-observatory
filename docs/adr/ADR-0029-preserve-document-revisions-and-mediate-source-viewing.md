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
`docling-slim[convert-core,format-pdf,models-local]==2.126.0`, initially constrained
to `docling-parse==7.16.0` and `docling-ibm-models==4.0.2`, in the separate
ADR-0028 CPU worker. This is the modular distribution of Docling, not a replacement
parser or a new dependency in Core. Pin the complete qualified worker lock.

Package only selected layout/table assets with exact upstream revision, digest,
license and notice inventory. Runtime uses a read-only artifacts directory,
offline hub settings and denied network; missing assets return an actionable
local error, not an implicit download. OCR, VLM, remote serving and document-provided
plugins remain disabled by default. A scan with no usable text remains visible
as incomplete, not an invented extraction. Final asset identities and supported
resource profile must be specified before this decision is approval-ready.

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
project close/lock. No long-lived database read lease, plaintext disk cache or
whole-file renderer buffer is selected.

**Unresolved before packet approval:** establish whether this repeated verification
fits the existing representative first-page/resource target and concurrent metadata
writes. The proof must set maximum source/range sizes and per-document concurrency,
include full-file authentication time, and verify prompt cancellation/lease release.
Small response size alone does not bound source work. If it fails, explicitly
select a bounded cache of encrypted derivative chunks using the existing object
envelope, with parent-revision/rights binding and recoverable eviction. Release the
source read transaction before publishing derivative chunks to avoid self-contention;
review its lifecycle as a separate material boundary. Do not
invent a new cryptosystem or silently relax the target. This is a visible planning
decision, not permission to implement both options or add a control framework.

Disable PDF scripting/XFA/actions/attachments and remote asset fetches. All copy,
print, external-open and export commands go through action-specific rights checks
and explicit destination selection where required. Keep copied text out of audit
logs; permitted quotations carry source identifiers. Application controls do not
prevent a researcher taking a screenshot or using an already authorized export.

## Consequences

Originals and accepted evidence survive parser replacement. Additive Core
schema migrations retain original revisions, provenance and rights; rollback
retains verified ciphertext and never relabels a new revision as an old one.
An incompatible IR/selector change needs a versioned migration and ambiguity
report, not silent offset repair. Parser failure or cancellation discards only
uncommitted outputs; source and metadata remain usable.

Local CPU dependencies/assets add installation size and cold-start cost. Windows
wheel resolution is not runtime, LPAC, packaging, licensing or performance proof.
Both remaining planning gaps above must be closed before W2 approval; production
qualification remains a later implementation obligation, not waived by G1.

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
