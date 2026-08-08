# Continuous integration

The pull-request gate is defined by `.github/workflows/ci.yml` and governed by
`ci-policy.json`. `tools/ci_check.py` validates both files locally, including the
full action commit pins, Windows runner label, least-privilege permissions,
required commands, unique artifact names, and fourteen-day report retention.

## Required jobs

| Job | Responsibility | Retained report |
|---|---|---|
| `foundation` | Repository, workflow, architecture, ADR, quality, packaging-input, unit, and backlog gates. | `ci-foundation.json` |
| `quality` | Ruff formatting, Ruff linting, and mypy over the explicit governed Python scope. | `ci-quality.json` |
| `contracts` | Foundation plus portable cross-process contract tests through the service profile. | `ci-contracts.json` |
| `packaging-smoke` | Frozen Python, Node.js, and Rust dependencies plus locked packaging-source validation. | `ci-packaging-smoke.json` |

The workflow runs on pull requests, pushes to `main`, and explicit manual
dispatches. Superseded runs on the same ref are cancelled. Every job uploads its
machine-readable report with `always()` so a report remains downloadable when a
verification command fails. Reports are retained for fourteen days and never
include hidden files.

## Security and reproducibility

The root permission is only `contents: read`; checkout credential persistence is
disabled. The workflow must not reference repository or production secrets and
must not use `pull_request_target`. GitHub actions are pinned to full reviewed
commit SHAs, while their release versions remain recorded in `ci-policy.json`.
Runtime versions and dependency resolution come from the repository's exact pins
and frozen lockfiles.

Run the hosted-CI equivalents locally before completing a task:

```powershell
.venv\Scripts\python.exe tools/ci_check.py --repo .
.venv\Scripts\python.exe tools/quality_check.py --repo . --report artifacts/tmp/local-quality.json
.venv\Scripts\python.exe tools/verify.py --profile foundation --report artifacts/tmp/local-foundation.json
.venv\Scripts\python.exe tools/verify.py --profile service --report artifacts/tmp/local-contracts.json
```

The packaging smoke gate qualifies locked source inputs only. Installer creation,
signing, upgrade, repair, rollback, and removal remain owned by their later CAP-00
slices and must not be inferred from this smoke result.

Primary action and runner sources:

- https://github.com/actions/checkout
- https://github.com/actions/setup-python/releases
- https://github.com/actions/setup-node
- https://github.com/actions/upload-artifact/releases
- https://github.com/actions/runner-images
