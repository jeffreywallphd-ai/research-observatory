# Toolchain and lockfile contract

The W0-W5 repository uses exact runtime and package-manager pins. The canonical
machine-readable values live in `runtime-versions.json`; conventional version
files repeat those values for ecosystem tooling and are checked for drift.

| Tool | Pin | Declaration |
|---|---:|---|
| Node.js | 24.19.0 LTS | `.node-version`, `.nvmrc`, `package.json` |
| Python | 3.14.6 | `.python-version`, `pyproject.toml` |
| Rust | 1.96.1 | `rust-toolchain.toml` |
| pnpm | 11.20.0 | `package.json` |
| uv | 0.12.2 | `runtime-versions.json` |
| Trivy | 0.73.0 | `security-toolchain.json` with per-platform archive and executable SHA-256 |

The Python development group also pins Ruff 0.15.22, mypy 2.3.0, and
types-PyYAML 6.0.12.20260518. `quality-scope.json` closes the Python quality
boundary: every `.py` file discovered beneath its application, service, package,
worker, tool, and test roots must be explicitly listed. An unlisted addition or
stale entry fails before formatting, lint, or type checks can run. The approved
UI-reference generator has its own immutable-reference checks outside this code
boundary.

The pins select a supported Node LTS line, the current Python feature release,
and stable Rust and package-manager releases as of the decision date. Upgrade
them only through a reviewed change that regenerates every affected lockfile and
passes the foundation, security, desktop, and service profiles as applicable.

## Deterministic installs

```powershell
corepack pnpm install --frozen-lockfile
uv sync --frozen --no-install-project
cargo fetch --locked
.venv\Scripts\python.exe tools/install_trivy.py --repo .
```

These commands may consume the network or an already populated cache, but must
not resolve or rewrite dependency versions. `tools/runtime_check.py` validates
the declarations and reports actionable remediation for missing or mismatched
tools. The Python lock includes PyYAML because the repository workflow and
planning commands parse the governed YAML backlog. Trivy is installed into
ignored checkout-local state and validates its own reported version after
checksum-verified extraction. CAP-00.S01.T03 owns runtime installation and
developer-environment generation; CAP-00.S03.T03 owns the security scanner.

Primary sources:

- https://nodejs.org/en/about/previous-releases
- https://www.python.org/downloads/source/
- https://blog.rust-lang.org/2026/06/30/Rust-1.96.1/
- https://pnpm.io/installation
- https://docs.astral.sh/uv/concepts/projects/sync/
