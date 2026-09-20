# CAP-04.S01.T03 transport-01 independent disposition

**CHANGES REQUESTED for this bounded public transport increment.**
Reviewer: `w2_document_packet_preflight`.
Candidate: `c75b3e1f0b5ef0635aa3472f7a44f4ed0a8121b7`.
Base: `87de02816a93f0a146ef92efe55a07e1390ebc5b`.
This is not task completion or renderer/native-journey/large-input qualification.

## T03-TRANSPORT-01-F01 — P2: UUID sorting is not durable latest-acceptance order

Location: `services/core-api/src/research_observatory_core/import_commit_repository.py:72`
(`latest_commit_request`; candidate line numbers). The same ordering assumption
appears at line 144 in `latest_manifest`.

Latest saved request discovery orders only by `setting_id DESC`. Core's
`domain_contracts.new_uuid_v7` uses wall-clock milliseconds plus independently
random suffixes, not a monotonic acceptance sequence. A later accepted request
can therefore sort below an earlier one. Discovery then returns the older
request after the renderer loses its local request ID, contrary to the new
durable latest-request recovery boundary. Sorting manifest revision UUIDs has
the same defect for the newly exposed latest-manifest lookup.

Reproduction at the exact candidate with the existing isolated real service
fixture: constrain only the repository's generated setting IDs to two valid
UUIDv7 values from the same millisecond, first lexically higher and then lower;
prepare draft revision 1; append draft revision 2; prepare revision 2; call
`latest_commit_status` and `latest_commit_request`. The requests are distinct,
but discovery returns the first request and stored draft revision 1 while the
actual current draft is 2. The probe exited 0 in 2.297 seconds. Its output was:

```json
{"differentRequests":true,"discoveryReturnedFirst":true,"discoveryReturnedSecond":false,"storedSelectedDraftRevision":1,"actualCurrentDraftRevision":2}
```

Only the request-discovery path was dynamically probed; the manifest lookup's
identical UUID-order assumption was confirmed by source inspection. Reviewed
product/test/contract inputs matched the candidate during the probe; concurrent
renderer edits were outside this snapshot. No real user data was accessed.

Material criterion: request discovery and immutable-manifest navigation must
identify the latest durable accepted operation without relying on renderer
memory or assuming that random identity order is acceptance order.

Smallest closure: order these lookups by actual persisted insertion/acceptance
order in their existing append-only relations, not UUID magnitude. Preserve the
exact request/input/actor and manifest/output authentication checks. Add
out-of-order valid UUID regressions for both lookups, including adapter/service
reopen, and retain absence, preparation-without-execution and replay cases. No
new migration, general ordering framework or human gate is required by this
finding.

## Reviewed coverage and evidence limits

Reviewed the exact API, new repository/service discovery/read helpers, generated
client producer/output, native allowlist, tests and documentation delta. The
routes retain authenticated project actions, strict request models and body
bounds; cancellation binds exact preview/request/job. Manifest access retains
accepted-output and current/historical rights checks, including off-page
revocation. Public members expose bounded metadata and canonical IDs, not bulk
source payloads. Error text correctly avoids claiming that an uncertain reply
proves no publication.

Generated methods capture owned requests before field access or awaiting
transport, validate exact shapes and coherent counts, and bind known preview,
request, job, revision and cursor identities. Scientific reuse intentionally may
refer to another preview's original immutable manifest; the status decoder does
not falsely equate those two preview identities. Native forwarding admits the
new exact routes and bounded field sets, without arbitrary activity or actor
input. No additional material blocker was confirmed in this bounded review.

Owner-reported fresh exact-candidate checks: 26 TypeScript cases, contract
typecheck and `core_api_contract --check` PASS; one native allowlist case PASS
with 5.93-second build and the existing unused Status warning; six API, eight
service and two bounded-review Python cases PASS (16 total) in 27.572 seconds.
The independent review ran only the targeted ordering probe, not those suites.
Earlier missing-route REDs and exploratory setup/import failures remain in the
transport implementation evidence rather than being relabeled as passes.

Previously approved storage/worker internals were not relitigated. Known full
rights-scan paging complexity, publication guard/lease lifetime, renderer,
actual native/Core crossing and large-input qualification remain explicit
later T03 work; this adverse checkpoint does not waive or claim those criteria.
