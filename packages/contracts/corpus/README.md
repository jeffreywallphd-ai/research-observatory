# Portable corpus membership contract

`corpus-membership.schema.json` is the versioned wire contract for a CorpusItem
revision, immutable discovery path, and membership decision in
`CAP-04.S04.T01`. Its membership states and transitions are bound to the frozen
`domain-lifecycle.v1.json` corpus-item profile. Pending review, duplicate
relationship, and availability are independent fields, not new lifecycle
states. It does not grant source, Work, actor, protocol, rights, or process
negotiation authority; Core must re-read those authorities in its protected
writer transaction.

Every discovery edge points from a source observation to a corpus item, records
canonical UTC millisecond time, and names its predecessor item revision. The
initial edge has a null predecessor; an appended edge names the exact current
item revision. `contextId` names the root import/query or citing Work identity,
while `sourceRevisionId` names the observed source revision. Core must verify
those types and relationships against protected records.

Run `node packages/contracts/corpus/generate.mjs` after changing the schema or
validator templates. `--check` denies stale generated TypeScript/Python output.
Both validators bind the raw schema SHA-256 and return content-free error codes.
The generated Python `encode_*` functions accept exact
`model_dump(mode="json", by_alias=True)` dictionaries, add the contract envelope,
validate, and return independent JSON-compatible documents. A `None` result
must deny the write. The caller must still prove project, source, Work, actor,
decision predecessor, and evidence authority transactionally.

The `fixtures/` directory contains valid and denied wire examples for both
language tests. The core v1 contract and process compatibility advertisements
remain unchanged; this package export does not activate a v2 process handshake.
