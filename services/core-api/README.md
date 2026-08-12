# Core API

Owner: Research Observatory maintainers
Boundary: Packaged Python modular monolith and local application composition root.

Domain and application policies remain separated from adapters. This module
owns local API composition and transactional coordination; resource-intensive
activities execute through worker contracts rather than inside request handlers.

`component-manifest.json` is the generated Core API sidecar version contract. It
must mirror the single product version in `packaging/product-version.json`.

## Development contract

The service source is in `src/research_observatory_core`. It is a local-only
FastAPI modular monolith with explicit health, readiness, version, safe
configuration, registered-module, and capability projections. It binds only to
a canonical numeric loopback address; port `0` delegates port selection to the
operating system. The native host owns the bounded startup handshake and
authenticated local transport. An unsupervised service instance has no launch
credential and denies HTTP requests by design.

Validate configuration without opening a socket:

```powershell
$env:PYTHONPATH = "services/core-api/src"
python -m research_observatory_core.main --check
```

Configuration uses the `RO_CORE_` prefix (`PROFILE`, `BIND_HOST`, `BIND_PORT`,
and `LOG_LEVEL`). The current release accepts only the `local` profile and never
includes raw configuration, credentials, research text, or document content in
diagnostic records.

`packages/contracts/core-api/openapi.json`, its generated TypeScript client, and
`core-runtime.schema.json` are the portable generated and hand-authored
contracts. Regenerate or check them with `tools/core_api_contract.py`. The API contains application
behavior only; `design/ui-reference` remains a governed experience reference
and is not served or embedded by this process.

## Windows sidecar package

`packaging/sidecar-build.json` fixes the W0-W5 release package to a
Python 3.14.6, PyInstaller 6.21.0 `onedir` build named with Tauri's Windows x64
target triple. The artifact is self-contained: a system Python installation is
not required. Build it from the frozen development environment with:

```powershell
.venv\Scripts\python.exe tools/core_sidecar_build.py --repo .
```

The build emits only ignored files under `artifacts/tmp`, including an exact
SHA-256 inventory and a frozen-process configuration check. The committed
artifact schema and packaging test fail if a runtime file is absent or changed.
Tauri process supervision is introduced by `CAP-01.S03.T03`; installer signing
and clean-VM release qualification remain owned by the approved `CAP-01.S05`
slice.

Under supervision, the desktop starts the executable with `--supervised`. Core
first consumes exactly `auth <64 lowercase hexadecimal bytes>\n` from inherited
stdin while the process is still suspended. The desktop generates this 256-bit
credential with the operating-system CSPRNG for every launch and never places it
in arguments, environment variables, files, the renderer, logs, or the handshake.
Core retains only its SHA-256 digest. It then binds an OS-assigned IPv4
numeric-loopback port, emits one strict JSON handshake on stdout, and accepts
exactly `shutdown\n` on inherited stdin for graceful
lifespan cleanup. Closing the control pipe also requests shutdown, while the
Windows supervisor's Job Object remains the final process-tree containment
boundary. The desktop creates Core suspended, attaches the Job Object before any
Core code can run, and then resumes it; immediate helper descendants cannot escape
the application's graceful, forced, or host-exit cleanup.

Every HTTP request must arrive from a numeric loopback peer, carry the exact
`127.0.0.1:<assigned-port>` Host authority, omit Origin, and present the current
credential as a single Bearer value. Proxy forwarding is disabled. Missing,
stale, duplicate, malformed, cross-origin, non-loopback, and authority-confused
requests fail closed with fixed secret-safe codes. Rotation occurs on every
start or retry, and the native credential buffer is zeroed when its supervised
process is dropped.

Every accepted request also receives one canonical trace ID. Versioned failures
use RFC 9457 problem details and omit internal exceptions, paths, credentials,
and research content. Runtime operations expose strict status projections,
identity-based pagination, explicit cancellation, and bounded monotonic SSE
replay. No operation-create route or scholarly workflow is implemented here;
CAP-03 supplies durable operation ownership behind this contract.

At slice and release qualification, benchmark the real packaged process with:

```powershell
.venv\Scripts\python.exe tools\core_sidecar_performance_check.py --repo . --report artifacts/tmp/core-sidecar-performance.json
```

Before any process starts, the gate verifies the complete package report and
644-file artifact inventory against the governed build contract and the exact
artifact identity approved by the baseline. It benchmarks a private copy whose
complete tree is protected by a Windows read-only ACL and no-delete path handles
for the entire measurement, then reverified around every lifecycle. A renamed
executable, changed dependency, transient create/use/delete injection, or mid-run
substitution is nonqualifying.

The governed Windows x64 baseline retains all seven cold-process samples after
one filesystem warmup, exact hardware identity, measurement-tool commit and
bytes, package report/manifest/evidence hashes, median strict readiness, p95
shutdown, and p95 idle root-process working set. Every metric must remain within
both its absolute slice budget and a 20 percent regression boundary. Baseline
bytes are independently hash-pinned. Qualification additionally requires a clean
tracked Git state and proves the currently executing tool path/SHA and current
HEAD in the report. `--measure-only` is deliberately nonqualifying, and every
failed invocation replaces a prior report with an explicit `ok: false` result so
stale PASS evidence cannot survive.
