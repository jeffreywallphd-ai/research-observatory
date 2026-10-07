# Protected staged document parsing

CAP-05.S02.T01 defines values and ports under accepted ADR-0028 and ADR-0029.
Native adapters are implemented by S02.T02; isolated execution remains T03, and persistent
revisions and human acceptance remain S03. This contract introduces no database
migration, HTTP endpoint, UI change, accepted-head write or parser dependency.

[Proposed ADR-0044](../adr/ADR-0044-bind-native-parsing-contracts-to-existing-document-authority.md)
documents the additive native raw contract and parent-authenticated port under
the unchanged accepted decisions, including compatibility, rollback and proof
limits. It supplies the same-change-set protected-interface trace without
granting new architecture or runtime authority.

`parsing/contracts.py` owns strict, frozen version-1.0 values. Original object
digest/length/format, project, attachment, document/revision, candidate, source
assertion and Work/Version revisions travel together. Local imports carry local
provenance; remote acquisitions additionally bind the exact location and retained
receipt digest. Producer identity records version, configuration and asset
digests, separately from durable workflow job and attempt identities.

The IR retains ordered flat nodes with earlier parents, raw/normalized text
projections, locations, reference entries and identifier observations, citation
candidate sets, table indices/spans/cell text, figures and protected preview
receipts. Unknown elements keep their type and raw text. Quality dimensions and
warnings remain separate; missing confidence is unknown, and a reported numeric
value is no probability of correctness or acceptance. Reported table grids reject
overlap; explicit ambiguous grids retain competing geometry for review.
Reference strings, citation markers and cell text use their identified node's
projection and a contained span of its decoded text. Missing node text or a
contradictory projection/range is refused. Containment uses the exact normalized
range and raw contributors, including reordered and noncontiguous contributors;
it does not impose a new monotone-offset rule on legitimate Unicode mappings.

`ro-text-nfc-1` pins Unicode 16.0.0 NFC plus CRLF/CR to LF. It preserves case,
whitespace, ligatures and hyphenation. Text offsets are half-open Unicode code
points, including supplementary scalars as one position. Raw text is decoded
source text, not original byte offsets; original bytes remain in the encrypted
source object. Compact identity runs and per-scalar transformed mappings retain
all raw contributors. Composition can have noncontiguous contributors; expansion
can map multiple normalized scalars to one raw scalar. Reordered marks can map
backwards. Every span is checked against the exact mapping, never an approximation
over an unstated normalization. Page coordinates use finite points in the
unrotated original page frame with top-left origin; page rotation is explicit.

The Core-owned closed registry admits native structured/text, pinned Docling
2.126.0 CPU and the approved PDF inspection fallback. Runtime availability and
source eligibility are trusted Core observations. Selection prefers eligible
JATS/TEI/XML/HTML, then PDF, DOCX and text; stable source/parser IDs break ties.
An explicit alternative-copy selection or proven same-object/source assertion is
required; sharing a Work, Version or content digest alone grants no equivalence.
Denied, unavailable and unproven candidates stay in the record. PDF fallback is
a separate inspection-only attempt after an exact Docling failure, timeout or
memory limit. Cancellation and source/rights denial cannot trigger fallback.

The additive object-store parse facet resolves the exact committed attachment
and current retained provenance, then evaluates inspect and derive together in
the existing protected writer transaction. Existing inspection-only consumers
retain their behavior. `LocalProtectedParseSource` authenticates and reads in
bounded chunks under the caller's production native-session guard, releases the
writer before parsing, and hands the adapter private read-only memory without a
path, key or write port. It repeats current source/rights authorization under the
same guard before delivery. Current actor, accepted Intent and privacy checks
come from the existing rights repository. Test-owned SQLCipher/encrypted-object
tests exercise changed rights and real detach/close/reopen denial; their parser
double is explicitly synthetic and does not qualify an isolated worker.

`stage_parse` binds the request/selection fingerprint to the parent-authenticated
producer, job, attempt and artifact receipts. The receipt must be constructed by
the trusted launcher independently of worker JSON. Strict UTF-8 JSON rejects
duplicate fields, nonfinite values, invalid graphs and output over 64 MiB; copied
model instances are revalidated. Errors contain codes, with no retained private
decoder/validation exception. Cancellation is monotonic and fails closed on a
broken callback. Failure, cancellation and denied delivery expose no usable IR
and cannot change canonical document facts. Staged output is never acceptance.

