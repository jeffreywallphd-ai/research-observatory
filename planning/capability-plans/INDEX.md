# Capability decision and execution plan index

Supplemental release `1.3.4` extends the one-time capability decision gate through CAP-19. Each packet documents credible options, an explicit recommendation, the preselected best-in-class recommendation or a reasoned human override, cross-slice contracts, verification, and the restricted conditions that may reopen planning.

## Automation

- `python tools/planctl.py review CAP-XX` regenerates the static review site and prints the selected capability link.
- Reviewers confirm or override resolved recommendations near the top of the capability page, inspect linked slice pages, and export one decision-feedback JSON record.
- `apply-feedback` is optional and records reasoned overrides or notes; `approve` is the explicit one-time approval of the decision-complete packet and all slice plans.
- `python tools/planctl.py --repo . prepare CAP-XX` creates missing proposed plans from governed templates.
- `python tools/planctl.py --repo . adopt-recommendations CAP-XX` rejects placeholders and records each researched recommendation as the completed selected default.
- `python tools/planctl.py decisions CAP-XX` reports recommendations, blockers, approval state, and review link.
- `python tools/planctl.py validate CAP-XX` performs structural validation.
- `python tools/planctl.py ready CAP-XX --require-approved` is the mandatory pre-execution gate.
- `taskctl capability start/resume` invokes readiness and cannot bypass it.

- [`CAP-01` — Windows-first desktop shell and supervised local runtime](CAP-01.md) — 3 decisions; `proposed` / `complete` / approval `pending`
- [`CAP-02` — Local projects, durable storage, security, and recovery](CAP-02.md) — 3 decisions; `proposed` / `complete` / approval `pending`
- [`CAP-03` — Canonical domain, research intent, provenance, and durable workflows](CAP-03.md) — 4 decisions; `proposed` / `complete` / approval `pending`
- [`CAP-04` — Scholarly ingestion, connectors, canonicalization, and corpus governance](CAP-04.md) — 4 decisions; `proposed` / `complete` / approval `pending`
- [`CAP-05` — Document acquisition, parsing, source inspection, and page anchors](CAP-05.md) — 3 decisions; `proposed` / `complete` / approval `pending`
- [`CAP-06` — Local search, discovery, corpus diagnostics, and screening](CAP-06.md) — 23 decisions; `proposed` / `complete` / approval `pending`
- [`CAP-07` — Provider-neutral model gateway and governed AI execution](CAP-07.md) — 20 decisions; `proposed` / `complete` / approval `pending`
- [`CAP-08` — Evidence schemas, extraction, verification, and adjudication](CAP-08.md) — 23 decisions; `proposed` / `complete` / approval `pending`
- [`CAP-09` — Scholarly graph, comparison sets, synthesis, and reproducibility](CAP-09.md) — 23 decisions; `proposed` / `complete` / approval `pending`
- [`CAP-10` — Novelty auditing, research opportunities, and plural research modes](CAP-10.md) — 26 decisions; `proposed` / `complete` / approval `pending`
- [`CAP-11` — Windows PC/lab product hardening, validation, packaging, and release](CAP-11.md) — 18 decisions; `proposed` / `complete` / approval `pending`
- [`CAP-12` — University-hosted deployment, institutional identity, collaboration, and operations](CAP-12.md) — 18 decisions; `proposed` / `complete` / approval `pending`
- [`CAP-13` — Managed cloud control plane, tenant data planes, governance, and SaaS operations](CAP-13.md) — 18 decisions; `proposed` / `complete` / approval `pending`
- [`CAP-14` — Cross-platform desktop qualification and release](CAP-14.md) — 18 decisions; `proposed` / `complete` / approval `pending`
- [`CAP-15` — Empirical study design and protocol development](CAP-15.md) — 18 decisions; `proposed` / `complete` / approval `pending`
- [`CAP-16` — Manuscript blueprint, venue profiles, and article architecture](CAP-16.md) — 18 decisions; `proposed` / `complete` / approval `pending`
- [`CAP-17` — Technical report and study-results integration](CAP-17.md) — 18 decisions; `proposed` / `complete` / approval `pending`
- [`CAP-18` — Source-grounded manuscript drafting and publication artifacts](CAP-18.md) — 18 decisions; `proposed` / `complete` / approval `pending`
- [`CAP-19` — Reviewer simulation, editorial synthesis, and revision](CAP-19.md) — 18 decisions; `proposed` / `complete` / approval `pending`

Plans for future capabilities are created on demand from `TEMPLATE.md`; generated plans remain proposed until completed and approved.
