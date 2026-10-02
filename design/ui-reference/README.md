# Research Observatory UI Reference Proposal

This directory is an inert **Academic Minimal 1.8 proposal**, copied from the approved 1.7 package. It is not the active experience authority. See `APPROVAL.yaml` for the pending status.

## Start with the workflow

Open `ingestion-reconciliation.html#attach-full-text` for the proposed selected work/version attachment interaction, `document-reader.html#reader-source-context` for the future reader and selected-version return contract, or `prototype-index.html` for every reference page. The fourteen guided workflow sequences are inherited unchanged.

## Authority

- The approved 1.7 package under `design/ui-reference/` remains the implementation authority until this exact proposal receives human approval and a new approval record.
- The 1.8 change is bounded to the inline Ingestion Review attachment contract, an exact-revision status/route handoff, future Document Reader return, and proposal metadata; illustrative names, files, states and inactive actions create no backend scope.
- `APPROVAL.yaml` records the proposal status; `REFERENCE_MANIFEST.yaml` identifies governed files.

## Open locally

```bash
python -m http.server 8080
```

Then open `http://localhost:8080/ingestion-reconciliation.html#attach-full-text`.

## Shared implementation

- `assets/tokens.css` — inherited light/dark tokens.
- `assets/app.css` — shared components and proposed attachment panel styling.
- `assets/app.js` — local, inert picker/drop interaction; no file bytes are read and no acquisition occurs.
- `STYLE_GUIDE.md` / `style-guide.html` — technical and visual specification.
- `WORKFLOW_CATALOG.md` / `.json` — fourteen inherited use-case sequences.
- `CAPABILITY_COVERAGE.md` / `.json` — page contracts and capability mapping.
- `scripts/build_mockups.py` — deterministic page generator.
- `scripts/verify_site.py` — reference integrity checks.

University/cloud administrator consoles remain deferred.
