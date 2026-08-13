# Static capability and slice planning review

> **Repository destination:** `docs/automation/planning-review-site.md`. The generated site under `planning/review-site/` is a review surface; capability and slice Markdown plans remain canonical.

## Entry points and navigation

- `planning/review-site/index.html` - all capability packets.
- `planning/review-site/waves/WN.html` - one wave's capability increments,
  ordered slices, progress, and exit/activation gate decision.
- `planning/review-site/CAP-XX/index.html` - decision register and approval surface.
- `planning/review-site/CAP-XX/CAP-XX.SYY.html` - individual slice plan.

The left navigation is a two-tab planning switcher on every page:

- **Waves** is the default on the review-center and wave pages. It exposes the
  primary execution sequence and each wave's exit/activation gate.
- **Capabilities** is the default while reviewing a capability or one of its
  ordered slices. It preserves the product-outcome view without obscuring wave
  placement.

The tabs support pointer activation plus Left/Right, Home, and End keyboard
navigation. Switching tabs changes only the navigation view; it never changes
approval or backlog state.

Use `python tools/planctl.py --repo . review CAP-XX --wave WN` to regenerate and print directly openable links.

Capability aliases and descriptive slice labels are the default presentation.
Canonical `CAP-XX` and `CAP-XX.SYY` values remain visible because they are
immutable evidence keys; slice numbers also preserve the declared sequence.

## Decision controls

Every decision contains:

- the documented candidate options;
- the preselected best-in-class recommendation;
- an `Other` option;
- a brief Other-description input, visible and required only when Other is selected; and
- a separate detailed feedback/rationale textarea.

The Other brief description should name the proposed direction concisely. The detailed rationale should explain why it is preferable, constraints, required evidence, and any approval conditions.

## Feedback format

The site exports `capability-decision-feedback` schema `1.1`.

A documented choice resembles:

```json
{
  "id": "CAP-XX-D01",
  "selected_option": "A documented candidate",
  "other_option": null,
  "accepted_recommendation": false,
  "rationale": "Detailed reason for the override"
}
```

An Other choice resembles:

```json
{
  "id": "CAP-XX-D01",
  "selected_option": "__OTHER__",
  "other_option": "Use a hybrid local-first index with hosted overflow",
  "accepted_recommendation": false,
  "rationale": "Detailed constraints, tradeoffs, and validation conditions"
}
```

Other requires both `other_option` and rationale. The brief description is limited by the interface; detailed reasoning belongs in rationale.

## Applying feedback

```bash
python tools/planctl.py --repo . apply-feedback CAP-XX <downloaded-json>
```

For Other, `planctl`:

1. validates schema, plan hash, complete decision coverage, description, and rationale;
2. creates the canonical candidate `Other: <brief description>` if not already present;
3. records that candidate as `selected_option` and marks the decision accepted;
4. archives the original JSON, preserving detailed rationale;
5. regenerates the review site; and
6. leaves capability and slice approval pending.

Feedback is never implicit approval.

## Approval

If defaults are accepted with no notes or overrides:

```bash
python tools/planctl.py --repo . approve CAP-XX --wave WN --by "<reviewer>" --commit <git-sha>
```

If feedback was exported:

```bash
python tools/planctl.py --repo . approve CAP-XX --wave WN --feedback <downloaded-json> --by "<reviewer>" --commit <git-sha>
```

Approval applies to the decision-complete capability packet and every ordered
slice plan in `WN`. Future-wave plans may remain proposed until their activation
gate. Historical approvals covering all slices remain valid.

## Generation and validation

```bash
python tools/plan_review_site.py --repo .
python tools/plan_review_check.py --repo . --report artifacts/planning-review-site-validation.json
node --check planning/review-site/assets/review.js
```

The validator must confirm page/plan hashes, decision IDs, internal links, and the presence of Other controls on every capability decision.

## Change control

Do not edit generated decision cards by hand. Change `tools/plan_review_site.py`, canonical plans, or shared site assets, regenerate, and validate. A site generated from stale plan hashes cannot authorize feedback or approval.
