# Repository automation tools

- `planctl.py` - prepare, review, apply feedback, approve, validate, and gate capability plans.
- `taskctl.py` - schema-validate, select, claim/renew owned leases, enforce transitions and release gates, attach exact-commit evidence, and atomically compare-and-swap capability/slice/task state.
- `backlog_views.py` - deterministically render the comprehensive Markdown plan and compact status summary from `planning/backlog.yaml`, or fail on generated-view drift with `--check`.
- `capability_plan_check.py` and `slice_plan_check.py` - validate canonical plans.
- `plan_review_site.py` and `plan_review_check.py` - generate and validate the static review site.
- `ui_reference_check.py` - validate the approved experience reference.
- `repository_structure_check.py` - validate declared module boundaries and reject deferred implementation or committed binaries.
- `runtime_check.py` - validate exact runtime/package-manager pins and report actionable mismatches.
- `bootstrap.py` - verify prerequisites, perform frozen installs, generate local development configuration, and run the foundation smoke gate.
- `architecture_check.py` - validate repository-area purposes, module dependency rules, stable interfaces, and deployment-profile boundaries.
- `agent_protocol_check.py` - enforce atomic all-slice approval, durable capability execution, READY-only selection, scope/check/evidence rules, and task briefing.
- `adr_new.py` - create a task-linked Proposed ADR and update the decision index in one guarded command.
- `adr_check.py` - validate ADR states/index/task links and require matching changed ADRs for protected architecture paths.
- `verify.py` - run composable task-facing verification profiles and emit command, duration, failure, and JSON report evidence.
- `ci_check.py` - enforce pinned actions, least-privilege triggers, required CI jobs, and retained failure evidence.
- `quality_check.py` - run governed Ruff formatting/lint and mypy checks with a structured report.
- `packaging_smoke_check.py` - validate frozen packaging source inputs without producing or signing binaries.
- `install_trivy.py` - install and verify the per-platform checksum-pinned security scanner in ignored local state.
- `security_check.py` - scan source and dependencies, enforce release/exception policy, and emit sanitized evidence.
- `fixture_corpus_check.py` - validate the synthetic scholarly fixture corpus license, provenance, exact inventory, hashes, semantic coverage, and intentional malformed inputs offline.

Run these from the repository root after the setup kit has installed `repo-seed/`. The external setup package is not the repository.
