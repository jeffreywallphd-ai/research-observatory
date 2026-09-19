# Local reference parsing — CAP-04.S01.T01

`ingestion.reference_imports.ImportSession` consumes an already-authorized binary
stream using bounded `read(size)` calls. It never opens a path, seeks, logs source
content, executes instructions, calls a provider, assigns rights or changes the
canonical corpus. The caller owns stream lifetime and must retain the immutable,
protected source object and its rights/access/provenance metadata. This composes
with the existing verified object-stream port without exposing decrypted paths.

## Handoff and completion

Supply a basename, expected plaintext SHA-256, explicit format and encoding.
Iterate `records()` once; yielded records are **provisional**. Only normal iterator
exhaustion with `complete == True` proves EOF, expected source digest, and a
complete error report. That flag does not mean all records are valid or that any
import was committed. Abandonment, cancellation, timeout, source/count limits,
read failure and hash mismatch cannot become completion. Restart from the same
immutable object; do not resume from an unauthenticated offset.

`ImportRecord.to_document()` follows
[`import-record.schema.json`](../../packages/contracts/ingestion/import-record.schema.json).
Offsets are zero-based half-open bytes; physical lines and record ordinals are
one-based, including CSV headers and BibTeX directives. Blank separators do not
create records. Raw Base64 bytes are exact. Over-limit records retain their
source digest, byte/line range and raw-record digest, but omit inline bytes;
retrieve those bytes only through the authorized source object. All IR and raw
values are protected research data, not safe default telemetry or public exports.

Ordered fields preserve repetition and unknown fields. RIS values retain decoded
continuation text; CSV values are decoded cell text, without spreadsheet evaluation;
BibTeX and CSL fields retain value-expression text. Exact lexical syntax always
remains in raw record bytes. Syntax failures may lack extracted fields but retain
the original bytes/range and coded diagnostics. No malformed data is silently
converted to a valid record. Unrecoverable framing quarantines the remaining
range instead of guessing new record boundaries.

Each retained field has bounded warning codes at its exact ordered position:
duplicate fields, rejected normalization candidates, unresolved macros and
formula-like cells remain attributable even when no candidate is emitted.
Record warnings retain the summary plus framing/source-wide diagnostics. Warnings
never replace raw values or confer human mapping acceptance.

Record keys are SHA-256 of compact ASCII JSON:
`["import-record-key/1", ordinal, byteStart, byteEnd, lineStart, lineEnd, rawSha256]`.
They are independent of read chunking and filenames and are **not** canonical
work, source-record or revision IDs. ADR-0013/0024 continue to own durable identity.
ADR-0027's import identity additionally binds source/parser/mapping/selected-record
and effective-draft decision inputs in CAP-04.S01.T03.

Common scalar title/author/year/container candidates collapse whitespace; DOI
candidates remove recognized wrappers, trim outer whitespace and case-fold without
stripping internal punctuation. This is syntax normalization, not identifier
existence, source verification or scholarly confidence. Every candidate names its
source field index and uses the existing `{"kind":"unknown"}` confidence shape.
`mappingDecision` is null. CAP-04.S01.T02 owns mapping/selection/error-report UI;
CAP-04.S01.T03 owns authorized atomic commits and durable manifests.

## Formats, limits and failure behavior

- RIS: TY/ER framing, repeated tags, unknown tags and indented continuation lines.
  A new TY safely ends a malformed missing-ER record; valid later records survive.
- BibTeX: brace/parenthesis entries, nested/escaped values, quoted/numeric literals
  and `#` concatenation. Local `@string` definitions are bounded text substitutions;
  definitions take effect only after full record validation. Unresolved
  redefinitions shadow older values and propagate warnings, not stale or invented
  values. Preamble/comment content
  is retained and inert; no TeX command, extension, filesystem read or subprocess.
- CSL JSON: a UTF-8 item array, not an arbitrary repository wrapper. Top-level
  repeated fields and unknown nested values remain auditable. Syntax parsing is
  not a claim of complete CSL semantic validation or canonical reconciliation.
- DOI lists: one identifier per nonblank line. Invalid lines remain error records;
  there is no network lookup or inferred DOI existence.
- CSV: explicit comma/tab/semicolon delimiter, one header row, standard quoting,
  multiline cells and duplicate columns retained by index. A bad header cannot
  turn the next data row into a replacement header. Formula-like cells are flagged
  and retained as data. T02 previews must render inert text; spreadsheet-oriented
  exports must prefix active cells under ADR-0027, not rely on CSV quoting.

