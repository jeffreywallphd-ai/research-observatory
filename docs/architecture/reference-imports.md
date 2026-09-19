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
The public undo command accepts only the expected current revision. Core resolves
the previous effective edit, skipping appended undo events so repeated undo never
becomes an implicit redo. Stale requests fail without replay. Rights comparison
resolves both sparse histories setwise, checks default permissions first, and
evaluates changed decisions only; permission requires both a permitted value and
researcher-confirmed basis. This retains all-action restrictions outside the page
without expanding large correction payloads in application memory.
Digests stream the complete ordered effective draft, not just visible rows. Current
rights and cancellation still constrain historical reads, including raw-record
access. Per-record inspect denial blocks affected pages rather than exposing raw
values through another route. Reports stream bounded, freshly authorized pages
covering parser warnings, mapping warnings and exclusions without source content,
names, hashes or paths. Content-bearing export remains a separately authorized
action. Draft editing never creates canonical SourceRecords.

The service composes real project authority, encrypted objects and a local worker
pump. Its exact job configuration binds source/manifest, parser and limits,
rights, privacy, native recovery epoch and an actual canonical Intent revision.
The existing persisted manifest/domain project-ID bridge is checked explicitly.
A draft Intent is contextual, not accepted or governing; preview does not invent
an intent acceptance gate. Worker definitions deny network/model access and use
unknown record progress. Every bounded activity operation revalidates the open
project; ordinary close drains work before releasing the project session.

The worker only claims and recovers its registered import activity. Shared
admission preserves interactive capacity; no reservation means no claim. A parse
receipt binds actual verified EOF, source-manifest and ordered IR identity, and
only the exact succeeded attempt publishes its preview. Expired ordinary attempts
replay immutable source chunks. Recovery-epoch mismatch receives policy
cancellation before recovery/claim, not a fabricated assertion of an observed
security lock. Native code must supply a durable trusted epoch before this service
is composed into production; the renderer cannot choose one.

The native supervisor arms an atomic, bounded recovery marker after acquiring
the existing application-instance guard. Active means the whole native session,
including ordinary Core stops and no-child intervals. Same-native restart may
retain its owned epoch; a new native process rotates an unresolved active epoch.
Lock admission increments an atomic security latch under the lock-manager mutex,
before its asynchronous immediate-stop callback. Disk publication happens after
termination, never ahead of it. A missing/invalid/replaced marker grants no old
worker authority; it does not invent an application sign-in requirement.

Only terminal native exit may publish an ordinary-restart marker: first fence
protected actions, lock/policy/verification admission and Core starts, drain
launch/process work, and reconcile the security latch. Unverified shutdown stays
active. No further marker publication is admitted after sealing. This is local
session recovery, not rollback resistance against a hostile same-account user.

The inherited, bounded startup control record carries the epoch and per-launch
nonce alongside the launch capability; it is cleared after parsing. Legacy
authentication grants no import-worker context. Runtime composition requires
that context, local actor authority and object keys. Project open attaches the
worker; close and process lifespan drain it before releasing the project session.
One shared local admission ledger reserves one CPU slot and 256 MiB RAM for
interactive use; the serialized import pool reserves one CPU slot, 256 MiB RAM
and 1 GiB disk. These are admission estimates, not OS resource enforcement.

The authenticated review routes use strict, bounded JSON-list DTOs without
relaxing the tuple-based domain models. A 900,000-byte envelope budget leaves
headroom for native HTTP framing. Summary abbreviations are explicit; separate
raw/candidate/effective detail pages retain complete values. CSV mappings select
immutable column indices and resolve repeated headers in Core. Mapping revisions
advance from the project profile high-water mark even after undo. Group edits
preserve untouched values and check their expanded size incrementally before
atomic publication. Stale edits require rereading, never automatic replay against
a newer draft. Diagnostic fragments bind the revision and scanned ordinal;
current rights are checked on every page and completeness is explicit.

Native selected-file groundwork reuses the folder picker's STA, cancellation and
cleanup reservation, now spanning the consuming transfer. A native-only held file
rejects network/device/reparse/offline sources, retains non-deletable ancestors,
denies file write/delete sharing and verifies same-handle identity/length and EOF.
Reads are at most 128 KiB; a seal is returned only after all chunks are accepted
and authority remains current. No plaintext staging or renderer source path.
Source identity begins at the verified open, not an earlier Shell observation.
This follows Windows [file sharing semantics](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew)
and [handle path verification](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getfinalpathnamebyhandlew).
The native intake command now composes these helpers with private authenticated
Core routes. The renderer supplies explicit format/encoding/rights and its selected
project, never the source path or Core session nonce. Every transfer pins the
actual supervisor process, launch and selected-project generation plus an ephemeral
Core/project session. Close/reopen, replacement launches and late project replies
cannot continue an old transfer. Cleanup cancellation may reach only the original
still-running Core/session after a project selection changes.

