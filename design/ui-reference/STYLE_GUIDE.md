# Research Observatory — Academic Minimal Style and Experience Guide

**Version:** 1.3  
**Reference ID:** `RO-UI-ACADEMIC-MINIMAL-1.3`  
**Purpose:** Approved implementation specification for the crisp light / deep-navy Research Observatory interface on Windows, macOS, and Linux desktops.

## 1. Authority and design-first change order

This guide, `assets/tokens.css`, `WORKFLOW_CATALOG.*`, `CAPABILITY_COVERAGE.*`, `SITE_MANIFEST.json`, and the linked HTML pages form the approved experience reference. Tokens, semantic states, page regions, workflow order, accessibility behavior, and approved visual baselines are normative. Mock names, values, studies, vendors, prose, and inactive controls are illustrative.

Intentional experience changes are design-first: update the guide, workflow/page contracts, and affected HTML; run reference validation; obtain explicit human approval and a new reference ID; only then implement application code. Defect fixes may restore the current approved reference without redesign.

## 2. Design character

Research Observatory is a rigorous academic workbench rather than a consumer chat interface. Use quiet structure, fine borders, compact information density, restrained royal-blue interaction accents, serif page and manuscript titles, and deep navy—not black—for dark mode. Generated prose is downstream of evidence, study-design, result, manuscript, or review objects.

## 3. Color system

| Token | Light | Dark | Use |
|---|---|---|---|
| Canvas | `#F5F7FB` | `#061527` | Application background |
| Primary surface | `#FFFFFF` | `#0B1F37` | Main cards and panels |
| Secondary surface | `#F8FAFD` | `#102740` | Nested panels and selected rows |
| Elevated surface | `#FFFFFF` | `#142E49` | Drawers and popovers |
| Strong text | `#10233D` | `#F4F8FF` | Titles and primary values |
| Body text | `#32465F` | `#C8D5E5` | Body copy |
| Muted text | `#697B91` | `#8FA4BB` | Supporting metadata |
| Border | `#DCE4EE` | `#27415D` | Structural dividers |
| Primary action | `#2563EB` | `#5B91FF` | Links, selected navigation, main buttons |
| Primary hover | `#1D4ED8` | `#78A7FF` | Hover and active action |
| Success | `#15803D` | `#3FC071` | Verified, complete, approved |
| Warning | `#B45309` | `#F5A94B` | Attention, partial, pending |
| Danger | `#B42318` | `#FF766B` | Failed, blocked, unsupported |
| Violet | `#6D4AFF` | `#9B84FF` | Optional, inferred, critical reading |
| Cyan | `#007C91` | `#45C4D6` | Extracted or machine-produced states |

Do not use color alone. Every state needs text, iconography, or shape. Charts use the semantic palette in the order blue, cyan, violet, green, amber, red, then neutral.

## 4. Typography

| Role | Size / line height | Weight | Family |
|---|---:|---:|---|
| Display | 40 / 48 px | 600–650 | Source Serif 4, Iowan Old Style, Georgia |
| Page or manuscript title | 32 / 40 px | 650 | Serif |
| Section title | 22 / 30 px | 650 | Serif or UI sans |
| Card title | 15 / 22 px | 650 | Inter, Segoe UI, system sans |
| Body | 14 / 21 px | 400 | UI sans |
| Compact/table | 12 / 18 px | 400–600 | UI sans |
| Label | 11 / 16 px | 650 | UI sans, uppercase sparingly |

Body text may not fall below 12 px. Long manuscript text uses a 16–17 px serif face with 1.55–1.7 line height and a 70–78 character measure.

## 5. Geometry and spacing

- Base spacing unit: 4 px.
- Desktop page padding: 28 px; compact desktop: 20 px; mobile: 16 px.
- Expanded navigation: 240 px; collapsed: 72 px.
- Top bar: 64 px.
- Standard grid gap: 16 px; dense gap: 12 px; section gap: 24–32 px.
- Card radius: 10 px; control radius: 8 px; pills: 999 px.
- Card padding: 16 px; large card: 20 px.
- Control heights: compact 32 px, standard 40 px, primary 44 px.
- Table rows: 38 px dense, 44 px standard.
- Right evidence/review inspector: 360–400 px.
- Focus ring: 2 px primary with 2 px offset.
- Shadows remain subtle; borders provide most hierarchy.

