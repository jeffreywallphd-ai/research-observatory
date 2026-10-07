# CAP-05.S02.T03 — isolated offline parsing

Claim base: `446819465a63776d7f00696f0bfee8b14fa065a9`; owner
`codex-w2-implementation`, existing W2 campaign, LOC / Windows x64.
Both dependencies, CAP-05.S02.T02 and CAP-04.S05.T02, are DONE/approved.

Authority: approved CAP-05.S02 sections 7–9.3/11, accepted ADR-0028 and
ADR-0029; existing version-1 Document IR, selection and protected-source ports.
The selected parser is Docling slim 2.126.0 with the resolved CPU wheel lock,
immutable Heron/TableFormer accurate assets, cell matching and OCR/enrichment
disabled. Existing raw native adapters and staged IR are predecessors, not
proof of actual packaged execution. Human acceptance remains CAP-05.S03.
There is no new UI workflow or automation-framework source work in this task.

| Material boundary | Observable outcome and selected proof |
|---|---|
| Criterion 1: real parser | A signed dedicated parser package converts declared synthetic scholarly PDFs offline through the selected Docling release and assets. Actual LPAC/no-capability/no-write execution and source-to-staged-IR proof; dependency preparation alone is nonqualifying. |
| Runtime/profile authority | Parent selects a closed parsing profile with a finite package/file/inventory envelope derived from the measured pinned tree. Signed image, every dependency/model/config/notice byte and profile agree. Connector 256 MiB/256-file/64 KiB inventory and 10 MiB binary limits remain unchanged. Reject unsigned, modified, missing-asset and cross-profile packages before execution. |
| Source/output identity | Parent-owned original hash/length, producer/config/assets, job/attempt and encrypted raw receipt bind independently of worker echoes. Chunk both input and large output under parsing limits. Exercise substituted source/output/attempt and malformed/trailing/oversize IPC; no raw paths, keys, project handles or network operations cross IPC. |
| Geometry and quality | Fixture labels freeze before tuning. Exact unrotated top-left point coordinates include rotated/scaled pages; render one requested bounded page, respecting 40 million pixels. Separate missing text, replacement characters, reading order, anchors, references and table uncertainty; scans remain incomplete with OCR disabled. Model confidence is not scholarly correctness. |
| Failure/resource admission | One parser, at most four CPUs/threads, 4 GiB private committed memory, 128 MiB source, 500 pages, 64 MiB IR, 15-minute wall time. Material hostile/encrypted/malformed/huge-canvas, missing-assets, crash, timeout/OOM and cancellation cases return typed content-free failure and no partial canonical output. Cancellation kills only the owned job within five seconds. |
| Persistence/recovery principal | Existing protected read closes its database transaction before inference. Recheck current session/rights and durable attempt fence before encrypted raw staging/delivery. Exercise actual native structured receipt and PDF output through encrypted storage, crash/cancel/restart, new-attempt retry and larger-tree guardian cleanup. Previous originals, raw attempts and accepted heads remain immutable. |
| Fallback | Only an eligible exact Docling failure/timeout/memory failure can select a separate inspection-only text/page attempt. Cancellation or source/rights denial cannot trigger fallback; degraded output cannot qualify Docling or silently advance canonical state. |
| Criterion 2/3 and compatibility | Behavioral regressions precede product edits where practical; version-1 historical IR/selection fixtures remain valid. Add only required portable raw/transport contracts, fixtures, documentation/notice inventory and a linked indexed implementation ADR for protected paths; accepted ADRs stay unchanged. |
| Criterion 3: installed family composition | Every admitted existing family must compose with the actual installed descriptor, canonical source format and strict Core decoder. Test first-party fallback version admission and plain-text-to-worker `txt` mapping; qualify actual native/plain-text/inspection encrypted staging. No new parser family or selection policy. |
| Performance evidence | Authenticate the exact committed package, complete immutable input closure, producer and frozen corpus labels. Measure actual hardware, cold/warm samples, resource peaks and raw samples against ADR-0029's 10-page p95 targets. Diagnostic measurements cannot substitute for qualified benchmarks. |

First proofs: package/profile substitution and chunked-IPC boundary tests;
actual pinned dependency/model verification; a focused packaged LPAC born-digital
PDF and native receipt path before broader integration. Where native proof
cannot precede implementation, retain the diagnostic result and qualify the
completed adapter separately at its exact committed candidate.

Independent read-only preflight: `artifacts/tmp/CAP-05.S02.T03.preflight-s02_t01_review-01.json`
(SHA-256 `2b35e52986ac34934782f4b4a02ad5181b8a29380b0ca9736c0fd2b78cf20616`).
It supports a distinct bounded product parsing package under existing authority;
it is advisory, not a task approval or a new amendment.

Selected checks: affected parser/contracts/profile/transport tests, actual Windows
principal and encrypted-workflow integration, pinned runtime/asset/notice checks,
directly affected lint/type/schema/architecture/ADR checks and required resource
and parser performance proofs. Integrated S02 end-to-end review follows the task.
Fresh full repository/profile, cross-capability, desktop accessibility, packaging,
Wave review and separate human G2 release remain W2 obligations. Unchanged
whole-history checks are not a routine task replay.

Mandatory gate currently demonstrated: none. A proven failure of selected
security/performance/licensing authority will be preserved and routed explicitly;
ordinary debugging remains inside this task.

Advisory learning: inspection used the dependency's PDFium version where the
closed registry requires the first-party adapter's version; plain text had an
admitted selection family but lacked the installed composition and wire-format
bridge. Earlier decoder doubles did not exercise those composition boundaries.
The tracked failing regressions precede both fixes. Plain-text expansion and
normalization cancellation regressions cover the additional hostile-input risk;
the complete pinned Unicode-16 conformance corpus preserves the mapping contract.
Native execution remains separately required; these doubles do not qualify it.

Further advisory learning: cooperative cancellation did not bound an uncancelled
nonstarter segment's rich tuple allocation before wire-mapping admission. A
failing measured-storage regression reproduced that gap. Compact scalar/origin
buffers replace the transient tuple graph without imposing a new format quota;
Unicode gold and existing noncontiguous, blocked and class-zero composition
cases remain required. Check the pinned decomposition expansion when qualifying
the working-storage bound.
