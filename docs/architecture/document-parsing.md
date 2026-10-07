# Protected staged document parsing

CAP-05.S02.T01 defines values and ports under accepted ADR-0028 and ADR-0029.
Native adapters and isolated Docling execution remain S02.T02/T03; persistent
revisions and human acceptance remain S03. This contract introduces no database
migration, HTTP endpoint, UI change, accepted-head write or parser dependency.

`parsing/contracts.py` owns strict, frozen version-1.0 values. Original object
digest/length/format, project, attachment, document/revision, candidate, source
assertion and Work/Version revisions travel together. Local imports carry local
provenance; remote acquisitions additionally bind the exact location and retained
receipt digest. Producer identity records version, configuration and asset
digests, separately from durable workflow job and attempt identities.

The IR retains ordered flat nodes with earlier parents, raw/normalized text
projections, locations, reference entries and identifier observations, citation
candidate sets, table indices/spans/cell text, figures and protected preview
receipts. Unknown elements keep their type and raw text. Quality dimensions and
warnings remain separate; missing confidence is unknown, and a reported numeric
value is no probability of correctness or acceptance. Reported table grids reject
overlap; explicit ambiguous grids retain competing geometry for review.
Reference strings, citation markers and cell text use their identified node's
projection and a contained span of its decoded text. Missing node text or a
contradictory projection/range is refused. Containment uses the exact normalized
range and raw contributors, including reordered and noncontiguous contributors;
it does not impose a new monotone-offset rule on legitimate Unicode mappings.

`ro-text-nfc-1` pins Unicode 16.0.0 NFC plus CRLF/CR to LF. It preserves case,
whitespace, ligatures and hyphenation. Text offsets are half-open Unicode code
points, including supplementary scalars as one position. Raw text is decoded
source text, not original byte offsets; original bytes remain in the encrypted
source object. Compact identity runs and per-scalar transformed mappings retain
all raw contributors. Composition can have noncontiguous contributors; expansion
can map multiple normalized scalars to one raw scalar. Reordered marks can map
backwards. Every span is checked against the exact mapping, never an approximation
over an unstated normalization. Page coordinates use finite points in the
unrotated original page frame with top-left origin; page rotation is explicit.

The Core-owned closed registry admits native structured/text, pinned Docling
2.126.0 CPU and the approved PDF inspection fallback. Runtime availability and
source eligibility are trusted Core observations. Selection prefers eligible
JATS/TEI/XML/HTML, then PDF, DOCX and text; stable source/parser IDs break ties.
An explicit alternative-copy selection or proven same-object/source assertion is
required; sharing a Work, Version or content digest alone grants no equivalence.
Denied, unavailable and unproven candidates stay in the record. PDF fallback is
a separate inspection-only attempt after an exact Docling failure, timeout or
memory limit. Cancellation and source/rights denial cannot trigger fallback.

The additive object-store parse facet resolves the exact committed attachment
and current retained provenance, then evaluates inspect and derive together in
the existing protected writer transaction. Existing inspection-only consumers
retain their behavior. `LocalProtectedParseSource` authenticates and reads in
bounded chunks under the caller's production native-session guard, releases the
writer before parsing, and hands the adapter private read-only memory without a
path, key or write port. It repeats current source/rights authorization under the
same guard before delivery. Current actor, accepted Intent and privacy checks
come from the existing rights repository. Test-owned SQLCipher/encrypted-object
tests exercise changed rights and real detach/close/reopen denial; their parser
double is explicitly synthetic and does not qualify an isolated worker.

`stage_parse` binds the request/selection fingerprint to the parent-authenticated
producer, job, attempt and artifact receipts. The receipt must be constructed by
the trusted launcher independently of worker JSON. Strict UTF-8 JSON rejects
duplicate fields, nonfinite values, invalid graphs and output over 64 MiB; copied
model instances are revalidated. Errors contain codes, with no retained private
decoder/validation exception. Cancellation is monotonic and fails closed on a
broken callback. Failure, cancellation and denied delivery expose no usable IR
and cannot change canonical document facts. Staged output is never acceptance.

The [portable schemas](../../packages/contracts/documents/README.md) describe
wire shape, with an explicit semantic-rule inventory. New incompatible versions
must follow the existing compatibility/ADR route. No implicit offset migration
or format repair is selected. Isolated execution, resource enforcement, offline
assets, raw-output persistence and slice-wide recovery remain subsequent work.
