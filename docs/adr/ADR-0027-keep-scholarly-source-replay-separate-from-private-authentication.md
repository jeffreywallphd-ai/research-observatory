---
id: ADR-0027
title: Keep scholarly source replay separate from private authentication
status: Accepted
date: 2026-09-13
deciders:
  - human:repository-owner; W2 design/architecture approval recorded 2026-09-19
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

Select candidate 2 with all four planned adapters. The owner accepted this exact
decision in [W2 design/architecture approval](../../artifacts/evidence/W2.design-architecture-owner-approval-01.md).
Complete W2 packet approval remains required before implementation.

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

### Binding ingestion and corpus details

- Import identity is SHA-256 of versioned canonical serialization of source-object
  digest, parser version, mapping-profile revision, ordered selected-record keys
  and the immutable effective-draft decision digest. That digest binds accepted
  per-record mapped values/corrections, inclusion/link decisions, rights/default
  decisions and import options; exclude credentials, paths and transient UI state. A
  record key binds its original ordinal/location and raw-record digest; it is not
  a work ID. A project-scoped unique import-identity constraint and one transaction
  make an identical effective draft replay its existing manifest after current
  authorization checks. A changed accepted value or decision creates a new attempt
  and manifest revision, reusing existing source-record identities rather than
  duplicating records or overwriting prior decisions. A reused request ID with a
  different effective-draft digest is a conflict, not a replay. Test identical-draft
  retry and same-source/profile/selection with changed corrections or rights.
  Preserve raw fields, byte/record location, normalized fields and
  per-field warnings in versioned ImportIR; mapping profiles are immutable project
  revisions. Never use an absolute source path as identity or exported metadata.
- CSV is data, not code. No evaluated formulas, macros or BibTeX commands.
  Spreadsheet-oriented export prefixes potentially active cells (`=`, `+`, `-`,
  `@`, leading control whitespace) as inert text while retaining original values
  in protected provenance; normal CSV quoting alone is not neutralization.
- Use the existing HTTPX transport behind one Core-owned broker with normal TLS
  verification. Separate per-provider admission buckets, initially one in-flight
  request and at most one request/second until a stricter advertised limit applies.
  At most three attempts with bounded jitter/Retry-After; authentication/permission
  denial is terminal. Cap each metadata response at 10 MiB and request at 30 seconds;
  validate decompressed limits too. Persist resumable cursors, not an unbounded
  automatic search. No shared cross-project result cache is selected.
- Retain protected source snapshots only where source terms/rights permit; otherwise
  retain the permitted fields, digest, retrieval/terms observation and an explicit
  unavailable replay-body state. Do not treat redaction as permission to redistribute.
  Deterministic tests use synthetic/licensed fixtures. A separate opt-in live smoke
  at the source slice checkpoint and Wave exit uses a public known item, at most
  five requests/provider, configured local authority and no private research query.
  Missing optional provider configuration must pass the not-configured path, not
  be reported as live success. No mandatory account purchase/provisioning is selected.
- Work identifies the scholarly contribution; WorkVersion identifies a preprint,
  accepted manuscript, version of record, correction or retraction-linked edition.
  SourceRecord remains an immutable provider assertion. Explicit version links
  outrank title similarity. Conflicting/reassigned identifiers cannot auto-merge.
  DOI normalization removes recognized DOI wrappers, trims boundary whitespace and
  case-folds the identifier; do not strip meaningful internal punctuation. Preserve
  raw identifiers. Provider IDs remain namespaced; arXiv version suffixes identify
  versions, not interchangeable work assertions. Normalization is versioned.
- Exact unique valid identifiers may auto-link, never probabilistic title/author
  similarity. Deterministic candidate ranking uses normalized title tokens, author,
  year and venue features, with transparent component scores. Before tuning, freeze
  a rights-cleared labeled fixture set and candidate retrieval targets of precision
  >=0.90 and recall >=0.95; report pair and cluster errors separately. Scores are not
  probabilities. Human merge/split appends decisions and alias/membership revisions,
  checks expected predecessors and marks affected dependents; undo is a new decision,
  never deletion or identity reuse. No invented gold labels or auto-adjudication.
- Rights dimensions are store, inspect, index, derive, model-use, quote, export
  and share, each permitted/denied/unknown with provenance and conditions. Unknown
  denies that action; permission in one dimension does not grant another. Corpus
  snapshots bind an immutable membership revision plus the exact source/work/version
  assertions and governing protocol. Discovery edges carry root import/query, source,
  direction, time and predecessor IDs; overlap reports count explicit distinct sets
  at one snapshot, not inferred unseen coverage. Rights changes re-evaluate affected
  actions without erasing the historical basis or silently running them again.

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
