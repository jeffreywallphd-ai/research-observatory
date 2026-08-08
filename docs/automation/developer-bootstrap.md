# Developer bootstrap

The bootstrap is one sustained, fail-closed setup command. It checks every
runtime and package manager against `runtime-versions.json`, installs only from
committed lockfiles, creates the local development configuration, and ends by
running the foundation smoke profile.

## Prerequisites

Install the exact Node.js, Python, Rust, pnpm/Corepack, and uv versions in
[`toolchain.md`](toolchain.md), and make their commands available on `PATH`.
The bootstrap reports the expected version and installation action for each
missing or mismatched prerequisite. It does not silently substitute a runtime.

On Windows, from the repository root:

```powershell
.\bootstrap.cmd
```

On macOS or Linux, from the repository root:

```sh
python3 tools/bootstrap.py --repo .
```

Successful execution is idempotent. It runs these governed operations:

1. `corepack pnpm install --frozen-lockfile`
2. `uv sync --frozen --no-install-project`
3. `cargo fetch --locked`
4. `.venv` Python foundation verification

## Local state contract

The checkout-local outputs are limited to ignored paths:

- `.venv/` for the Python environment;
- `node_modules/` for pnpm installation metadata and packages;
- `.local/development.json` for non-secret development settings;
- `target/` if later Rust build commands are run.

Package managers also use their normal user-level download caches outside the
checkout. `.local/development.json` contains no credential or secret. Do not put
tokens, passwords, or keys in that file or in any `.env` file.

If setup fails, correct the reported prerequisite or frozen-install error and
run the same command again. The configuration file is written atomically only
after every dependency step and the smoke check pass.
