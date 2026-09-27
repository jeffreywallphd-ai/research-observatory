# Scholarly reconciliation and duplicate review

CAP-04.S03.T01 exposes bounded local reconciliation under ADR-0013/0024/0025/0027.
The source of a fact remains separate from its inferred Work association. Generated
JSON schemas and Core OpenAPI/TypeScript come from `tools/core_api_contract.py`.
Consumers use the public API and these portable values, never SQLite internals.

## Durable candidate batches

CAP-04.S03.T02 adds `batches/prepare`, `batches/schedule`, `batches/status`,
`batches/cancel` and `candidates` under `/projects/reconciliation`. Prepare binds
the complete accepted import/connector inventory, current accepted Intent and
policy to a Core-issued request ID. Schedule reuses that immutable request;
it never adopts records accepted after the snapshot. Retry a failed enqueue with
the same request ID. Failed or cancelled jobs use the existing explicit Task
Center continuation; an ordinary restart preserves the request and a changed
security session cancels old authority. No source lookup uses the network.

The batch atomically appends exact associations, cached features, candidate-set
and pair evidence, provenance and accepted workflow output. A cancelled or failed
publication contributes none of those partial facts. Task Center refresh/cancel
remains available during the writer. Every close/shutdown signals all local
workers before waiting for their drains; failed drain preserves the open project.

`candidates` takes an immutable set revision plus bounded `after` and `limit`
(1–100). Scores, weights, missing/disputed features, source fingerprints and
algorithm/configuration versions are historical evidence, not probabilities or
automatic merge authority. `membershipState` separately reports changes since
publication; `dependencyState` reports existing or pending review impacts. Current
source rights are rechecked even for historical pages. Zero candidates means only
that the bounded frozen retrieval generated no pairs, not proof of no duplicates.

Human review uses `review/context`, `review/preview` and `review/commit`. It binds
complete current Work/source membership, all affected aliases, explicit survivor
and partitions, an evidence digest, retained conflicts, rationale and the exact
preview digest. Merge/split/assignment appends immutable decisions and new Work
revisions; original assertions and receipts remain. Dependency impact work is
durable and does not imply downstream recalculation is already complete.

## Public handoff

1. Commit an accepted import draft through the existing durable workflow. Use its
   manifest revision, preview context, included member ordinal and record key as
   an `import-member` SourceAddress. A source-record ID alone is insufficient.
2. For a completed retained connector page, POST root, previewId and zero-based
   ordinal to `/projects/reconciliation/connector-address`. Core resolves the exact
   accepted output revision and returns a `connector-record` SourceAddress.
3. POST root, UUIDv7 commandId and source to `/projects/reconciliation/exact`.
   `new-work` and `exact-linked` carry canonical Work/revision IDs with inferred
   knowledge. `review-required` carries flags/candidates and no Work mutation.
4. POST root and assertionRevisionId to `/projects/reconciliation/inspect`. The
   result preserves raw assertions, normalization/version, source selectors,
   competing field observations and selection reasons. Conflicts remain disputed.
   `result` is the original immutable reconciliation receipt. `canonicalWork`
   binds the current `canonicalFields` projection to its Work ID and exact
   canonical revision ID in one read snapshot, even when inspecting an older
   assertion. It is null for an unresolved assertion with no Work association.

The native authenticated Core session and current open project are mandatory.
Core resolves source values and rights itself; client-supplied grants are rejected.
Every contributing source must still permit inspect, store, derive and index.
Current accepted Intent and project privacy are rechecked even for replay and
inspection. Local retained-source operations perform no network request and do
not reuse an old network confirmation. Changed command reuse conflicts; an exact
authorized retry returns its original immutable result after restart. Reconciliation
does not grant export, training or remote-model rights.

## Normalization version scholarly-identifiers/1.0.0

