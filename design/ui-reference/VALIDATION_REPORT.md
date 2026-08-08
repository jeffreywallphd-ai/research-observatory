# Research Observatory UI Reference Validation Report

**Baseline:** Academic Minimal v1.3  
**Reference ID:** `RO-UI-ACADEMIC-MINIMAL-1.3`  
**Date:** August 7, 2026

## Scope

- 32 PC/lab researcher-facing product pages.
- 14 approved objective-specific workflow profiles.
- 1 visual style-guide page and 1 prototype index.
- Shared light/dark design tokens, component stylesheet, print stylesheet, and interaction script.
- Governed approval, reference manifest, capability coverage, page inventory, workflow catalog, and deterministic validation scripts.
- Complete Chromium light/dark renders for every product page and the style guide.
- Six research-production surfaces: Study Design Studio, Manuscript Blueprint, Technical Reports & Results, Manuscript Studio, Reviewer Simulation, and Revision & Response.

## Automated checks

| Check | Result |
|---|---|
| Reference approval, ID, status, and governed-file hashes | Passed after v1.3 hash regeneration |
| Product-page inventory | Passed; exactly 32 product pages and 34 HTML documents |
| Capability-to-page coverage | Passed; all 20 approved capabilities are represented or explicitly identified as repository/hosted infrastructure rather than desktop pages |
| Workflow catalog | Passed; exactly 14 profiles with valid purpose, output, routes, ordered/cyclical behavior, and handoffs |
| Project creation and adaptive workflow markers | Passed |
| Complete tool access and supporting-tool return behavior | Passed |
| Research-production page contracts and safeguards | Passed |
| Local links and assets | Passed; no broken or package-escaping references |
| Shared styles and behavior | Passed on all 34 HTML documents |
| Main/navigation landmarks, page titles, and theme controls | Present |
| Duplicate HTML IDs | None detected |
| Icon-only button accessible names | Present |
| JavaScript syntax | Passed with `node --check` |
| Python generator/validator/render compilation | Passed |
| CSS parsing | Passed for all shared stylesheets |
| Theme toggle, sidebar collapse, tabs, use-case selection, and mock feedback | Passed in Chromium |
| Adaptive workflow navigation | Passed across all 14 profiles |
| Light/dark render identity | Passed; requested theme equals initialized document theme before capture |
| Complete visual rendering | Passed; 33 governed pages rendered in both themes, with comparison images generated |
| Backlog and reference alignment | Passed; planning includes governed-reference, workflow, cross-platform, study-design, result, manuscript, and reviewer verification profiles |

## Visual review

All 32 product pages were inspected in light and dark mode through four contact sheets, and the six research-production pages were inspected at full comparison size. Light mode uses crisp white/slate surfaces with restrained royal blue. Dark mode uses deep navy surfaces and controlled cool-blue interaction states. Information density, typography, focus hierarchy, tables, inspectors, graphs, and status semantics remain consistent.

The project-creation and project-home views make the selected use case and ordered workflow prominent. Each workflow page exposes the current stage, previous and next stages, rationale, quality state, and expected output. Supporting workspaces remain accessible through **All tools** and preserve a route back to the current workflow stage.

The new pages visibly enforce the expanded integrity model:

- Study Design Studio compares alternatives and exposes evidence, validity, ethics, feasibility, and human approval gates.
- Manuscript Blueprint requires an article architecture and evidence/claim plan before long-form drafting.
- Technical Reports & Results separates reported, extracted, verified, disputed, and adjudicated study evidence.
- Manuscript Studio exposes claim, citation, result, and authorship support while blocking unsupported claims.
- Reviewer Simulation keeps reviewer roles independent before editorial synthesis and disclaims acceptance prediction.
- Revision & Response preserves comments, dispositions, manuscript diffs, responses, evidence changes, and re-review.

## Reconciliation findings addressed

Version 1.3 extends the prior evidence-and-opportunity workbench through cross-platform desktop qualification and an evidence-to-publication lifecycle. It adds no tenant, billing, university-administration, or cloud-operations surfaces before their approved waves. Mock studies, counts, prose, venues, and chart values remain illustrative and do not create implementation requirements beyond the page/workflow contracts.

Critical and hermeneutic support is scheduled before critical/theory article production; advanced detector ensembles, portfolio ranking, convergence monitoring, and living intelligence remain in the later research-intelligence wave.

## Limits

These files are governed static experience references with simulated controls and mock data. They do not implement persistence, retrieval, model execution, statistical analysis, rights enforcement, study conduct, or backend workflows. Automated reference checks do not replace production accessibility testing, platform qualification, researcher usability studies, security/privacy testing, methodological review, or application-conformance evidence. The application must emit a route/workflow/token/reference manifest and pass interaction, accessibility, responsive, cross-platform, research-integrity, and controlled visual-regression gates against this approved reference.
