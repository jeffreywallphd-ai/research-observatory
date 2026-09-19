---
id: ADR-0027
title: Keep scholarly source replay separate from private authentication
status: Proposed
date: 2026-09-13
deciders: []
linked_tasks:
  - CAP-04.S02.T01
  - CAP-04.S02.T02
  - CAP-04.S02.T03
  - CAP-04.S03.T01
  - CAP-04.S04.T02
decision_scope: W2 scholarly source configuration, replay, identity assertions, rights and credential delivery; no authorization for live queries or later providers.
affected_paths:
  - services/core-api/src/research_observatory_core/ingestion/**
  - services/core-api/src/research_observatory_core/connectors/**
  - packages/contracts/ingestion/**
  - packages/contracts/rights/**
supersedes: []
superseded_by: null
---

# ADR-0027: Keep scholarly source replay separate from private authentication

## Context

W2 imports and four source adapters feed one inspectable corpus. ADR-0013/0024
own canonical identity and provenance; ADR-0017 owns local secret leases;
ADR-0019 owns privacy and egress. A source API being public does not authorize
sending a private research query or redistributing every returned field.

The old CAP-04.S02 forecast required exact request URLs. That would retain
authentication/contact query parameters for some providers. Preserve the
scientific observation, not a reusable credential-bearing wire request.

Primary sources reviewed 2026-09-13: [OpenAlex authentication](https://help.openalex.org/api/authentication/),
[Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/),
[Unpaywall v2](https://unpaywall.org/api/v2) and
[Semantic Scholar API](https://www.semanticscholar.org/product/api).
OpenAlex distinguishes keyless and keyed access; Crossref has public access;
Unpaywall requires contact configuration; Semantic Scholar availability and
limits depend on the endpoint. These facts do not establish live availability.

## Candidates

1. Keep exact wire requests in ordinary provenance. Easy byte replay, but leaks
   private authentication/contact information and couples replay to old secrets.
2. Separate a protected scientific request/response record from broker-injected
   authentication. Adds an explicit replay contract, preserves observation
   lineage and supports current credentials without distributing old values.
3. Deliver only local imports/DOI lookup. Simpler networking, but removes planned
   discovery coverage; not selected merely to shorten implementation.

## Decision

Recommend candidate 2 with all four planned adapters. This remains **Proposed**
until reviewed and accepted within the complete W2 packet.

- Local imports work offline with no account. Each provider advertises actual
  capabilities and configuration requirements. Missing configuration, quota,
  denied policy, timeout and partial results are distinct from an empty result.
- Core authorizes the scientific operation before dispatch. A narrow broker
  validates provider, endpoint, method, parameter schema, destination and budget;
  only it obtains an ADR-0017 lease and injects authentication/contact values.
  No renderer, connector, job argument, environment or command line receives
  reusable secrets. Prefer supported authentication headers over URL keys.
- The protected replay record contains source/adapter version, operation,
  scientific query/filter/sort, cursor, time, response status and the protected
  response-object reference. Authentication/contact parameters are omitted,
  including values echoed in response URLs, headers or errors. Unknown response
  fields are not an excuse to retain those values. Record that redaction occurred.
  Arbitrary raw headers and request URLs are not replay authority.
- Scientific terms may themselves be private: keep query and permitted response
  payloads in the encrypted project, never default logs/support bundles/tracked
  fixtures. Replay uses current policy/configuration and creates a new observation;
  it does not claim identical remote results or reproduce authentication bytes.
- Pagination checkpoints bind the request identity and provider cursor; commit
  source observations idempotently. Partial page failures cannot silently become
  complete coverage. Bounded provider-specific retry respects Retry-After and
  cancellation; do not retry authentication denials indefinitely.
- Provider IDs and field values remain source assertions. Exact normalized IDs
  produce deterministic matches; disagreement and probabilistic candidates remain
  inspectable. Human merge/split and version/update decisions retain old identities,
  decisions and dependent-staleness events rather than overwriting source records.
- Local import IR separates raw source value/location, normalized candidate,
  warnings and human mapping decision. The manifest binds original file digest,
  parser/mapping versions and selected records; use that scientific input identity
  for idempotent commits. Changed input creates a new manifest, not an in-place
  replay. CSV cells render as inert text and exported cells neutralize formulas;
  parsing never invokes BibTeX commands or arbitrary extensions.
- Capture discovery route, retrieval time, terms/license/access observations and
  action-specific permissions. Unknown rights remain restrictive. Metadata access
  alone does not permit full-text acquisition, model use or export. Resolve
  permissions again at the action, not only at import.

Credentials/contacts are optional private local settings, never task fixtures.
No account provisioning, live query, purchase or external upload is authorized
by selecting this design. Exact provider admission schemas and redaction fixtures
are implementation artifacts under this boundary, not additional human gates.

## Consequences

W2 retains source coverage and a useful offline path. Replay explains the
scientific request but is deliberately not a credential-bearing network capture.
Provider-specific redaction and current terms need maintenance.

Extend existing repository/provenance and encrypted object contracts; do not add
an import-only database. New versioned schemas migrate additively with verified
encrypted rollback. Failed imports leave canonical state unchanged; disabling an
adapter preserves observations and local documents. The portable contracts do
not qualify non-Windows adapters before their scheduled Wave.

## Verification

Criterion-linked fixtures cover all four adapters, missing configuration,
429/Retry-After, denied egress, invalid/expired cursor, interrupted page commit,
restart, changed remote result, malformed response and source disagreement.
Use synthetic credential/contact sentinels in request, error and echoed-response
locations; assert absence in project provenance, connector IPC, logs, arguments,
exports and tracked fixtures. Check current rights through alternate API paths.
Live provider checks, if required for qualification, need explicitly configured
authority and must remain distinct from deterministic replay tests.

## Task links

- `CAP-04.S02.T01`
- `CAP-04.S02.T02`
- `CAP-04.S02.T03`
- `CAP-04.S03.T01`
- `CAP-04.S04.T02`
