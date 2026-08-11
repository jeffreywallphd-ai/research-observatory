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
