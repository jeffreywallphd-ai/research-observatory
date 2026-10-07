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
| Protected interface documentation | Every changed protected contract/port path has a changed indexed Proposed or Accepted task-linked ADR in this change set, documenting inherited authority, compatibility, rollback and verification limits. | Existing ADR checker over original claim base through the corrected candidate; preserve the four-path R01 failure and obtain independent closure of R01.F01. |

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

Independent pre-submission review at `60f8a6fab3bf9d59a7b2267bea6e0c288f8df4d2`
found two missed acceptance cases: a bibliography marker with both a retained
and missing target must retain unresolved uncertainty instead of rejecting the
document; valid optional HTML list/paragraph/head endings must preserve source
hierarchy and text ownership through the relevant ancestor. The exact adverse
observation is `artifacts/tmp/CAP-05.S02.T02.review-s02_t01_review-observation-01.json`,
SHA-256 `b99db24d5c12c28d71217164fc265a6d45a6dc7b6b6df1ea2651bf8c16229daf`.
The original passing selected run and unsubmitted R01 manifest remain unchanged
as historical observations; they do not qualify the newly demonstrated cases.
Minimal behavioral regressions precede the correction. Existing IR citation
states remain unchanged: incomplete target sets are conservatively unresolved,
with original targets/known reference identities retained in the raw receipt
and a quality warning, rather than inventing a complete link or a new wire state.

The same finite independent observation also identified native TEI `head` being
promoted to a caption under a foreign-namespace `figure`. Native contextual
semantics require the parent's namespace as well as its local name. A minimal
foreign-parent/native-parent regression precedes that correction too.

Formal R01 at `bfae61bbbbca3f20d3a4089d6c9e33acebdfe00e` found a separate
criterion-3 documentation gap, `CAP-05.S02.T02.R01.F01`: the selected dependency
architecture check did not run the protected-path ADR coverage check. Four
new contract/port paths therefore lacked a changed indexed companion despite
unchanged accepted ADR-0028/0029 governing their implementation. The exact
failed checker output and independently authored adverse disposition remain
preserved. Add only Proposed ADR-0044 within this task's approved scope, keeping
accepted decisions unchanged. Its fresh check must use the original claim base
so the incremental R02 diff cannot hide those original interfaces. This missed
acceptance row is updated before documentary remediation; the existing checker
and preserved failed run supply the regression, without adding a framework test.
