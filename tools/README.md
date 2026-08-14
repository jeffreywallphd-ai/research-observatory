# Repository automation tools

- `planctl.py` - prepare/review complete Wave packets and record one commit-bound pre-Wave approval.
- `taskctl.py` - select wave-scoped capability increments, present descriptive aliases, claim/renew leases, enforce ordered slices and sequential wave-exit gates, attach exact-commit evidence, and atomically compare-and-swap state.
- `backlog_views.py` - deterministically render the comprehensive Markdown plan and compact status summary from `planning/backlog.yaml`, or fail on generated-view drift with `--check`.
- `capability_plan_check.py` and `slice_plan_check.py` - validate canonical plans.
- `plan_review_site.py` and `plan_review_check.py` - generate and validate the static review site.
- `ui_reference_check.py` - validate the approved experience reference.
- `ui_change_gate.py` - enforce exact task/PR reference lineage, human design approval, reference-before-code ordering, and governed restoration evidence.
- `ui_conformance.py` plus `ui_*_check.py` entry points - compare the activated desktop target with approved tokens, routes, workflows, accessibility/responsive behavior, and controlled visual baselines.
- `repository_structure_check.py` - validate declared module boundaries and reject deferred implementation or committed binaries.
- `runtime_check.py` - validate exact runtime/package-manager pins and report actionable mismatches.
- `bootstrap.py` - verify prerequisites, perform frozen installs, generate local development configuration, and run the foundation smoke gate.
- `architecture_check.py` - validate repository-area purposes, module dependency rules, stable interfaces, and deployment-profile boundaries.
- `agent_protocol_check.py` - enforce one pre-Wave approval, durable Wave execution, READY-only selection, multi-level verification, review boundaries, and task briefing.
- `adr_new.py` - create a task-linked Proposed ADR and update the decision index in one guarded command.
- `adr_check.py` - validate ADR states/index/task links and require matching changed ADRs for protected architecture paths.
- `verify.py` - run composable task-facing verification profiles and emit command, duration, failure, and JSON report evidence.
- `ci_check.py` - enforce pinned actions, least-privilege triggers, required CI jobs, and retained failure evidence.
- `quality_check.py` - run governed Ruff formatting/lint and mypy checks with a structured report.
- `packaging_smoke_check.py` - validate frozen packaging source inputs without producing or signing binaries.
- `install_trivy.py` - install and verify the per-platform checksum-pinned security scanner in ignored local state.
- `security_check.py` - scan source and dependencies, enforce release/exception policy, and emit sanitized evidence.
- `fixture_corpus_check.py` - validate the synthetic scholarly fixture corpus license, provenance, exact inventory, hashes, semantic coverage, and intentional malformed inputs offline.
- `benchmark_registry.py` - validate and run pinned golden/contract benchmarks, emit deterministic results, and enforce versioned human-approved baseline changes without overwriting baselines.
- `build_manifest.py` - validate the single product version and generated component contracts, then emit deterministic commit/dependency/schema/model-set build provenance with dirty-state labeling.

Run these from the repository root after the setup kit has installed `repo-seed/`. The external setup package is not the repository.
