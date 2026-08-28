# Core API contracts

`core-runtime.schema.json` defines the strict framework-neutral health and
readiness response variants, including runtime identity, state, version, and
capabilities. `openapi.json` and `generated.ts` are generated from the FastAPI
application and committed so service, desktop, and client compilation detect API
drift before runtime. The generated source records the exact OpenAPI SHA-256 and
generator version, exposes a deployment-neutral transport port, strictly decodes
untrusted responses, and implements compatibility, problem-detail, pagination,
cancellation, and bounded SSE replay calls.

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

Core API client version `1.0.0` is accepted only when the service identity and
schema are exact, its declared API major matches, and the client falls within the
inclusive-minimum/exclusive-maximum compatibility range. Failures use RFC 9457
problem details with stable `RO-CORE-*` codes, an opaque 128-bit trace ID, and
safe remediation. Operation status is identity-paged; cancellation is explicit;
progress frames are monotonic SSE events replayed after an accepted sequence.
The generated client also exposes strict Research Intent workspace,
change-impact-preview, and draft-save calls. It rejects extra response fields,
malformed UUIDv7 revision identities, mismatched current/history summaries,
launchable draft projections, inconsistent impact tokens, invalid scope groups,
and unbounded idempotency identities before values cross the renderer boundary.
The draft-save header is mandatory; Core binds it to the exact project, stable
OS-local actor, command, committed revision, provenance fact, and pending outbox
fact so an identical retry can replay across process restart without creating a
second revision.
The current in-memory operation registry is an integration seam only—CAP-03 owns
durable workflow state and creation behavior.
