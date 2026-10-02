# CAP-05.S01.T01 — Academic Minimal 1.8 attachment proposal

**State:** proposed, inert, pending exact human reference approval. The active
implementation authority remains `design/ui-reference/` at
`RO-UI-ACADEMIC-MINIMAL-1.7`. The separate proposal package is
[`planning/W2-reference-1.8/`](../../planning/W2-reference-1.8/README.md),
with proposed ID `RO-UI-ACADEMIC-MINIMAL-1.8`. It does not approve the W2
campaign, change the backlog or implement document acquisition.

## Decision for review

| Candidate | Effect |
|---|---|
| **Recommended: inline panel in Ingestion Review** | Keeps the selected canonical work/version, metadata-only status, rights decision, local file candidate and cancel/retry action together. It uses the existing page, components and primary-workflow return context. A committed revision records the future reader route; opening stays pending until CAP-05.S04 delivers the protected viewer. |
| Separate acquisition route | Creates another governed page and navigation transition for the same selected record. It would need extra selection restoration, focus, cancellation and version-context rules without adding useful room for this bounded local attachment. |

The proposed [style contract](../../planning/W2-reference-1.8/STYLE_GUIDE.md#14-local-full-text-attachment-from-a-selected-workversion),
[Ingestion Review](../../planning/W2-reference-1.8/ingestion-reconciliation.html#attach-full-text),
[page contract](../../planning/W2-reference-1.8/CAPABILITY_COVERAGE.md#ingestion-reconciliationhtml--ingestion--reconciliation),
and [workflow note](../../planning/W2-reference-1.8/WORKFLOW_CATALOG.md#catalog)
describe the same small change. The fourteen workflow sequences and semantic
tokens are inherited without relabeling ADR-0026 selections.

The panel starts from the highlighted work/version row. It exposes a native
file picker and drop target, displays only candidate name and size in the mock,
requires explicit confirmation of an uncertain work/version association, and
keeps rights unknown or denied separate from project-only permitted use. It
names metadata-only, pending, blocked and recoverable states. Unsafe files have
no bypass; unsupported, password-protected, oversized, denied and interrupted
cases each have a specific next action. Cancel and Escape clear the pending
candidate, retain the selected metadata record and return focus to the invoking
control. The reader link previews a future route. Application success must retain
the exact committed revision, selected-version return context, and Task Center
status while processing. The real reader action stays disabled/pending until
`CAP-05.S04` implements protected source viewing under ADR-0029.

The HTML is an offline reference. Its file input and drop demo reads no file
bytes, creates no storage object, makes no network request and cannot assert
that rights or content inspection passed. Mock titles, counts and names are
illustrative. The real application must enforce association, policy, type,
password, size, checksum and quarantine decisions at trusted boundaries.

## Validation and approval boundary

The proposal generator reproduced all 54 governed file hashes. The package
site check found 35 HTML files, 33 product pages, 14 workflow profiles and 20
capability records. JavaScript syntax and the Playwright interaction smoke
check passed, including focus on panel entry, disabled initial action,
candidate/rights/match controls, cancellation and Escape focus return.
Light and dark previews can be regenerated locally from the proposed HTML when
needed for review. Generated PNGs are excluded from this immutable source
proposal; the privacy hook requires an independent, exact binary review before
any new screenshots may be committed. The proposed HTML and generator are the
reviewable source. The affected Ingestion Review generator also fixes an
inherited rendering defect that printed helper calls instead of badges and
metrics, so the selected-work panel can be reviewed in its intended context.
The copied legacy v1.3 validation outputs and contact sheets were removed from
this proposal to avoid presenting stale evidence.

`tools/ui_reference_check.py --reference planning/W2-reference-1.8` has only
the expected pending-approval failures: `reference is not approved:
status='proposed'` and `manifest is not approved: status='proposed'`.
The current governed package digest is
`19fbd0f9250e4994b561913beacb0aecbea07478e53981272b7866682a778b7e`;
it identifies proposal bytes, not an approval.
Do not mark these records approved to make the check pass. The next authority
step is explicit owner approval of the exact package and a new immutable
reference approval record; only then may material plans and CAP-05.S01.T01
product implementation bind to 1.8.

## Package delta from approved 1.7

The changed non-HTML governed files are `APPROVAL.yaml`,
`CAPABILITY_COVERAGE.json`, `CAPABILITY_COVERAGE.md`,
`PAGE_INVENTORY_SOURCE.md`, generated `PAGE_INVENTORY.md`, generated
`README.md`, `REFERENCE_MANIFEST.yaml`, `SITE_MANIFEST.json`,
`STYLE_GUIDE_SOURCE.md`, generated `STYLE_GUIDE.md`,
`WORKFLOW_CATALOG.json`, `WORKFLOW_CATALOG.md`, `assets/app.css`,
`assets/app.js`, `scripts/build_mockups.py`, `scripts/render_previews.py`,
and `scripts/smoke_interactions.py`. All 35 root `.html` pages were
regenerated for the 1.8 proposal footer; the substantive page changes are
`ingestion-reconciliation.html`, `document-reader.html`, `style-guide.html`
and the Ingestion Review description in `prototype-index.html`. The nine
light/dark/comparison previews for Ingestion Review, Document Reader and the
style guide can be regenerated locally but are excluded from the immutable
proposal. `SHA256SUMS.txt`, `VALIDATION_REPORT.md`,
`ui-reference-validation.json` and legacy contact sheets were omitted because
they describe older packages.
