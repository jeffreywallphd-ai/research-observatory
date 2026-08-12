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
operating system. The later supervision task owns the bounded startup handshake.

Validate configuration without opening a socket:

```powershell
$env:PYTHONPATH = "services/core-api/src"
python -m research_observatory_core.main --check
```

Configuration uses the `RO_CORE_` prefix (`PROFILE`, `BIND_HOST`, `BIND_PORT`,
and `LOG_LEVEL`). The current release accepts only the `local` profile and never
includes raw configuration, credentials, research text, or document content in
diagnostic records.

`packages/contracts/core-api/openapi.json` and `core-runtime.schema.json` are the
portable generated and hand-authored contracts. The API contains application
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
binds an OS-assigned numeric-loopback port, emits one strict JSON handshake on
stdout, and accepts exactly `shutdown\n` on inherited stdin for graceful
lifespan cleanup. Closing the control pipe also requests shutdown, while the
Windows supervisor's Job Object remains the final process-tree containment
boundary. The desktop creates Core suspended, attaches the Job Object before any
Core code can run, and then resumes it; immediate helper descendants cannot escape
the application's graceful, forced, or host-exit cleanup.
