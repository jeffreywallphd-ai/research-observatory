# Scholarly-source connector contracts

CAP-04.S02.T01 implements the portable seam in ADR-0027. It does not install a
provider, authorize a network call or publish canonical scholarly records.

## Public shape and identity

`packages/contracts/connectors/` contains Draft2020-12 request, result-page and
capability schemas, emitted by the existing `tools/core_api_contract.py --write`
generator. `--check` and the contract fixtures reject drift. The matching owned
Pydantic values live in `connectors/contracts.py`; `ports/connectors.py` exposes
mockable adapter/cancellation interfaces with no SDK, path, database or secret
handle. The portable seam itself introduced no API route, framework, dependency
or migration. The provider runtime below builds on that seam.

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
and performance evidence are unaffected by that contract-only delivery.
Integrated source-slice/platform qualification remains separate.

## OpenAlex and Crossref runtime — CAP-04.S02.T02

Core compiles only supported field/filter/sort/projection semantics into fixed
HTTPS destinations. Unknown operations deny rather than broaden a query. The
broker owns the single retry/rate budget, public-address DNS binding, TLS,
bounded JSON parsing and broker-only credential leases. Error bodies, wire URLs,
authentication/contact fields and dependency debug headers are not replay data.
Sanitized scientific responses and source assertions remain protected project
objects; they do not create canonical Works or grant export/model/share rights.

Authenticated Core endpoints provide capabilities, exact-request previews,
confirmations, job status and cancellation. An accepted Intent destination,
current privacy policy, rights and exact researcher confirmation are separate
requirements. Confirmation is session-local and expires; reopening a project
does not silently reauthorize pending requests. Client-supplied request data or
source-package trust cannot mint consent. Optional Intent egress fields preserve
old clients' omission behavior and default to local-only.

Each confirmed page is an existing durable workflow job. Under the current
project/consent guard, one canonical writer validates the attempt capability,
lease, cancellation and predecessor, then accepts page/raw references, cursor,
output artifacts, provenance and workflow success together. Pre-commit failure
rolls back all canonical acceptance; encrypted orphan objects may remain. Lost
post-commit acknowledgement cannot convert accepted success to cancellation.
Receipt reads retain project-before-object lock order. Import and connector
workers share one conservative document-lane resource policy.

Caches are project/page scoped and recheck current authority. Local cache hits
do not renew remote-validation time; only a new response or valid conditional
revalidation does. Retained-body redaction provenance survives hits, 304s and
restart. Failed/partial pages do not advance checkpoints. Fresh invocations can
resume from the exact completed predecessor with new current confirmation.

Tests use synthetic provider responses, actual local protected persistence and
an isolated real TLS transport boundary. These are not live-provider, native UI
or production-package claims; remaining adapters and slice/Wave qualification
retain their own obligations.

## OA and graph adapters — CAP-04.S02.T03

Unpaywall resolves one DOI with API v2 and preserves every reported OA location,
host, license and version. Semantic Scholar API v1 supports one-paper lookup,
directed citations/references and positive/negative-seed recommendations. Graph
assertions retain the seed/direction and raw edge; null edges, mismatched IDs,
duplicate papers or non-advancing offsets are failures, not complete coverage.
Recommendation requests use a bounded JSON POST to the one fixed HTTPS endpoint;
other provider operations retain GET. No returned OA URL is fetched here.

The existing Windows profile vault holds one strict, versioned `connector-token`
connection record per provider. Complete compare-and-swap replacement makes key
and contact updates atomic; explicit null clears a value. Missing optional
configuration allows keyless access; missing Unpaywall contact is not-configured.
Corrupt, inaccessible or lost-root configuration is unavailable, never keyless
fallback. Profile values stay separate from project data and scientific replay.

Authenticated native-only configuration routes accept bounded replacements and
return only presence, availability and opaque CAS versions. They are excluded
from public OpenAPI and the renderer's generic bridge. Saving is a local action,
not consent or a connection test. The broker checks current operation authority
before configuration access/cache/replay and re-leases values on every retry.
Unpaywall contact uses `email`; Semantic Scholar credentials use `x-api-key`.
Injected values and encoded echoes are removed before source publication.

Source Manager keeps settings entry in an owned native form. The renderer sees
only saved/cancelled/unavailable/conflict/rejected/unconfirmed outcomes. Cancel
before dispatch changes nothing; after possible transmission, lost replies or
stale context remain unconfirmed. Settings are not prefilled, and preservation
requires the current CAS version. Reopening checks current presence; it does not
infer which writer committed an earlier unconfirmed save.