File/network work and failed-result cleanup run off the window thread and outside
the security-lock mutex. Final publication rechecks lock generation, cancellation,
owner window and project/process authority. Cancellation arriving before worker
admission is retained by exact operation ID; the bounded queue never evicts a
pending cancellation, and flooding it closes intake for that native session.
The private routes are excluded from the renderer API schema/allowlist and retain
existing loopback capability authentication and actual-body limits. A supplied
source seal remains unverified until the worker proves EOF and digest equality.
Helper/protocol checks do not qualify actual native selection or packaging.

The desktop ingestion workspace now composes intake, saved-preview discovery,
status, mapping and grouped draft edits through these ports. Public discovery
rechecks inspection permission and returns at most 25 basename-only items; its
cursor advances over denied items without exposing their metadata. CSV controls
use the same target-name suggestions as the parser, preserving untouched columns
and unsaved edits across record pagination. Raw/candidate/effective fields remain
distinct. Project navigation discards private renderer state and ignores late
responses; cancellation dismissal restores focus and supports Escape.

Diagnostic download now streams private session-bound Core pages into a native-
selected local folder. Every page and final authorization require the same
current draft revision; an intervening edit or rights change invalidates the
download. The content-free CSV validates complete contiguous record coverage,
including multiple diagnostics per record. A held create-new exclusive stage is
flushed and read back before a same-handle, no-overwrite rename. Unpublished
stages are deleted by their owned handle. Shared directory pins reject redirects
and prevent ancestor replacement. No destination path reaches the renderer.

The successful rename is publication: later cancellation cannot remove it or
claim no file was saved. Native lock/project/launch and operation guards cover
only this bounded local publication; Core's prior final authorization remains a
separate point, not a cross-process transaction. Network and verification work
stay outside publication mutexes. Interrupted native-process termination may
leave a content-free hidden partial stage, never a successfully named report.
This follows [Windows handle operations](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-setfileinformationbyhandle)
and [non-replacing rename semantics](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_rename_info).

CSV intake now explicitly selects comma, tab or semicolon in the native request;
other formats reject non-comma choices. One reserved `imports.preview.<id>`
settings row binds project, preview, format, encoding and delimiter at revision
zero, atomically with preview creation. It uses existing immutable protected
settings, not a new database schema or a writable preference. Reads reject
malformed/mismatched settings and extra revisions. An absent legacy row means
comma; reads never backfill or alter earlier authority. Changing parsing requires
a new preview, preserving the original source and decisions.

Comma jobs retain their exact input-schema/definition/configuration identity.
Tab and semicolon use an explicit version-1.1 input/definition, bound again on
worker claim and parser completion. Receipts include the actual delimiter.
Comma effective-draft hashes retain byte-exact `/1` serialization; alternative
delimiters use `/2` with the delimiter in its header. Source/chunk hashes and
raw-span record keys are unchanged. The generated review contract displays the
persisted selection rather than current form state.

This is not yet a complete production wizard. Duplicate/count projection remains
CAP-04.S01.T02 work. Native-window, full 100k-record and packaged end-to-end
qualification remain required; unit/service composition is not a substitute.

The version-12 migration supplies protected append-only summary attempt, row,
group and completion relations for the remaining projection work. Exact v11 DDL
is retained as a test fixture; backup-first upgrade and rollback preserve prior
preview rows and create no historical summaries. No summary UI or worker is
claimed from this storage groundwork alone.

The summary adapter now computes compact rows from the actual effective draft,
with store/inspect permission for every row, including excluded and contextual
rows. It rechecks the exact current revision inside each insertion transaction.
Pages resolve sparse history once and stream selected decision payloads while
retaining the 16 MiB bound. Counts and candidate groups derive from complete stored
rows, never caller-supplied totals. Coverage uses included parsed records as its
denominator. Context rows, malformed rows and excluded records remain explicit.

Exact raw-record hashes and unique normalized DOIs identify within-preview review
candidates only; they do not merge works or predict canonical re-import effects.
Overlapping reasons count each candidate record once, with indexed group/member
paging rather than materialized pairs. A receipt binds project, preview, source,
manifest, draft, parse attempt, summary job/attempt, algorithm and ordered result.
Completion remains hidden until that exact output reference is accepted by the
durable queue. Any draft/rights change invalidates previous summary reads. Failed
attempts retain hidden rows; a recovered attempt begins at ordinal one.
The local summary activity now reuses the durable worker and current project
guards. Its distinct exact input binds source/parser, accepted parse, draft,
Intent context, privacy, native epoch and algorithm. The shared single-step job
assembler preserves historical parser definitions byte-for-byte. Summary retries
reuse Task Center continuation semantics with the actual unsuccessful predecessor
and exact scientific authority; they never silently adopt a new policy or draft.
Every bounded operation revalidates the project and authority, with cooperative
cancellation and heartbeat. Security-epoch mismatch cancels old queued summaries;
a later explicit calculation has new authority. Summary-only cancellation leaves
the review draft intact. The summary API/renderer and native/packaged/whole-project
scale qualification remain required task work.

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
