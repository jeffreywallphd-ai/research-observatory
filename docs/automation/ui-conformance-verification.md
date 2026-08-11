# Desktop UI conformance verification

The `desktop` verification profile uses the approved UI reference as a contract,
never as the shipped application. The historical activation name
`approved-reference-application` identifies the exact offline conformance fixture
under `apps/desktop/dist`; that fixture exercises the complete reference and
visual baseline but is not a Tauri frontend.

The separately authored application lives under `apps/desktop/product-dist` and
is the only `frontendDist` used by Tauri in production or development. Product
checks require an exact build-input/output manifest, a CAP-01-only route
inventory, no reference-only pages or workflow markers, no unexpected requests,
and functioning keyboard, focus, dialog, theme, live-region, responsive, and
accessibility behavior. Missing, redirected, stale, incomplete, or
reference-contaminated product output fails closed.

## Checks

The reference-fixture portion validates exact light/dark semantic-token
declarations, all 32 reference route identities and all 521 exact required-region contracts, approved
primary and supporting-tool navigation, all 14 ordered workflows,
distinct-route previous/next behavior, tab-order and Enter activation for every
workflow link, keyboard theme/sidebar/focus behavior, accessible-name and exact
responsive visual parity, and 64 controlled reference screenshots (32 pages in two
themes). The product portion separately verifies only implemented capability
surfaces. Every report cites the normative token, style, route, workflow, page,
and approval sources and carries the explicit illustrative exclusions. Mock
names, studies, counts, dates, prose, and chart values are never product
requirements.

Run the complete gate on the Windows x64 qualification platform:

```powershell
.venv\Scripts\playwright.exe install chromium
.venv\Scripts\python.exe tools\verify.py --profile desktop --report artifacts/tmp/desktop-verification.json
```

The renderer is pinned by `verification/extensions/desktop-ui.json`: Playwright
and Chromium versions, Windows x64, 1440×900 viewport, device scale, locale,
timezone, reduced motion, light/dark schemes, fonts, animation suppression, and
deterministic time/random data. Browser requests are aborted and reference
assets are inlined, so qualification is offline.

## Visual baseline changes

`verification/baselines/desktop-ui.json` records the screenshot SHA-256 values
and full renderer identity. `verification/desktop-ui-baseline.schema.json`
strictly validates the current record and every reachable historical snapshot.
Authoritative verification rejects an uncommitted baseline, incomplete or
malformed approval record, or reference package whose Git blobs do not produce
the cited package hash. A changed committed visual contract must cite a
different approved reference ID and a different approval commit occurring
between baseline versions. A provenance-only ratification may retain the
reference ID only when every renderer setting and screenshot entry is
byte-equivalent and the package SHA plus approval commit are the sole changed
fields. Create a baseline only after the reference has completed the human
approval gate:

The later exact ratification may close a preserved pre-control package-lineage
gap only for the identical visual contract. Historical schema, raw-byte,
transition, and approval-record checks still run; a screenshot, renderer,
reference ID, or any other baseline-field change cannot use this exception.
Because the approval record is itself governed, one handoff commit necessarily
contains the new exact approval package before its immediate child updates the
baseline provenance. That handoff is accepted only when its baseline bytes are
unchanged from its single parent, the child changes provenance only, and the
child independently validates the exact package at both approval and baseline
commits. No additional intermediate commit is permitted.

```powershell
.venv\Scripts\python.exe tools\ui_conformance.py --repo . --write-baseline `
  --approved-reference-id <exact-approved-reference-id>
```

The writer refuses to overwrite a baseline for the same reference. Never update
hashes to make an unexplained visual change pass.

## Failure and recovery

Failures name the governing artifact and page or workflow identity. Correct the
application or, for an intentional design change, complete the design-first
reference approval workflow before changing implementation or baselines. If the
browser is absent, install the pinned Chromium build with the command above; do
not substitute another engine or version.