The Research Intent scope form exposes the existing local-only / approved
content / approved-redacted policy through impact, draft and explicit acceptance.
Existing destinations remain intact unless removed. A source Test is a bounded
DOI lookup, with separate local preview and explicit send; it grants no authority.
Fixed provider policy links open in the system browser without research data.

Read-only `/projects/connectors/recent` and `/inspect` project routes recover
original exact-preview jobs and accepted source observations. The recent window
is limited to 20 original source jobs within 100 workflows; retry continuations
remain in Task Center. An exact preview ID also resolves older or unconfirmed
submissions. Inspection checks retained inspect rights without renewing network
consent, and projects one record at a time with title, OA-location and discovery
fields. Missing observations, missing jobs, partial/failed coverage and complete
empty pages remain distinct. Confirmation tokens and session authority never
enter the inspection projection. No migration or parallel history store is used.

Development checks cover synthetic mappings, isolated real DPAPI, native/Core
permission and configuration paths, protected-project restart and browser
interactions. Final native/task/slice qualification remains pending; these checks
are not live-provider or production-package evidence.

## Signed plugin SDK contract — CAP-04.S05.T01

`packages/contracts/connectors/connector-plugin-*.schema.json` publishes the
portable manifest, project-grant, invocation-request and invocation-plan shapes.
The authorization-provenance schema records a successful pre-dispatch decision.
`connectors/plugin_manifest.py` owns their Core validation. This is a separate
SDK from the first-party connector request/capability/page contract above:
ADR-0028 permits only lookup, search, references, citations,
open-access-locations and repository-metadata for plugins. The first-party
recommendations and OA-resolution operations do not become plugin authority.

A plugin manifest declares its stable plugin and source identities, semantic
plugin/SDK versions and required SDK features, fixed entry point, complete file
hashes, permitted operations and exact HTTPS destination templates. It also
declares broker-only authentication scopes, data classes, source-terms status,
rate/resource ceilings and requested permissions. These declarations are
untrusted inputs and do not grant project, network, credential or rights access.
The signed source ID must be `plugin.` followed by the plugin ID; plugin IDs
are at most 121 characters so that qualified source IDs fit the 128-character
portable field. A plugin cannot claim a built-in provider ID. Core registration
in T02 must still reject
plugin-ID/publisher collisions before enablement.
Missing terms remain `not-reported`; a terms reference does not permit retention,
full-text acquisition, model use, export or sharing. Current Core policy and
action-specific rights still decide each operation.

Core verifies a detached Ed25519 signature over the **exact manifest bytes**
against an explicitly configured local publisher key, validates the strict
manifest and verifies the complete declared file set before producing a verified
package identity. Its package digest is SHA-256 over the domain prefix
`research-observatory-connector-package-v1` plus a zero byte, followed by each
file in sorted path order as a four-byte big-endian UTF-8 path length, path,
eight-byte big-endian content length and exact content bytes. The manifest
digest and signature digest remain separate. Unknown publishers, changed signed
bytes, undeclared files, changed file bytes, unsafe paths, incompatible major
versions and unknown required features deny. No bundled key can trust itself.

An authenticated active Core-owned project grant must bind the exact plugin
ID/version, publisher, manifest and package digests, declared permissions and
destinations, project and revision. A same-version package update therefore
requires a new enable decision; increased permissions require renewed consent.
The authorization function only returns an attributable plan containing those
identities, source, operation, invocation, Core-owned scientific-request digest
and routing-request digest when the current grant and requested
operation/destination match. The latter digest binds the routing fields and
scientific digest; it is not a digest of wire bytes or replay content. A typed
`authorized` provenance envelope recomputes authorization from the verified
package, Core-owned grant and request, with no claim
that an operation ran or yielded a result. It does not execute plugin code,
obtain a secret, authorize a scientific query or persist consent. CAP-04.S05.T02
owns durable enablement, dispatch through an LPAC worker and narrow broker,
current policy/rights rechecks, denial/audit and restart qualification. A caller
must never accept a plugin-supplied grant or plan as Core authority.

## Plugin network broker — CAP-04.S05.T02

