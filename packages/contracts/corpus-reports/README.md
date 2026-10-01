# Portable corpus report contract

`corpus-report.schema.json` freezes the `CAP-04.S04.T03` snapshot, member and
drill-page shapes. `CorpusReportSnapshot`, `CorpusReportMember`, and
`CorpusReportDrillPage` are versioned documents. The Core models live in
`research_observatory_core.corpus_report_model`; `generated.ts` exposes matching
TypeScript types and a strict decoder. The schema carries structural wire
rules; Core still resolves source, project, Intent, protocol, rights, and actor
authority in the protected writer/read transactions.

The denominator is **one current canonical CorpusItem revision per item in the
project at the snapshot transaction**. It includes every membership state.
Later inclusion decisions, new discovery paths, and Work changes do not rewrite
the snapshot. `memberCount` and `membersSha256` bind the ordered immutable member
rows, and each drill row names its exact item, Work revision, path, source and
context revision witnesses. A page uses at most 100 members; a cursor is scoped
to the project, snapshot, exact filter and position and must be rejected if it
cannot be validated after retry or restart. An empty report has `memberCount=0`,
the SHA-256 of the empty member stream, and an empty `all` drill page.
The member stream hashes each member's `model_dump(mode="json", by_alias=True)`
as JSON with sorted keys, ASCII escaping, compact separators, and one trailing
newline, in ascending `itemId` order. The per-row digest uses the same bytes.
The exact filter kinds are `all`, `membership`, `duplicate-linked`,
`unattributed`, `source`, `route`, `source-overlap`, `route-overlap`, and
`coverage`. `coverage` with `state=known` and `value=null` selects all known
values; a nonnull value selects one exact observed value. Other selector
fields must be null. Every displayed count therefore has an exact drill.

`sourceKey` is `import:<exact import manifest revision ID>` or
`connector:<retained provider key>` when that root is established by the
protected source assertion and discovery path. Paths without an attested root
have `sourceKey=null`; they contribute to their route and to
`unattributedItemCount`, not to an invented source. That count is the number of
**distinct member items with at least one unattributed path**, including an
item that also has an attributed path. The `unattributed` drill filter uses
that same predicate. `discoveryPathCount` counts exact retained path edges,
while `unattributedDiscoveryPathCount` counts edges with `sourceKey=null`.
Source path counts plus unattributed path counts reconcile to the total; route
path counts also reconcile to the total. These are **discovery-path counts**,
not counts of unique source records, database result coverage, or unseen work.
Each source and route counts a canonical item once in `itemCount`, even if it
has several paths from that source or route. A contribution's
`discoveryPathCount` retains that path multiplicity. Pair-overlap `itemCount`
counts items in both distinct source-root or route sets, once per pair. A
pair's `discoveryPathPairCount` sums the cross-product of its two path sets
*within each item*: two import paths from A and one connector path from B give
one overlapping item and two path pairs. This measures observed convergence
without treating duplicate paths as additional canonical items. Contributor
and overlap lists are complete; publication fails with an explicit
resource-limit error instead of silently truncating them.

Each path also carries a snapshot-time source-boundary projection.
`metadataAssertionStatus=retained` and `reportInspectStatus=allowed` require
an exact `rightsPolicyRevisionId`; `rightsExpiresAt` is nullable canonical UTC
time. A path without an external assertion is `no-external-assertion` /
`unassessed`, with no policy revision or expiry. `sourceCopyAvailability` is
`unknown` until an exact per-source copy witness is retained. The frozen
projection does not grant future inspection: Core must recheck the same
current policy revision and expiry before serving the saved report.

Every member classifies `identifier`, `year`, `venue`, `language`, `discipline`,
`oa`, and `full-text` exactly once. `known` requires a nonempty value and an
exact retained, rights-authorized source assertion witness. `not-reported`
means the inspected retained source did not report a value; `unknown` means a
determinate value is unsupported, ambiguous, or absent without a defensible
not-reported assertion; `unavailable` means relevant evidence cannot be
inspected or retained. Missing values stay null and are never counted as zero.
Permission to inspect metadata, a CorpusItem `availability=available` value,
or a provider name is **not** an OA or full-text witness. Known OA/full-text
values are only explicit `yes`/`no` observations. These states disclose limits
without suggesting whole-database coverage or unseen records.

`coverage` counts the four epistemic states across the same denominator for
each dimension. `valueDistributions` show at most 50 exact known-value groups
per dimension, ordered by count then value; `otherKnownCount` and `truncated`
make any overflow explicit. The member drill remains exact, including values
outside the displayed group list. `membershipCounts` always includes all four
states, including zero counts. No cluster, citation-neighborhood, inferred
discipline, or automatically acquired full-text claim is part of this contract.

The pure accumulator accepts members in strictly ascending item-ID order and
hashes canonical JSON lines without retaining the member rows. It caps reports
at 100,000 items, 100 million path edges, 49.95 billion path pairs, 512
distinct source roots, 32 source roots per item and 20,000 observed source
pairs. These integer bounds are below JavaScript's safe-integer limit.
Exceeding a cap fails before publication; Core must roll
back the entire snapshot. These are implementation resource limits, not
statements about the scholarly corpus.

Regenerate/check the portable files with:

```powershell
.venv\Scripts\python.exe tools/generate_corpus_report_schema.py
node packages/contracts/corpus-reports/generate.mjs
.venv\Scripts\python.exe tools/generate_corpus_report_schema.py --check
node packages/contracts/corpus-reports/generate.mjs --check
```

The fixtures include valid snapshot/member/page examples, a same-item two-path
source-overlap example, and denied examples for a false denominator and a
known value without its witness. They use synthetic identities and
observations only.
