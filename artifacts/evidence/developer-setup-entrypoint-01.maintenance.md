# Windows developer setup entrypoint

The owner requested a root `setup.cmd` that prepares the pinned prerequisites
and invokes the existing bootstrap in one call. This bounded developer-setup
increment adds that entrypoint, its CMD/PowerShell runtime helper, focused
Windows tests, and setup instructions. It changes no product, taskctl, runtime
pin, lockfile, verification criterion, or approval.

The inspected predecessor is commit
`1e463df5c7080b0f19ef4b82ae0929858620420f`. Its existing bootstrap test source
has SHA-256 `c5ce000b9e9d3ef28eb07a28e457fd6f2afd2ff45e64326ea4c626c71cdb966a`;
the developer-bootstrap guide has SHA-256
`8f89841dc783e2184a18ad6005f0a78b1a2f5da5497eb911eed2526d335d88e4`.
These exact predecessor bytes remain in Git and the ignored local source note.
The root README's setup command also changes to `setup.cmd` for discoverability.
Risk-selected checks cover the additive developer entrypoint and acquisition
helper; existing product and release qualification remain separate.

`setup.cmd` locates its own checkout, forwards arguments and failure status,
and leaves an explicit place for later setup steps. The helper validates the
declared Node 24.19.0/Python 3.14.6/pnpm 11.20.0 contract, requires existing
uv 0.12.2, verifies the official Node ZIP SHA-256 before extraction, and uses
checkout-local Node/Python/Corepack. Existing incompatible directories are
preserved; global installations and persistent environment settings are not
changed. The promoted PowerShell source exactly matches the previously
independently reviewed helper (SHA-256
`61737d238abab1a07190af84bb1209ee610944fa35ec82fd3789a6696151934c`).
Rust 1.96.1 and the documented native build tools remain prerequisites.

Precommit checks passed six focused bootstrap/setup tests, affected-file Ruff
format and lint, and Windows PowerShell 5.1 syntax parsing. The four new cases
exercise the real CMD/PowerShell plan path from an unrelated working directory
and a path containing spaces, argument/exit-code forwarding, invalid-root
denial, and changed-pin denial. Synthetic fixtures auto-clean. The two existing
bootstrap tests use their original fake command runner.

Private precommit observations and source hashes are retained in
`artifacts/tmp/setup-entrypoint-01/precommit-validation-04.json`. Initial
sandbox temporary-directory permission errors, the test-launcher quoting
failure, a lint finding, and a syntax-parser execution-policy denial remain
preserved there and in referenced local logs. The launcher transport was
corrected without changing its assertions; syntax parsing used a process-only
execution-policy setting.

These checks do not establish runtime installation, network acquisition,
dependency-bootstrap, or clean-machine success. No download, runtime install,
actual dependency bootstrap, or broad product verification was run. Final
commit-bound verification, fresh-clone plan-only verification, independent
disposition, and local-main integration remain with the campaign owner.