## 6. Application shell and guided workflows

The top bar contains product identity, current project, universal search, notification/help actions, and user or local-profile controls. The sidebar gives the selected use case an ordered, numbered primary workflow. Completed, current, upcoming, optional, blocked, and attention-required steps must be visually distinguishable. All tools remain accessible in a secondary disclosure. Opening a supporting tool preserves workflow context and offers return to the current step.

Project creation presents the approved workflow catalog. Changing use case previews navigation and output effects and versions the Research Intent Contract. Every workflow page shows current step, rationale, previous/next action, relevant quality gate, and expected output.

## 7. Research-production workspaces

### Study Design Studio
Use a three-pane layout: 280 px stage rail, flexible design workspace, 360 px evidence/validity inspector. Alternatives must be comparable on design logic, feasibility, ethics, validity, data, and analysis—not reduced to one opaque score.

### Manuscript Blueprint
Use 260 px outline navigation, a flexible section-and-claim plan, and a 360 px evidence/venue inspector. Show article type, venue constraints, section purposes, word budgets, planned claims, required evidence, and unresolved prerequisites.

### Technical Reports & Results
Use a 260 px private-report library and flexible result reconciliation workspace. Distinguish reported, extracted, verified, disputed, and author-adjudicated results. Never infer unreported statistics. Tables, figures, methods, limitations, and deviations retain exact report anchors.

### Manuscript Studio
Use a 260 px outline, a minimum 640 px writing surface, and a 360 px evidence/result inspector. Mark supported, partially supported, blocked, and author-written claims. Manuscript text must trace to accepted evidence packets, verified results, and approved blueprint sections.

### Reviewer Simulation
Use independent reviewer-role cards, comment filters, editorial synthesis, and evidence links. Reviewers do not share hidden rationales or converge before completing independent assessments. The interface must never report acceptance probability or impersonate named real reviewers.

### Revision & Response
Use 280 px issue clusters, a flexible revision/diff and response editor, and a 320 px lineage inspector. Preserve original comment, author disposition, revised passage, response text, evidence links, and re-review result.

## 8. Semantic evidence and production states

- Observed: direct source or report content.
- Extracted: machine-structured from observed content.
- Inferred: analytical relation not explicitly stated.
- Verified: independently checked against a passage, report, or reproducible calculation.
- Disputed: credible alternatives remain.
- Adjudicated: researcher decision and rationale recorded.
- Stale: a dependency changed.
- Blocked claim: insufficient evidence or result support; drafting must stop or use explicit qualification.
- Draft: editable author-facing material not yet approved.
- Reviewed: evaluated in a specific simulated review round.
- Revised: changed in response to an accepted issue.

## 9. Interaction and accessibility

Meet WCAG 2.2 AA. Maintain visible focus, logical tab order, accessible names, predictable Escape behavior, list/table alternatives for spatial views, reduced-motion support, and non-color status cues. Use confirmation only for destructive, privacy-sensitive, externally transmitted, or difficult-to-reverse actions. Preserve keyboard operation for workflow navigation, tables, evidence linking, manuscript outlines, review triage, and dialogs.

## 10. Cross-platform parity

Qualify both themes and all research workflows on Windows x64, macOS Apple Silicon, Linux x64, and Linux ARM64. Platform-native menus, file dialogs, key labels, credential prompts, GPU/provider availability, and packaging may differ. Project data, scholarly objects, semantic states, workflow order, page contracts, evidence lineage, and manuscript/review behavior may not.

## 11. Compliance automation

Retain this entire directory under `design/ui-reference/`. Automated checks validate approval and hashes; token parity; route/link/landmark/ID integrity; workflow and capability coverage; required regions; accessibility; light/dark screenshots; responsive behavior; and application conformance. `desktop` and `desktop-cross-platform` verification profiles invoke UI-reference integrity, page-contract, workflow, token, accessibility, interaction, and visual-regression subchecks. Research-production pages additionally invoke `study-design`, `results`, `manuscript`, and `reviewer` checks.