Implementation status: this is a tested, unconnected Core component while
`CAP-04.S05.T02` is blocked on the packaged LPAC/no-plaintext-write boundary.
No production caller currently binds it to a workflow job, worker IPC, current
grant, or durable audit. The required runtime composition described below is
not yet implemented or qualified.
Live composition must also recheck current publisher trust before each broker
call, or cancel every affected worker immediately on trust revocation; a grant
check alone would leave an already-running worker with stale publisher authority.

`connectors/plugin_broker.py` accepts only a Core-owned plan and the strict
`PluginBrokerCall` operation parameters. Its generated JSON Schema is the
cross-process call shape; it has no arbitrary URL, HTTP method, header, body,
filesystem path or secret field. The schema fixes field types and bounds; the
Core model additionally enforces operation-specific combinations. An IPC reader
must enforce ADR-0028 framing/job binding before validating this call and must
not treat a worker-supplied plan as authority.

Before each request, Core loads the authoritative invocation request by its
job-bound identity and re-derives authorization from that request, the verified
package and the **current** project grant. It compares the entire plan, then
invokes the required current project/intent/rights policy
callback with the concrete scientific parameters. It repeats those checks after
rate waiting and before any optional Core-side scoped secret lease. No callback,
stale grant, unauthorized scope or changed operation denies. Broker instances
must share one Core-owned `PluginBrokerRates` instance so the
one-request-per-second and single-in-flight budget cannot be reset by creating
another broker. Before a secret lease, a separate Core-owned scope binding must
match the destination's exact HTTPS scheme, host and port; merely signing two
destinations does not make a credential valid at both.

Construction also requires a synchronous Core-bound denial-audit callback that durably
records a content-free reason code against the authoritative job. If that audit
fails or returns an awaitable, the broker surfaces `audit-unavailable` and does not turn the call into
success. Frame-level denials occur before this broker and require audit in the
LPAC runtime wrapper.

The broker expands only signed HTTPS scheme/host/port/path templates and derives
fixed query keys from the operation. It makes GET requests only, never follows
redirects, checks every DNS answer for public routability, and dials the checked
numeric address while retaining the signed hostname as the TLS identity. The
wire target is capped after percent encoding, before transport construction.
The request has normal TLS validation, no environment proxy, and a 30-second
deadline. Responses are limited to 10 MiB on wire and after decompression;
error bodies and wire metadata are never returned. A scoped credential stays
in Core and is injected as an Authorization header only for the exact request;
echoes in successful JSON are sanitized before the bounded body is returned.
The broker response is not an accepted source record or a rights decision.

`repository-metadata` is restricted further to the generated
`connector-plugin-repository-metadata.schema.json` public assertion: exact
requested repository ID, bounded display name and optional bounded description.
Unknown fields and a changed repository ID fail. It carries no arbitrary link,
download instruction, credential or source-rights grant. The worker and Core
publication path still need their separate output/provenance validation.

## Local plugin trust and project grants — CAP-04.S05.T02

Implementation status: the persistence and authorization components below are
partial task groundwork. No production native/UI caller authenticates the
researcher's trust and project-permission actions or dispatches a plugin through
the LPAC worker. These components do not authorize plugin execution on their own.

`connectors/plugin_trust.py` stores local publisher-key decisions in the existing
profile-scoped `SIGNING_TRUST` credential port. An authenticated human action
binds the exact key ID and public-key fingerprint. Immutable, chained events and
a compare-and-swap head retain trust, revoke and explicit post-revocation key
rotation history. An unknown, revoked, corrupt, unavailable or interrupted trust
record fails closed. Package-provided key material cannot add local trust.
Removing local trust stops authorization for that publisher across every project
without rewriting historical project grants.

`plugin_grant_repository.py` stores exact, project-scoped enable/revoke decisions
and content-free denials in protected SQLite v21, bound to immutable provenance
events. A grant pins package and manifest digests, version, publisher, permissions,
destinations, the reviewed operations/data classes/credential scopes, and the
local trust key fingerprint and revision. The same plugin ID cannot switch publisher within a
project's grant history; a revoked or superseded action replay cannot reactivate
historical permission. Re-signing an identical package after key rotation, or
retrusting a revoked key, requires a new project decision. `PluginGrantService.enable` verifies signed bytes against
current local trust before persisting an exact researcher confirmation.
`PluginGrantService.current_authorization` repeats signature/file verification,
active trust and current grant lookup on every dispatch before returning a Core
plan. Its request must come from the existing authoritative workflow job; the
broker separately rechecks current project/intent/rights policy. The native/UI
caller owns actor authentication and the two distinct visible decisions: local
publisher trust and exact per-project permission.
