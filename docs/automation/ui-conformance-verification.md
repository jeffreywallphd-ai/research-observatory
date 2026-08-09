# Desktop UI conformance verification

The `desktop` verification profile binds researcher-facing implementation to the
approved UI reference. CAP-00 activates an `approved-reference-fixture` target
before application code exists. This mode qualifies the verifier and baseline,
not a shipped desktop application: it fails as soon as a UI implementation file
appears under a configured application root. CAP-01 must then replace the
fixture activation with an implementation target and retain every conformance
boundary.

## Checks

The profile validates exact light/dark semantic-token declarations, all 32
product route identities and required regions, approved primary and
supporting-tool navigation, all 14 ordered workflows, distinct-route
previous/next behavior, keyboard theme/sidebar/focus behavior, accessible-name
and responsive-state parity, and 64 controlled screenshots (32 pages in two
themes). Every report cites the normative token, style, route, workflow, page,
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
and full renderer identity. Authoritative verification rejects an uncommitted
baseline. A changed committed baseline must cite a different approved reference
ID and a different approval commit occurring between baseline versions. Create
a baseline only after the new reference has completed the human approval gate:

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
