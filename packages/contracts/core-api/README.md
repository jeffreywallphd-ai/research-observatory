# Core API contracts

`core-runtime.schema.json` defines the strict framework-neutral health and
readiness response variants, including runtime identity, state, version, and
capabilities. `openapi.json` is generated from the FastAPI application and
committed so desktop/client generation can detect API drift before runtime.

These contracts contain no OS paths, socket assignment, credentials, research
content, provider types, or deployment-specific framework objects. Version or
semantic breaking changes require the compatibility and ADR controls declared
in the repository architecture.

`sidecar-artifact.schema.json` is the strict Windows x64 packaging handoff. It
binds the component/version, target triple, pinned Python and PyInstaller
builder, entry point, total size, and every packaged file's relative path,
byte count, and SHA-256 digest. It contains no host paths or research data.

`runtime-handshake.schema.json` is the strict inherited-pipe startup handoff
from the packaged Core process to the desktop supervisor. It binds protocol and
build compatibility, PID, numeric loopback endpoint, a process-local nonce,
capabilities, database compatibility range, and a stable diagnostic code. The
nonce is not exposed to the renderer and remains a public process-binding value,
not an authentication secret. CAP-01.S04 authenticates the local transport with
a separate per-launch 256-bit credential delivered from the native supervisor to
Core over inherited stdin before process resume. That credential is deliberately
absent from every portable contract, handshake, log, report, and renderer API.