The [portable schemas](../../packages/contracts/documents/README.md) describe
wire shape, with an explicit semantic-rule inventory. New incompatible versions
must follow the existing compatibility/ADR route. No implicit offset migration
or format repair is selected. Isolated execution, resource enforcement, offline
assets, raw-output persistence and slice-wide recovery remain subsequent work.

## Native structured extraction

CAP-05.S02.T02 adds `workers/document/native_parsing.py` and the Core
`NativeStructuredParser` adapter. Only the worker parses original JATS, TEI,
generic XML or inert UTF-8 HTML. Core imports the value/port contracts and
validates the delivery; it does not import the worker or open original paths.
The new [native raw schema](../../packages/contracts/documents/native-structure.v1.schema.json)
is additive. Existing IR, request and result wire versions remain 1.0.

The raw receipt retains exact qualified element names, ordered decoded
attributes, nearest source parents, distinct original byte anchors (including
empty elements), close kind and owned decoded-text runs. Byte ranges are
half-open positions in the original source encoding. Decoded text is a separate
code-point stream: XML predefined/numeric entities are decoded; CDATA stays
literal; physical CRLF/CR remains raw until the existing projection normalization.
XML supports UTF-8, BOM-marked UTF-16 and explicitly declared ASCII/ISO-8859-1.
Algorithm support does not expand intake admission: a format not admitted by the
existing attachment boundary remains unavailable to production selection.

Each element has one staged `native-node-{index}` and one
`native-text-{index}` projection. Core checks unique preorder indexes, one root,
nearest parent, nonoverlapping markup and text ownership, complete decoded-text
coverage, and exact element-content intervals before mapping. Per-element NFC
preserves truthful child contributors when a combining mark composes across an
inline boundary in the parent's text. Original byte anchors remain in the raw
artifact; the existing IR text locator identifies that element's decoded-text
projection. Unknown elements retain type, text, source hierarchy and locations.

Native vocabulary recognition uses exact namespaces: unnamespaced/standard
JATS, unnamespaced/TEI P5, generic unnamespaced XML, and unnamespaced/XHTML HTML.
Foreign elements with familiar local names remain unknown. Source bibliography
entries and explicit bibliography links produce staged reference/citation
observations, never scholarly authority. Duplicate or absent source IDs leave
candidate links ambiguous/unresolved. A partially missing target set is
conservatively unresolved with a quality warning; all original targets and known
entry identities stay in the raw receipt. Identifier values are observed fields,
not inferred citations. HTML's historical `doc-biblioentry` role is retained for
source compatibility; no accessibility conformance is inferred from that role.

Native rows/cells retain explicit source spans without inventing missing rows,
clamping geometry or expanding a source-controlled dense grid. The existing IR
requires each semantic cell's direct parent to be its table; this is the sole
parent transformation. The raw receipt retains original row/group ancestry.
Nested tables remain separate. Unsupported/duplicate geometry yields an unknown
cell with its text/attributes and an ambiguous table warning. HTML zero-rowspan
uses the observed remainder of its source row group. Figures retain captions
and locations; no image is fetched, OCRed or synthesized.

Worker extraction denies DTD/entity loading, processing instructions and active
or fetching HTML. Malformed content, depth over 256, more than one million
elements, original bytes over 128 MiB, output over 64 MiB or cancellation returns
no usable receipt. Failure messages are content-free and retain no private
decoder exception. Source digest/length/format and independent parent-owned
producer/job/attempt/raw-artifact hash/length/media receipts must all agree before
Core exposes staged IR. A worker JSON echo is insufficient.

