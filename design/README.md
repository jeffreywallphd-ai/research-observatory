# Design governance

`ui-reference/` contains the approved Academic Minimal design tokens, workflow catalog, page contracts, linked HTML reference, approval metadata, hashes, and visual baselines.

Intentional experience changes update and approve this reference before application implementation. See root `AGENTS.md` and `docs/automation/project-automation-guide.md`.

`ui-change.schema.json` governs per-task implementation lineage contracts stored
under `artifacts/evidence/ui-change/`. The design-first gate verifies those
contracts against immutable Git history, the task ledger, and the exact approved
reference package.
