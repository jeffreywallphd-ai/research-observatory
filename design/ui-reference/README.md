# Research Observatory UI Reference

This directory is the approved, linked, offline experience reference for the PC/lab-first Research Observatory researcher application using **Academic Minimal 1.4**.

## Start with the workflow

Open `new-project.html` to see use-case selection, `index.html` for the current project workflow, `application-settings.html` for app-wide Security & sign-in, or `prototype-index.html` for every reference page. The sidebar's primary use-case selector changes the ordered guided navigation. The full tool inventory remains available under **All tools**.

## Authority

- `assets/tokens.css`, semantic rules in `STYLE_GUIDE.md`, the fourteen profiles in `WORKFLOW_CATALOG.*`, route inventory, required page regions, accessibility behavior, and approved visual baselines are normative.
- Mock names, values, studies, providers, dates, prose, charts, and inactive actions are illustrative and do not create backend scope.
- `APPROVAL.yaml` records approval; `REFERENCE_MANIFEST.yaml` identifies governed files; `CAPABILITY_COVERAGE.*` maps capabilities to pages.
- Intentional user-facing changes require an updated proposed reference, validation, human approval, and only then application implementation.

## Open locally

```bash
python -m http.server 8080
```

Then open `http://localhost:8080/prototype-index.html`.

## Shared implementation

- `assets/tokens.css` — canonical light/dark tokens.
- `assets/app.css` — shared shell, workflow navigation, components, layouts, data displays, and responsive behavior.
- `assets/app.js` — theme, sidebar, tabs, mock actions, use-case selection, adaptive workflow ordering, and context guidance.
- `STYLE_GUIDE.md` / `style-guide.html` — technical and visual specification.
- `WORKFLOW_CATALOG.md` / `.json` — authoritative use-case sequences and outputs.
- `CAPABILITY_COVERAGE.md` / `.json` — page contracts and capability mapping.
- `scripts/build_mockups.py` — deterministic page generator.
- `scripts/verify_site.py` — reference integrity checks.

University/cloud administrator consoles remain intentionally deferred and require active W10/W11 requirements and separately approved page contracts.
