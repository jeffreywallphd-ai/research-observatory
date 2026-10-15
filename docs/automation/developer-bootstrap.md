# Developer bootstrap

The bootstrap is one sustained, fail-closed setup command. It checks every
runtime and package manager against `runtime-versions.json`, installs only from
committed lockfiles, installs the checksum-pinned security scanner, creates the
local development configuration, and ends by running the foundation smoke
profile.

## Prerequisites

On Windows x64, install uv **0.12.2** and Rust **1.96.1** as described in
[`toolchain.md`](toolchain.md), and make their commands available on `PATH`.
The native build also requires the documented Visual Studio build tools.
The setup entrypoint supplies the pinned Node.js, Python, and pnpm prerequisites.

From a fresh Windows clone or fork, run:

```powershell
.\setup.cmd
```

`setup.cmd` locates its own checkout, provisions Node.js **24.19.0**, Python
**3.14.6**, and pnpm **11.20.0**, then runs the existing bootstrap below. It
validates `runtime-versions.json` and the other declarations before proceeding.
Node comes from the SHA-256-verified official Windows archive; uv installs Python
into a checkout-local store without bin or registry registration. Corepack uses
a checkout-local cache. No machine-wide installation or persistent `PATH` change
is made.

To inspect the plan without downloads, tool execution, or writes:

```powershell
.\setup.cmd -PlanOnly
```

To provision only these runtime prerequisites, use
`.\setup-pinned-runtimes.cmd`; add `-RunBootstrap` to run the complete bootstrap.
The helper also accepts `-RepoRoot <fork-root>`. Existing incompatible or incomplete
local Node and `.venv` directories are preserved and reported as errors; move
them aside deliberately if replacement is wanted. Setup does not install uv,
Rust, Visual Studio, browser, model, or lab tools.

If the exact Node.js, Python, Rust, pnpm/Corepack, and uv versions are already
available, the validation/bootstrap entrypoint remains:

```powershell
.\bootstrap.cmd
```

It reports each missing or mismatched prerequisite and does not substitute a
runtime. On macOS and Linux, install all exact versions from the toolchain guide
before using the Python entrypoint below.

`bootstrap.cmd` prefers exact checkout-local runtimes under
`.local/toolchains/` when they exist, then falls back to `PATH`. This supports a
non-administrative setup without changing the machine-wide Node.js or Rust
installation. The directory is ignored and must contain only downloaded
toolchains and caches, never repository source or secrets.

On macOS or Linux, from the repository root:

```sh
python3 tools/bootstrap.py --repo .
```

Successful execution is idempotent. It runs these governed operations:

1. `corepack pnpm install --frozen-lockfile`
2. `uv sync --frozen --no-install-project`
3. `.venv` Python `tools/install_trivy.py --repo <checkout>`
4. `cargo fetch --locked`
5. `.venv` Python foundation verification

The foundation bootstrap does not download a browser. Before the Windows x64
desktop profile is first run, install its lock-pinned Chromium build:

```powershell
.venv\Scripts\playwright.exe install chromium
```

This download is a desktop qualification prerequisite, not an application
runtime dependency. The desktop checker fails actionably if the required build
is absent or its version differs.

## Local state contract

The checkout-local outputs are limited to ignored paths:

- `.venv/` for the Python environment;
- `node_modules/` for pnpm installation metadata and packages;
- `.local/development.json` for non-secret development settings;
- `.local/downloads/` for the verified Node archive and `.local/toolchains/` for
  checkout-local Node, Python, and Corepack prepared by Windows setup;
- `.local/toolchains/trivy/` and `.local/cache/trivy/` for the pinned scanner and its database cache;
- `target/` if later Rust build commands are run.

Package managers also use their normal user-level download caches outside the
checkout. `.local/development.json` contains no credential or secret. Do not put
tokens, passwords, or keys in that file or in any `.env` file.

If setup fails, its error includes both standard output and standard error. The
foundation gate saves its results, including the first failing check and its
diagnostics, to `artifacts/tmp/bootstrap-foundation-report.json`. An error before
verification starts may leave no current report. Correct the reported error and
run the same command again. The configuration file is written atomically only
after every dependency step and the smoke check pass.
