# Local search query contract

CAP-06.S01.T01 implements the approved CAP-06-D01/D06 query boundary under
Accepted ADR-0057. Core owns parsing, immutable ASTs, bounded import and portable
schemas. The package `research_observatory_core.search` imports no UI, server,
database or worker runtime. It can be used by an authenticated API adapter or
another local Core client. This task does not add an HTTP endpoint or a standalone
headless launcher; CAP-06.S01.T02/T03 own protected indexing and search delivery.

`parse_query(text)` returns a `QueryDocument`. `document.to_json()` serializes
private query content intentionally; `load_query_document(bytes_or_text)`
strictly imports and revalidates it. These functions are the semantic boundary.
Frozen, slotted `QueryNode` and `QueryDocument` constructors validate their inputs;
serialization validates again, including objects forged through Python's low-level
mutation facilities. Representations omit content. No query is logged, written to
storage, executed as SQL or granted access merely by parsing it.

## Syntax and meaning

```ebnf
query       = disjunction ;
disjunction = conjunction, { "OR", conjunction } ;
conjunction = unary, { [ "AND" ], unary } ;
unary       = "NOT", unary | "(", disjunction, ")" | leaf ;
leaf        = literal | phrase | text-field, ":", (literal | phrase)
            | "year", (":" | "=" | ">" | ">=" | "<" | "<="), year ;
```

Uppercase `NOT`, `AND`, `OR` are operators, with that precedence from highest to
lowest. Adjacency means conjunction. Parentheses group expressions. Same-kind
AND/OR branches flatten in order; operands are neither sorted nor deduplicated.
NOT remains explicit, including double NOT. Lowercase operator words are literal
data; quote uppercase operator words to search for them. Fields are case-sensitive:

| Field | Intended searchable projection |
| --- | --- |
| `title` | Canonical title |
| `abstract` | Lawfully available abstract |
| `full-text` | Lawfully available revision-bound full text |
| `authors` | Author names |
| `venue` | Venue metadata |
| `identifiers` | Identifier values |
| `year` | Integer publication year, 1 through 9999 |
| `tags` | Project tags |
| `decisions` | Human screening decision labels |

Unfielded literals/phrases select the default textual search scope; they do not
implicitly search numeric year metadata. A field binds only the following leaf:
`title:alpha beta` means `title:alpha AND beta`. Field groups such as
`title:(alpha OR beta)` and nested field overrides are unsupported. Pure-negative
`NOT alpha`, including `alpha OR NOT beta`, means set complement relative to the
same **currently authorized, filtered corpus snapshot** as the other operands.
Later compilation must implement that meaning explicitly; it cannot substitute
an FTS operator with different pure-negative semantics or a wider rights universe.

A literal is a nonempty run excluding whitespace, control characters and
`: ( ) " \ * ? ~ ^ < > = [ ] { }`. Other punctuation, including DOI slashes,
periods, apostrophes and hyphens, remains data. A phrase is nonempty text between
double quotes; it permits `\"` and `\\` escapes only. Control characters,
including embedded tabs/newlines and DEL, are rejected inside literals/phrases.
Unicode whitespace outside phrases separates tokens. Unpaired Unicode surrogates
are rejected; astral characters and combining marks are preserved. Colon-rich
identifiers and reserved punctuation can be quoted:

```text
title:"evidence synthesis" AND year>=2020
authors:山田 OR abstract:é
identifiers:"doi:10.1234/example(1)"
NOT (tags:excluded OR decisions:excluded)
"AND" OR full-text:"a quoted \"word\""
```

Wildcards, fuzzy/proximity suffixes, boosts, bracket ranges and backslash escapes
outside phrases are explicitly unsupported. Year comparison accepts ASCII decimal
digits only; `year:2020` canonically becomes `year=2020`. This language never
accepts raw FTS or SQL syntax as executable instructions.

## Normalization and analyzer provenance

The snapshot retains `originalQuery` exactly, plus deterministic `normalizedQuery`,
semantic AST, schema version `1.0`, grammar version `ro-search-query-1` and analyzer
identity `ro-unicode61-diacritics2-1`. Normalization adds explicit conjunctions,
canonical spacing, necessary parentheses and phrase escapes. It preserves literal
case, Unicode codepoints, punctuation and operand order. Parsing normalized text
must reproduce the same AST and normalized text. Import independently reparses
the original and rejects substitutions in any snapshot field.

The portable analyzer profile declares SQLite FTS5 `unicode61` with
`remove_diacritics 2`, no stemming and unchanged source normalization. The identity
binds this configuration for later index/run provenance; installed tokenizer
behavior and protected persistence require T02 proof. A literal is exact query
terminology without wildcard/fuzzy expansion. It does **not** promise byte-,
case- or diacritic-exact retrieval: the analyzer can map different source spellings
to the same tokens. A phrase requests adjacent analyzed tokens in order. Neither
query normalization nor tokenization may rewrite canonical source text, document
revisions or ADR-0029 NFC anchor identities. Analyzer changes require a new
profile identity and derivative generation under ADR-0057.

A literal that produces no analyzer tokens denotes an empty match set; it must
never become an unrestricted query. A punctuation-rich literal that produces
multiple tokens requests those adjacent tokens in order. T02 must lower each
literal/phrase through the declared analyzer and parameters without executing its
contents as query syntax. These meanings also apply inside NOT/combinations.

## Hard input and diagnostic limits