Defaults: 256 MiB source, 1 MiB inline record, 64 KiB field, 200k records, 256 fields,
64 nesting levels, 256 local macros, 120-second deadline. Positive bounded overrides
are explicit trusted-caller settings (no unlimited values); record ceilings extend
to 16 MiB, source to 2 GiB, depth to 128. Encoding is strict UTF-8 (optional BOM) or
explicit Windows-1252; CSL requires UTF-8. UTF-16/32 is unsupported and must be
converted deliberately without overwriting the original. Mixed/invalid encoding
creates visible errors, never replacement-character data loss.

Source/cancellation failures have content-free codes. Record warnings also contain
codes only, while original content stays in the protected IR. No default log sink
or telemetry is added. Source/durable-job integration and cross-process cancellation
remain slice integration obligations, not claims established by these pure parsers.

## Preview groundwork (CAP-04.S01.T02 in progress)

`import_drafts` keeps immutable mapping revisions, action-specific rights and
per-record decisions separate from parser observations. Duplicate CSV column
names use occurrence-qualified selectors; conflicting singleton candidates remain
explicit. Corrections do not overwrite raw fields. The versioned streaming
effective-draft hash includes source/project, parser, mapping profile/revision,
ordered decisions, rights and options; transient preview identity is excluded.
A hash is not evidence of complete parsing, current permission or commit authority.

`source_chunks` uses the existing encrypted object port to retain ordered source
pieces of at most 128 KiB (256 MiB total). Whole-source SHA-256 remains the import
identity; chunk hashes are storage details. Every bounded read checks current
inspect permission, verifies one encrypted piece and closes its object reader
before returning bytes. This preserves the existing object reader's rights barrier
without holding its SQLite writer reservation across parser yields. No new cipher,
plaintext staging, filesystem capability or import-only database is introduced.
The `reference-import` purpose is local-read only; unknown rights do not authorize
intake or inspection, and store/inspect permission grants no other action.

The protected version-11 repository now binds contiguous chunk membership and
total length atomically, protects shared references from deletion, and retains
bounded typed record metadata by durable job attempt. Raw binary bytes remain
only in encrypted chunk objects, not JSON. A parser-complete attempt binds one
observed workflow receipt with source-manifest dependency authority; pages remain
unavailable until the exact successful attempt accepts that receipt. Ordinary
expired-attempt recovery can reparse without exposing earlier provisional rows;
security cancellation closes access. Source records are not created by previews.

Draft revisions now use compare-and-swap on the current revision, one accepted
parse attempt and bounded groups of at most 100 decisions. Each decision binds an
actual record and the exact mapping profile. Profiles are immutable project-scoped
identities/revisions; undo cannot redefine an earlier profile. Source values and
researcher corrections remain distinct. Remapping recomputes source suggestions
while preserving explicit corrections, exclusions and per-record rights. A new
mapping conflict is visible and excluded until resolved, never silently imported.

Undo appends a revision restoring a selected earlier state. Sparse decision reads
follow that restored history; later edits cannot resurrect the abandoned branch.
Restoration cannot implicitly broaden any current default or per-record action
permission, including records outside the visible page. Such undo requests fail
atomically. A rights change requires its own explicit authorization; undo cannot
supply it.
Digests stream the complete ordered effective draft, not just visible rows. Current
rights and cancellation still constrain historical reads, including raw-record
access. Per-record inspect denial blocks affected pages rather than exposing raw
values through another route. Reports stream bounded, freshly authorized pages
covering parser warnings, mapping warnings and exclusions without source content,
names, hashes or paths. Content-bearing export remains a separately authorized
action. Draft editing never creates canonical SourceRecords.

These boundaries are not yet a complete production wizard. Native/service project
and lock authorization, worker composition, duplicate-candidate projection and UI
wiring remain CAP-04.S01.T02 work. Internal repository page limits are not the
native bridge limit: the service must project/paginate responses below 1 MiB.

## Verification and technical basis

Focused service and contract tests cover all formats, deterministic replay,
malformed recovery, corruption, explicit encoding, limits and a real binary file.
The generated-stream benchmark consumes 100k RIS, BibTeX and CSV records twice
without a batch list, measuring elapsed time and peak traced memory against a
16 MiB buffering-regression ceiling. Runs distinguish first/immediate-repeat from
OS cold-cache qualification; timing is a baseline, not a promised UI latency.

Primary format references consulted: [CSL input schema](https://github.com/citation-style-language/schema/blob/master/schemas/input/csl-data.json),
[BibTeX format](https://www.bibtex.org/Format/),
[BibTeX implementation specification](https://tug.ctan.org/info/knuth-pdf/bibtex/bibtex.pdf),
and [DOI handbook](https://www.doi.org/doi-handbook/html/).
All checked-in test metadata is explicitly synthetic and is not research evidence.
