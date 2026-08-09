---
id: ADR-0004
title: Govern desktop UI conformance and visual baselines
status: Proposed
date: 2026-08-08
deciders:
  - CAP-00 approved plan and CAP-00.S06.T04 independent review
linked_tasks:
  - CAP-00.S06.T04
decision_scope: Desktop target activation, approved-reference conformance checks, deterministic Windows visual baselines, profile and CI enforcement, and protection against same-change weakening.
affected_paths:
  - verification/extensions/desktop-ui.json
  - verification/desktop-ui.schema.json
  - verification/desktop-ui-baseline.schema.json
  - verification/baselines/desktop-ui.json
  - tools/ui_conformance.py
  - tools/ui_*_check.py
  - verification-profiles.json
  - quality-scope.json
  - ci-policy.json
  - .github/workflows/ci.yml
  - architecture-protected-paths.json
  - architecture-boundaries.json
  - tools/ui_change_gate.py
supersedes: []
superseded_by: null
---

# ADR-0004: Govern desktop UI conformance and visual baselines

## Context

CAP-00.S06 established an approved, offline UI reference and a design-first
lineage gate, but neither proves that an application continues to implement the
approved tokens, page contracts, workflows, keyboard behavior, responsive
states, or rendered appearance. A screenshot hash without its browser,
platform, viewport, font, data, and approval identity is not reproducible
evidence. Conversely, CAP-00 cannot claim a desktop application before CAP-01
creates one.

The final foundation slice therefore needs an executable verifier that can be
qualified against the approved reference now, fails when that temporary fixture
would mask real application code, and can be retargeted without weakening the
design-first boundary.

## Candidates

1. Leave desktop conformance to manual review. This preserves judgment but
   cannot detect drift deterministically or provide exact task/CI evidence.
2. Store only image files or hashes and compare them with an unpinned local
   browser. This detects some visible drift but makes results depend on mutable
   engines, fonts, animation, time, data, and platform state.
3. Activate a strict, schema-governed target; run reference-mapped semantic and
   browser checks; bind visual hashes to the complete renderer identity; and
   require a newly approved reference for every baseline revision. Use the
   approved reference itself only as an explicitly temporary pre-application
   fixture that rejects the appearance of application source.

## Decision

Adopt candidate 3. The `desktop` profile runs unit, reference-integrity, token,
route/page, workflow, accessibility/responsive, and visual-regression commands.
The activation binds the exact reference ID and package SHA-256, normative
sources, illustrative exclusions, target mode, implementation roots, and
controlled Playwright/Chromium settings. Reports map every failure to a
normative artifact rather than treating mock prose or data as requirements.

Before CAP-01, `approved-reference-fixture` mode targets the approved reference
and fails if a researcher-facing implementation file exists in any declared UI
root. This qualifies the verifier but does not assert that the desktop product
exists. Application implementation must replace the mode/target through a
protected, ADR-reviewed change.

Visual baselines contain 32 pages in light and dark at the pinned Windows x64
renderer identity. Verification rejects dirty baseline state and strict-schema
validates every reachable historical baseline, then binds it to the exact
approved reference package and complete approval record. Git history must show
a different reference ID and approval commit for a changed visual contract. A
provenance-only ratification may retain the reference ID only when the package
SHA and approval commit are the sole changes and every renderer setting and
screenshot entry remains byte-equivalent. The guarded writer refuses a
same-reference visual overwrite. CI installs the locked browser and runs the
full desktop profile. Activation, schemas, baseline, core
checker, entry points, profile wiring, CI wiring, and weakening-sensitive gate
controls are architecture protected.

An exact later ratification can close a preserved pre-control package-lineage
gap only for a byte-equivalent visual contract. It does not suppress historical
schema, raw-byte, transition, or approval-record failures and cannot authorize
changed screenshots, renderer settings, or reference identity.

## Consequences

UI drift becomes deterministic, offline, page/workflow-specific evidence, and
the approved reference remains the sole intentional-design authority. New
application source cannot silently inherit a fixture pass. Browser requests are
aborted, assets are inlined, time/randomness/animation are controlled, and no
secret or production data is used.

Windows x64 qualification requires the pinned Chromium download and controlled
fonts. Other desktop platforms remain later qualification targets and must use
their own approved baselines rather than reusing Windows hashes. Screenshot
hashes are intentionally sensitive; an engine/font/reference change requires a
new approved reference and baseline lineage. Rollback of these controls requires
a superseding ADR because deleting a command, target guard, or baseline-history
rule would weaken an accepted architecture gate.

## Verification

- `python tools/verify.py --profile foundation`
- `python tools/verify.py --profile desktop`
- `python tools/taskctl.py validate`
- Desktop regressions for fixture escape, token/route/workflow/accessibility
  drift, normative mapping, and same-reference baseline rewrite.
- Independent comparison of all 14 workflows, 32 route/page contracts, two
  themes, two responsive viewports, keyboard interactions, and 64 screenshot
  hashes on the pinned Windows renderer.

## Task links

- `CAP-00.S06.T04`
