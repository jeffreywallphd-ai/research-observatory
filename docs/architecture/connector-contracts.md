# Scholarly-source connector contracts

CAP-04.S02.T01 implements the portable seam in ADR-0027. It does not install a
provider, authorize a network call or publish canonical scholarly records.

## Public shape and identity

`packages/contracts/connectors/` contains Draft2020-12 request, result-page and
capability schemas, emitted by the existing `tools/core_api_contract.py --write`
generator. `--check` and the contract fixtures reject drift. The matching owned
Pydantic values live in `connectors/contracts.py`; `ports/connectors.py` exposes
mockable adapter/cancellation interfaces with no SDK, path, database or secret
handle. There is no new API route, framework, dependency or migration.

The five discriminated scientific operations are fielded search, identifier
lookup, directed citations/references, positive/negative-seed recommendations and
OA resolution. Provider capabilities and configuration state remain explicit;
unsupported operations do not silently fall back. A capability is descriptive,
not a current egress or credential authorization.

Invocation and observation IDs use existing canonical UUIDv7 conventions and
must differ. Project identity retains the existing UUIDv4/UUIDv7 bridge. The
project-scoped scientific digest is SHA-256 over ASCII JSON with sorted keys and
compact separators: schema version, project, provider/adapter/API version, exact
query/filter/sort/projection and page size. It excludes invocation, cursor and
execution policy, which remain in the protected request record. This is not a
new identity store or a general canonicalization algorithm. Changing a policy
still requires current authorization; equal query identity grants nothing.
Cache observations instead use `page_sha256()`: the same canonical serialization
of `scientificRequestSha256` and the full current `cursor` (or null). It prevents
a cached first page from satisfying a later-page request. Neither identity grants
cache access or relaxes current retention/rights checks.

Cursors bind that digest, provider, project, page index and bounded opaque value.
`assert_resumable(now)` checks the exact binding and expiry using the caller's
current canonical UTC instant. Next-page results require an advancing, different,
unexpired cursor. A cursor is provisional until Core atomically accepts the page
observations and permitted response references; partial/failed pages cannot
advance a completed-page checkpoint. Replay creates a new observation and may
return different remote results.

## Results, rights and privacy

Every page retains its original request/provider, observation time, explicit
retrieval time or absence, response-retention state, cache/rate observations,
page-level license/terms/access observations, warnings and classified errors.
The page observations remain present even when records are empty, and do not
substitute for each record's separate source observations.
A complete empty page is distinct from partial,
failed, denied, cancelled or not-configured. Partial/failed results explicitly
say retry-current or unavailable, never exhausted. Actual returned assertions
carry raw identifiers, namespaced fields, retrieval time and source-reported
license/terms/access observations. These are not verified claims, canonical
Work/Version identities, acquisition permission or any other action grant.

Unknown and not-reported source rights stay distinct and restrictive. Raw-body
retention is retained, permitted-fields-only or unavailable. A retained object
uses the existing plaintext SHA-256 object identity for the sanitized scientific
response, not credential-bearing wire bytes. Source terms/current action rights
must permit the actual retention; the model only represents the observation.

The schema deliberately accepts no arbitrary wire URL/header or authentication/
contact configuration. Queries, identifiers, cursors, values and body references
remain protected project data. Model reprs suppress content fields and ordinary
validation messages hide input values. `model_dump`, JSON serialization and
Pydantic structured error details are **not** redacted diagnostics and must not
be logged or sent to the renderer as failure messages. `ConnectorFailure` carries
only a validated bounded error category, not a provider exception message.

These shapes do not detect a secret echoed inside arbitrary scientific text.
The Core broker must omit/redact its injected authentication/contact values in
URLs, bodies, errors, headers and unknown extensions before constructing replay
records. No connector/renderer/job/environment/CLI receives a reusable secret.
Current project/intent/rights/egress checks remain mandatory before dispatch,
cache access, retry, resume and publication. Contract tests are not proof of
those later real network/storage boundaries.

## Bounds and verification

Policies represent ADR-0027 ceilings: one in-flight request/provider, at least
1000 ms between requests, at most three attempts, at most 30 s per request and 10 MiB
decompressed response. Retry-After is bounded (initial ceiling 300 s); authentication,
permission and policy denial are terminal. Cache-hit observations bind the
scientific page request (including cursor) and declared freshness. There is no cross-project cache or
scheduler implementation in this task. Provider-specific stricter limits remain
mandatory in adapters.

Requests are limited to 256 KiB serialized data, result snapshots to 10 MiB and
capabilities to 16 KiB; pages have at most 1000 records and the requested page size.
Individual query, cursor, record, field, warning and error collections have
explicit bounds. The transport must enforce limits before parsing external data.
The published JSON Schemas enforce structural shape. Cross-field identity,
outcome, time, continuation, retry, cache and retention invariants are additionally
enforced by the Core models; consuming a schema alone is not dispatch validation.

Synthetic fixtures and focused tests prove schema generation, immutable ownership,
mockable composition and these local semantic boundaries. Existing import suites
and performance evidence are unaffected. HTTP/broker enforcement, provider
fixtures, durable cache/page acceptance, restart and real source-slice/platform
qualification remain CAP-04.S02.T02/T03 and subsequent slice/Wave verification.
