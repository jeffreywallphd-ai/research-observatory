# Exact-revision source anchors

Version 1.0 follows ADR-0029 and CAP-05.S03.T02. Public `SourceAnchorReceipt`
contains Core-generated anchor/revision IDs, creation time and an immutable
target. The target binds the accepted normalized revision, original copy identity,
content/structure digests, Core structural block/sentence/projection IDs, an exact
quote, bounded adjacent context and half-open text position where text exists.
NFC Unicode 16.0.0 code-point offsets use `ro-text-nfc-1`; consumers explicitly
convert to UTF-16 only for display. Never normalize or search again to relocate
the selected passage. A later accepted revision does not move this target.

Page regions use normalized [0,1] rectangles in the **unrotated source-page**
top-left frame, original point dimensions and explicit clockwise rotation.
`pageIndex` is zero-based; displayed `pageNumber` is `pageIndex + 1`.
`granularity: block` discloses parser geometry precision. Missing coordinates have
an explicit reason and use visible structural/text inspection. Parser confidence
remains reported/unknown/not-reported/not-applicable/unavailable; scholarly
verification remains `unverified`.

The renderer proposes only revision/node IDs and a bounded span. Core derives
quote/context/geometry from the same authenticated accepted structure; requests
cannot supply paths, actor authority, quote text or geometry. The hidden native
IPC routes use the current human session, Intent/privacy policy and exact copy's
inspect/derive rights. Read, list and idempotent retry revalidate that authority.
Responses and errors must not enter logs, support bundles or deep-link URLs.

Persistence reuses the existing derived Document aggregate, encrypted object
envelopes, immutable provenance, material source dependency and atomic outbox.
No new schema migration or separate anchor identity store is introduced. A common
read authenticates at most 32 KiB of retained context and canonical registration;
it does not load the original PDF or the complete normalized IR. This establishes
derivative-context integrity, **not** current original-byte verification. Opening
the original still uses the complete authenticated object-read path.

Reader outlines page at most 50 structural elements with previews of 160 code
points; saved-anchor lists page at most 100 opaque IDs. The outline selection
names at most 2,048 code points; longer blocks remain inspectable through bounded
span selections. Historical revision choices and anchors retain exact identities.
CAP-05.S04 activates the approved attachment-to-reader route and protected source
viewer. CAP-05.S03.T03 owns context/citation resolution and broken-dependent
propagation. This task's inert passage component is not PDF viewing or evidence
acceptance.

Regenerate/check shapes with `python packages/contracts/anchors/generate_anchor_schema.py`
and `--check`. JSON Schema covers value shape; Core enforces the listed semantic
and current-authority rules. Fixture/tests reside in `tests/anchors/` and the
desktop source-anchor contract/passage checks.