The native tests use declared, repository-authored
[synthetic fixtures](../../tests/fixtures/documents/native/README.md), exact-byte
gold and an explicitly synthetic transport port. Existing protected-source tests
exercise actual test-owned encryption/rights/session fences. These checks do
not qualify packaged LPAC execution, encrypted raw persistence, offline Docling
assets, runtime resource limits or slice-wide recovery; those remain T03.
The vocabulary and geometry expectations were checked against the primary
[JATS 1.4 tag library](https://jats.nlm.nih.gov/publishing/tag-library/1.4/),
[TEI P5 reference](https://tei-c.org/release/doc/tei-p5-doc/en/html/REF-ELEMENTS.html),
[HTML table specification](https://html.spec.whatwg.org/multipage/tables.html),
[DPUB-ARIA 1.1](https://www.w3.org/TR/dpub-aria-1.1/), and the documented
[Expat](https://docs.python.org/3.14/library/pyexpat.html)/
[HTMLParser](https://docs.python.org/3.14/library/html.parser.html) callback APIs.

## Isolated offline runtime and raw attempts

CAP-05.S02.T03 adds the fixed installed Windows parser and trusted Core
`InstalledParserPipeline`. [Proposed ADR-0045](../adr/ADR-0045-bind-the-isolated-offline-parser-package-to-existing-document-authority.md)
maps its packaging and protected delivery to unchanged ADR-0028/0029 authority.
Docling slim 2.126.0, Docling Parse 7.16.0, CPU layout/table models and PDFium
5.13.0 run in a separate signed, sealed, zero-capability LPAC job. OCR,
enrichment, plugins, egress, compilation and plaintext scratch remain disabled.
The full signed runtime inventory digest is an explicit `parser-runtime` asset
in every installed descriptor, including native and inspection-only adapters.
The selected model digest alone does not identify the shipped native derivative.

Within its four-logical-processor ceiling, the parser prefers one allowed
processor on each distinct physical core, favoring the Windows-reported
performance class. Every selected bit remains within the parent affinity.
Unavailable, incomplete, overlapping or multi-group topology uses the previous
first-four-bit allocation. The connector keeps its one-processor selection;
the worker's actual post-assignment affinity must still equal the admitted mask.
The preference uses the documented
[processor relationship](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-processor_relationship)
and [process group affinity](https://learn.microsoft.com/en-us/windows/win32/api/processtopologyapi/nf-processtopologyapi-getprocessgroupaffinity)
APIs; it does not change machine scheduling settings.

The offline build verifies locally supplied upstream source archives and applies
only the tracked native admission/geometry and QPDF buffer patches. Original
MediaBox, CropBox, inherited rotation and UserUnit are admitted before page
decoding or surface allocation. Resource traversal, encoded/decoded streams,
predictor dimensions, image/mask geometry and actual JPEG/JPX headers are bounded.
Unverified JBIG2 decoding is denied before either parsing or rendering. This is
an input-denial outcome, not a reason to relax isolation or select fallback.
The package retains upstream notices, source/patch identities and build receipts.
Duplicated Torch/Torchvision/Docling source bytes are compacted into a bounded
read-only archive for introspection of already-frozen bytecode. A strict signed
index binds each member; the worker neither executes archive source nor extracts
it. Transformer discovery sources, native libraries and resources keep their
fixed paths. Full package authentication still checks every shipped file.

Core constructs a stager for one exact selected request and a live
`document-parse`/`document` workflow claim. It checks the native session and lease
before running, closes the protected source transaction before inference, and
rechecks current rights/session and the durable attempt before publication.
An encrypted exact request/expected-output intent is retained first. A second
atomic transaction authenticates that intent and the original, then retains
the encrypted raw output, distinct document aggregate, dependencies, provenance
and attempt diagnostic together. An incomplete intent makes no completion claim.
Failure returns no rolled-back receipt or readable orphan; a pre-existing shared
object and all earlier originals/raw attempts remain intact. No accepted head is
advanced by this staging service. S03 owns parsing-operation context, immutable
revision publication and human acceptance.

Only an exact Docling failure, timeout or memory-limit result can select the
separate inspection-only PDF text attempt. It records a new attempt, the prior
failure and unchanged source identity. Missing text, replacement characters,
reading order, anchors, references and table uncertainty remain separate. Current
source/rights denial, cancellation, missing assets and admission failures cannot
trigger fallback or produce canonical success.

Page rendering decodes only the requested admitted page. Its PNG contains one
bounded application geometry record from the same native admission result.
Core checks the original frame, requested page, dimensions, CRCs and compressed
scanline shape without allocating a decoded bitmap. The encrypted PNG receipt
binds its original geometry as well as the image bytes. Source viewing must
apply crop translation, rotation, media origin and UserUnit before mapping IR
points to actual rounded pixel dimensions. No plaintext image cache is created.

Core preflights one cumulative 100,000-entry budget for the raw node graph and
all table-cell expansion before constructing IR models. Relationship fanout is
bounded separately. Decoder loops check cancellation, and figure locators use
direct source-key lookup rather than repeated scans of the completed node list.

Engineering diagnostics and synthetic port tests do not qualify the installed
product. Commit-bound package, native-principal, encrypted source-to-staged-IR,
resource/cancellation/recovery and cold/warm performance proofs remain required
before this task or its slice can complete.