| Scheme | Canonical rule and retained distinctions |
|---|---|
| DOI | Numeric registrant components after `10.`, ASCII-only case folding, optional DOI label or exact doi.org/dx.doi.org HTTP resolver. Trim literal boundary whitespace as required by ADR-0027, then decode a resolver path once. Preserve Unicode, punctuation, internal spaces and explicitly percent-encoded suffix spaces. No nine-digit prefix limit, Unicode case folding or punctuation stripping. |
| PMID | Positive ASCII decimal, optional PMID label or exact PubMed resolver. Leading zeros converge; PMC IDs do not. |
| arXiv | Validate historical archive/date/sequence or modern date/sequence syntax. Preserve explicit versions; unversioned and v1 are distinct. Abs/pdf wrappers and historical classification adornments normalize. |
| ISBN | Check ISBN-10/13 checksum; convert ISBN-10 to its 978 ISBN-13 form. Preserve manifestation scope; raw import ISBN without subject authority is a container assertion. |
| ORCID | Check MOD11-2 and preserve leading zeros; canonical HTTPS form. Person identity cannot merge Works. |
| OpenAlex | Typed case-insensitive W/A/I/S/P/F ID, consistent optional namespace. Only W has Work scope. |
| Semantic Scholar | Separate 40-hex paper ID and positive decimal corpus ID namespaces. Provider grouping is an observation, not verified truth. |
| URL | HTTP(S) ASCII URI only, lowercase scheme/host, remove default port, decode unreserved escapes, uppercase other escapes. Preserve path case, query order, empty query/fragment delimiters and fragments. Dot-segment paths conservatively remain distinct. Locations never provide exact Work keys. |
| Title | NFKC, case folding and whitespace collapse produce a heuristic fingerprint, never an exact identity key. |

Validity describes this bounded syntax profile, never registry existence or
verification. Unknown schemes remain unsupported. Inputs retain their exact
observed representation. JSON strings and single BibTeX literals are decoded from
raw fields; unresolved BibTeX macros/concatenations remain flagged for review.

Unique compatible exact keys can link only subject-scoped Works/versions. All
identifiers on every candidate contributor participate in conflict detection;
a bridge between two Works is review-required. Explicit disputed, invalid or
reassigned assertions block linking. A matching provider key with incompatible
scholarly IDs is flagged as suspected reassignment. This does not claim to detect
unreported reassignment without contrary evidence. Accepted corrections retain
the original inactive key and are the only field-precedence authority; no arbitrary
provider ranking resolves conflicting values.

## Persistence, limits and recovery

Candidate inspection exposes the authenticated frozen and current accepted-source
inventory fingerprints. `inventoryState: changed` means the historical set does
not represent the current accepted inventory; generate a new batch to cover it.
Historical scores remain unchanged. Membership and dependency warnings describe
their separate current-state comparisons.

Schema 14 appends source assertions, Work revisions, exact-key lookup links and
command receipts to existing canonical record authority. One transaction includes
provenance, outbox and material source/Intent/privacy/normalizer dependencies.
Source rows and earlier revisions are unchanged. Generic audit labels contain no
title or identifier. Source inspection remains protected research content.
The dedicated assertion document has one versioned strict schema, database-enforced
identity bindings and a size limit; arbitrary payload blobs remain forbidden.

Source resolution occurs under the project lifecycle lock before the writer
transaction because protected reads also record access audit facts. The writer
rechecks the complete candidate set against resolved source snapshots. A concurrent
new source produces a conflict with no partial publication; retry the same command.
No source fetch occurs while holding the database writer.

Requests are limited to 32 KiB; identifiers to 64 KiB UTF-8; a source to 128
identifiers, 256 fields and 1 MiB serialized data; matching to 256 candidate Works
and 256 source contributors per Work; the complete action to 512 distinct sources
and 16 MiB of source snapshots; inspection to 4 MiB. Limits fail explicitly,
never silently truncate evidence. Large acquisitions continue through durable jobs.

The migration validates exact predecessor fingerprints and retained data, creates
and verifies a backup, then advances schema and history atomically. Interrupted
publication or migration rolls back; restart/retry rechecks current authority.
The fixture tests distinguish plaintext development storage, actual SQLCipher
with fixture keys, and the production Windows DPAPI/SQLCipher composition.

## Primary normalization sources

Consulted 2026-09-27:

- [DOI Foundation Handbook 2025](https://www.doi.org/doi-handbook/DOIHandbook_2025.pdf), namespace syntax and limited case insensitivity.
- [NCBI PubMed help](https://pubmed.ncbi.nlm.nih.gov/help/), PMID identity.
- [arXiv identifier format](https://info.arxiv.org/help/arxiv_identifier.html) and [service handling](https://info.arxiv.org/help/arxiv_identifier_for_services.html).
- [International ISBN Agency manual](https://www.isbn-international.org/sites/default/files/ISBN%20Manual%202012%20-corr.pdf) and [Library of Congress transition guidance](https://www.loc.gov/catdir/cpso/13digit.html).
- [ORCID identifier structure](https://support.orcid.org/hc/en-us/articles/360006897674-Structure-of-the-ORCID-Identifier).
- [OpenAlex entity lookup](https://help.openalex.org/api/get-single-entities/) and [Work attributes](https://help.openalex.org/data/works/attributes/).
- [Semantic Scholar API](https://api.semanticscholar.org/api-docs/snippets).
- [RFC 3986](https://www.rfc-editor.org/rfc/rfc3986.html), URI normalization and comparison.
