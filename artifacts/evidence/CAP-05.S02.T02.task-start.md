# CAP-05.S02.T02 — native structured parsing acceptance closure

Claim base: `ce14e0dcb0c8578f6514b900fa3baf24039a435d`. The owned W2
claim is recorded by `artifacts/tmp/CAP-05.S02.T02.claim-01.txt`.
CAP-05.S02.T01 is DONE, independently approved and locally integrated.

Authority: approved CAP-05.S02 plan section 9.2, accepted ADR-0028/ADR-0029,
and the version-1 staged parser contracts. This task implements secure native
JATS/TEI/XML/HTML extraction and its validated IR adapter. Native execution,
encrypted raw-output persistence, Docling, packaged resource qualification and
integrated recovery remain CAP-05.S02.T03. Revisions/acceptance and the reader
remain later slices. No UI, migration or automation-framework development is
selected.

## Material acceptance and proof

| Boundary | Required behavior | Planned proof |
|---|---|---|
| Golden structure/text | Retain ordered titles, abstracts, sections, paragraphs, lists, footnotes, references, citation markers, tables/cells and figures/captions. Recognize only the appropriate namespace vocabulary; preserve other elements as typed unknowns. | Declared synthetic JATS, TEI, generic XML and inert HTML fixtures with independently authored hierarchy/text expectations; namespace and mixed-content cases. |
| Unknown source locations | Retain qualified types, decoded text, original hierarchy and distinct source-byte anchors, including empty elements. Byte locations and normalized code-point positions are separate. | Adjacent empty foreign elements and a combining-mark child; exact fixture byte slices, raw-element identities and node/projection linkage. |
| Normalization | Each named element projection uses existing Unicode16 NFC/newline-only rules. Composition across inline children must not fabricate child offsets. | Parent/child composition, supplementary scalars, physical CRLF/CR, numeric/predefined entities and CDATA expectations; existing normalization regressions. |
| Raw-element identity | Each IR node/projection corresponds to one authenticated receipt element and its exact decoded-text interval. Preserve the nearest source parent except the documented direct-table-parent transformation. | Duplicate/aliased element indexes, contradictory parent/range mutations and the empty-element golden regression; source hierarchy remains in the raw receipt. |
| Trust and authority | Require exact source digest/length/format, selected producer, job/attempt and independently supplied raw-artifact receipt. Worker fields cannot grant these identities. | Authenticated-port boundary substitutions and malformed/duplicate/nonfinite wire rejection; staged result validation. |
| Scholarly uncertainty | Keep unresolved or ambiguous reference targets explicit, preserve observed identifiers and cell spans, and expose unsupported table geometry. Never infer a source, link, confidence or missing row. | Duplicate/missing targets, nested tables, explicit row/column spans and unrepresentable geometry fixtures; raw attributes remain retained. |
| Hostile input/resources | Deny DTD/entity resolution, processing instructions, active HTML and malformed content; enforce existing source/output/depth bounds and cancellation without usable partial output. | Small deterministic hostile/malformed/depth/cancellation fixtures and bounded size checks. Errors contain codes and retain no private validation exception. |
| Principal and handoff | Hostile-byte parsing belongs only in worker modules. Core consumes a validated raw delivery and has no canonical write port. | Real native algorithm plus Core adapter on test-owned synthetic bytes, strict receipt validation and existing protected-source/rights/session tests. In-memory transport doubles are explicit; they do not qualify LPAC or encrypted output persistence. |
| Compatibility/evidence | Preserve existing IR/request/result versions and consumers; publish the new versioned native raw contract and documentation within approved scope. | Existing parser regressions, generated schema checks and affected quality/architecture checks at a committed candidate. Broader fresh slice/Wave checks remain deferred. |

The read-only independent preflight by `agent:/root/s02_t01_review` confirmed
that the existing IR supports named per-element projections and empty unknown
blocks, with physical byte anchors retained in the raw artifact. It identified
the raw-element-to-IR identity invariant above and the adjacent-empty-element
fixture. This is advisory design input, not a task approval.

First tests precede production edits. Selection is limited to native/parser
contracts and directly affected schema, format, lint, types and architecture.
No unchanged full profile, history audit or runtime build is selected at this
task stage. Fresh independent task disposition and later slice/Wave gates
remain required.

Development observations remain separate from candidate qualification. The
initial `native-red-01.txt` records absent native modules (13 cases/17 errors),
not a behavioral boundary failure. Subsequent finite `dev-01` through `dev-04`
logs preserve format/lint errors and successful corrections without overwriting
them. Synthetic HTML gold now includes its explicitly authored abstract;
per-format expectations independently name the section/paragraph/inline,
list/item, footnote and figure/caption relationships. Native 20-case and portable
3-case development observations pass, along with affected normal-import types.
Fresh committed-candidate checks and independent disposition are still required.