Original and normalized queries each allow at most 8192 Unicode codepoints.
Normalization overflow rejects the original, ensuring every accepted normalized
query remains parseable. There are at most 16 nested syntactic groups/unary NOTs,
16 AST levels (root counts as one), 256 expanded AST node occurrences, and 32
operands per AND/OR branch. Shared child aliases count each occurrence. Cycles,
mutable children, subclasses and malformed/unknown node types are rejected.

Portable UTF-8 JSON is capped at 262144 bytes before decoding, with a string-aware
prewalk limiting nesting to 36 containers and total containers to 516 before the
recursive decoder runs. AST depth/node budgets apply again during rehydration.
Duplicate members, nonfinite constants, unknown fields/kinds/versions, invalid
UTF-8, surrogates, coercive values and Boolean/float/string years are rejected.
The default Python JSON integer-digit limit is also fail-closed. Portable JSON
Schema describes structural shape; it cannot prove cross-field parse binding or
all runtime budgets. All untrusted imports must use the Core loader after any
structural validation.

`QueryError.diagnostic` exposes only a stable code and numeric location. Syntax
offsets are half-open codepoint positions in the **original** query; EOF is a
zero-width span. Line and column are one-based. CRLF is one newline; lone CR and
LF also start new lines. Astral characters count once, combining marks count
individually. Structural/wire errors use the neutral span `[0,0)` at line/column
1. Exception messages, representations and decoder chaining omit query content.
This is not a claim to erase local memory or caller-owned source/traceback locals.

## Scope and verification

There is no durable mutation, migration or operational audit event in this pure
contract task. Query/run audit lineage, protected snapshots, authorization,
ranking, SQL lowering, index recovery, API search and governed UI conformance
remain in their owning tasks. Existing connector `SearchQuery` remains its
separate external-source DTO. Existing OpenAPI operations and generated client
artifacts remain available.

`tests/search/test_query_grammar.py` covers grammar, roundtrip, boundaries, locations,
strict wire import, immutable snapshots and content-free error surfaces.
`tests/search/test_query_contracts.py` exercises actual Core-to-JSON/schema
roundtrips, forged graphs and an isolated process without UI/server imports.

## Protected indexing Core commands

CAP-06.S01.T02 supplies `CoreLexicalIndexService` in `lexical_index_repository`. Its
`rebuild`, `begin_rebuild`/`run_build`, `resume`, `synchronize` and `retire`
commands use injected Native session authority, current canonical sources and
purpose-scoped derivative keys. They have no renderer dependency. A future
headless client uses these same Core boundaries; no AI-mode authority or launcher
is introduced. CAP-06.S01.T03 owns HTTP adapters, ranking, snippets and result UI.

Canonical schema 29 adds append-only source-change, generation, event and
selection records, plus fenced expiring writer leases. Migration starts from
the literal schema 28 predecessor, verifies a protected backup and preserves
earlier cells, objects and migration history. Source outbox publication and
change sequencing share the canonical transaction. Controller-only index
events do not feed their own consumer.

The generated `indexes/lexical-<generation UUID>.sqlite3` file is a separate
SQLCipher derivative. A revision-bound text mirror and external-content FTS5
table share that encrypted database. Its keys bind project, generation, purpose,
canonical-key version and package lifecycle. Files and ancestors retain identity
and no-reparse holds through close; WAL and shared-memory names stay guarded,
temporary tables remain in memory, and close checkpoints before owned cleanup.
Derivative bytes remain excluded from portable backup/export by the existing
package file-class policy.

Metadata uses the current canonical field selection and exact source-copy
`inspect` and `index` grants for `local-search`/`local-project`. Full text uses
the current accepted normalized revision and authenticated original copy. One
complete normalized projection is one FTS row, retaining its projection ID and
half-open codepoint range. Projection IDs are not node IDs: a projection may
have zero, one or several structural associations. This preserves phrases across
node boundaries and discarded punctuation without creating phrases across
separate projections or copies. Search never changes canonical normalization or
anchor identity.

Private commits and canonical acknowledgements are separate transactions.
Shadow rows are unreadable until sealed; promotion rechecks source watermark,
current authority, expiry, cancellation, integrity and expected pointer. An
unacknowledged incremental commit requires complete validation or a fresh
shadow, never blind batch replay. Failed or cancelled work preserves the prior
selected generation. A stale readable corpus requires synchronization before
Boolean results; current rights denial remains effective before physical purge.
All command failures are content-free and leave canonical research authoritative.

Queries load bounded, ordered batches of complete authorized items into memory
tables. All permitted metadata/text rows for an item stay in one batch, so
Boolean evaluation can be united across disjoint item sets without changing
negation or cross-row conjunction. Batch bounds limit the working set; the
100k-metadata/100k-passage qualification frame is not a corpus-import limit.
The internal candidate-ID helper is separate from T03's bounded result delivery.

Retirement recovery is a private Core operation returning no rows or reusable
store. It authenticates the held main-file identity against canonical Retired
metadata before opening SQLCipher, then uses only the exact historical vault
version under repeated current Native/actor/nonselection checks. It can verify
integrity, checkpoint and close, including after canonical-key rotation; it
cannot search, stage, update or promote. Ordinary leases still reject old
canonical-key versions. DELETE eligibility and reader drain precede key
revocation. `IndexCleanupPending` identifies a valid new selection whose obsolete
generation needs a cleanup retry; it does not mark the new generation incomplete.
