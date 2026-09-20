# CAP-04.S01.T03 service-01 independent disposition

**APPROVED for this bounded service/request/manifest-read increment.**
Reviewer: `w2_document_packet_preflight`.
Candidate: `ad03ffc89c29bd48cc3ffdacadf519cc76bcf205`.
Base: `32f5bc5becb2ddece497858b6447d7c54d4dca4a`.
This is not task completion or public API/native/UI/large-input qualification.

Reviewed the exact Git implementation, tests, architecture note and evidence
delta. No reproducible material blocker found in the implemented bounded scope.

- Durable requests use an explicit typed, versioned envelope at the reserved
  `imports.commit-request.<UUID>` setting key. Writes and reads enforce the
  65,536-byte UTF-8 limit; reads require exactly one text revision zero and exact
  project/request/hash binding. Writes authenticate the current draft/parse and
  preserve the original actor/time; changed inputs or actor identity conflict.
  Malformed or extra revisions fail closed. Existing append-only storage is
  reused without changing v13, historical fixtures or workflow snapshot schemas.
- Scheduling stores the exact command before queue admission and finds the
  original idempotency result before building a new submission. A concurrent
  winner is reread and its saved configuration checked. The request-only gap is
  recoverable by explicit retry under current authority, not automatic adoption
  of a changed draft, privacy policy or security epoch. Worker dispatch validates
  the real immutable workflow definition/snapshot/claim and actual continuation
  predecessor against the saved inputs; repeated activity guards compare current
  source/draft/Intent/privacy/epoch authority without replacing those inputs.
- Ordinary restart retains the saved command. Security reconciliation includes
  commit jobs and requests cancellation before claiming old-epoch work. Preview
  cancellation includes active commits. Job selection reuses the existing
  actual-source lineage lookup rather than inventing new retry identity or
  relying on UUID chronology.
- Manifest header/member reads require a real sealed manifest, its original
  succeeded queue attempt and the exact accepted output manifest/digest. The
  same transaction applies historical and current effective store/inspect
  checks to all members, including records outside the requested page. The
  historical rights scan now selects compact rights rather than buffering 100
  full decisions. Member projection retains included/excluded decisions,
  canonical identities and comparison status, with strict cursor/limit checks
  and an ordered prefix under the existing 16 MiB repository byte bound.
- The existing factory now composes the commit adapter through a combined
  portable import port. The ordinary summary regression covers that affected
  shared composition; no source-schema migration or Work reconciliation is
  introduced. Original publication F01/F02 remain closed and their adverse
  records remain preserved.

Owner-reported fresh exact-candidate checks: 15 publication, eight service, two
request and one ordinary-summary case PASS (26 total) in 35.886 seconds;
Ruff/format seven files, mypy four files and architecture PASS. This review did
not rerun those completed checks or any broader suite. The implementation note
accurately identifies tests added alongside implementation, not pre-edit RED
proof, and preserves earlier checkpoint outcomes separately.

## Proof limits carried forward

Final guard/transaction lifetime, current-principal native execution, public
transport/UI and large-input qualification remain pending. In particular,
`manifest_members` invokes the complete current-rights pass on each requested
page. Enumerating N members with page size 100 therefore repeats approximately
N squared / 100 member-rights work. The bounded fixture tests do not establish
100k navigation or bridge latency; that integration dependency must be measured
and resolved as required before those criteria are claimed. This disposition
does not waive them or classify this partial checkpoint as task completion.
