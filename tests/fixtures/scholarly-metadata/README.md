# Synthetic local-import fixtures

These fictional metadata examples are software tests, not scholarly sources.
No identifier or author here represents a verified research observation.
They supplement, without changing, the existing CC0 scholarly-corpus fixtures.
These new fixture files are likewise dedicated to CC0-1.0 by their contributors.

`records.csl.json` is a genuine CSL item array (not the older fixture wrapper).
`records.csv` retains quoted multiline fields; `records.doi` tests DOI wrappers
and meaningful punctuation. Deliberately malformed/boundary bytes are constructed
inline in parser tests so their expected errors remain beside each assertion.

`connector-page.v1.json` is a fabricated provider-neutral page for contract tests,
not a captured provider response or evidence of live availability. It contains
explicit missing rights observations and no credentials, contacts or real query.

`schema-v15-authority.json` and `schema-v15-populated.json` were captured from
the approved adapter at commit `0738c2543db85af8189bd0948393698b04662de6`
before WorkVersion edits. They contain literal schema and synthetic rows for a
candidate set, split/merge history, exact-source impacts, a partially processed
102-consumer review impact and a pending continuation after graph growth. The
loader pins their SHA-256 values and restores their literal bytes/rows; current
DDL is not used to reconstruct the predecessor. Their synthetic resolver tests
migration compatibility, not actual source-owner or Windows-principal authority.

`work-versions.v1.json` is a synthetic portable Core projection containing a
preferred version of record followed by a human-adjudicated retraction relation.
The old preferred exact revision and source evidence remain, while standing is
`requires-review`. It is a software handoff example, not a scholarly observation.
Its two source-address record keys use distinct, obvious synthetic placeholders;
the enclosing context digest is recomputed. It is not byte-exact parser output.
Real repository/client checks and immutable predecessor fixtures retain actual
parser keys. The two original keys were independently reproduced as content
digests after credential scanning flagged them; no scanner or hook was weakened.
