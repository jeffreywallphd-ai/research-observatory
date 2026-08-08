# Research Observatory

Research Observatory is an evidence-first, local-first scholarly reasoning and
research-production platform. The repository is organized as a Windows-first
monorepo with portable boundaries for later platforms and deployment profiles.

## Start here

- Read [`AGENTS.md`](AGENTS.md) before planning or implementation.
- Use [`planning/backlog.yaml`](planning/backlog.yaml) through `tools/taskctl.py`
  for authoritative work state.
- Use [`docs/README.md`](docs/README.md) to locate product, architecture,
  governance, and automation authorities.
- Validate the bootstrap foundation with
  `python tools/verify.py --profile foundation`.
- Prepare a Windows development checkout with `.\bootstrap.cmd`; see
  [`docs/automation/developer-bootstrap.md`](docs/automation/developer-bootstrap.md)
  for prerequisites and the cross-platform command.
- See [`docs/automation/toolchain.md`](docs/automation/toolchain.md) for pinned
  runtimes, package managers, and frozen-install commands.
- See [`docs/automation/build-manifests.md`](docs/automation/build-manifests.md)
  for product version, changelog, component compatibility, and build provenance.

## Monorepo boundaries

| Path | Responsibility |
|---|---|
| `apps/desktop/` | Tauri/React desktop shell and user-facing workspaces |
| `services/core-api/` | Packaged Python Core API modular monolith |
| `workers/` | Isolated, idempotent resource-specific activities |
| `packages/contracts/` | Portable schemas, API contracts, and generated clients |
| `packages/ui-tokens/` | Governed Academic Minimal design tokens |
| `packages/ui-components/` | Framework-facing reusable interface components |
| `tests/` | Cross-boundary foundation, desktop, contract, end-to-end, and packaging tests |
| `packaging/windows/` | Windows installer, upgrade, repair, and removal assets |
| `packaging/` | Product version authority, build inputs, and provenance schemas |

The machine-readable contract is [`repository-structure.json`](repository-structure.json).
Every declared module contains a README naming its owner and boundary. Hosted
administration, tenancy, SSO, PostgreSQL, Temporal, Helm, and Terraform
implementations are deliberately absent from the local W0-W5 skeleton.
