# CAP-04.S01.T02 — import preview, mapping and conflict UI

Claim base: `34a8015b14245ed76a6f9629a69c3ed8574bde42`. Authority: the
approved W2 packet at `c85a59f3a293f8e3f2eaf6454682c9a14b1efa55`,
CAP-04.S01, ADR-0027, inherited ADR-0019/0025/0026, and
`RO-UI-ACADEMIC-MINIMAL-1.7`. CAP-04.S01.T01 is DONE.

This task creates a reviewable draft, not canonical SourceRecord/Work imports.
CAP-04.S01.T03 owns atomic commits/manifests; CAP-04.S03 owns new work/version
reconciliation. No cloud traffic, provider credentials or real research fixtures.

| Material boundary | Outcome and planned proof |
|---|---|
| AC1: review and correction | Paginated raw/candidate comparison, explicit field mapping, exclusions, duplicate candidates, rights defaults, group edits and undo; domain and renderer behavioral tests. Immutable effective decisions bind accepted values, selection, rights, options and mapping revision. |
| AC1: cancellation/report | Cancel or failed parsing never publishes a canonical import. A complete diagnostic report covers malformed/excluded records without raw content or paths; spreadsheet output neutralizes active cells. Focused cancellation, malformed-source and export tests. |
| Source and project authority | Native selected regular file only; renderer receives no arbitrary read capability. Every Core action binds project, source digest, preview ID/revision and current rights. Test substitution, closed/read-only project, stale revision and lock/project-switch responses. |
| Durable/compatible execution | Reuse protected project storage, object-store and durable-job ports. Verified immutable source, bounded record pages, explicit ordinary restart versus security-lock interruption. Real project/worker, persistence/restart and cancellation-before-publication tests. |
| AC2: principal boundary | Synthetic native selection through authenticated Core and the actual project store, then preview, mapping, exclusion and safe report. Mocks cannot substitute for this wiring check. |
| AC3: governed experience | Implement the approved Import records journey in ingestion/reconciliation, with shared components/tokens, keyboard/focus/status and workflow return context. No illustrative corpus counts or fictitious resolved works. |
| Evidence selection | Focused changed-module, contract, native, renderer, rights and migration checks; bounded 100k pagination proof. Full W1 replay is not selected. Slice/Wave qualification retains broader obligations. |

## Read-only preflight and first regressions

The independent preflight identified a real integration mismatch:
`ProjectWorkerPolicy` only admits UUIDv7 projects although normal lifecycle-created
projects use UUIDv4 and the accepted workflow ProjectId contract supports both.
The approved current task explicitly integrates existing durable jobs and project
identities. Adjust only this adapter check, with actual lifecycle-created-project
admission and malformed/wrong-project denials before wiring imports. Keep job and
actor UUIDv7 constraints and repository/storage identity checks intact. This is
current-task integration, not a W1 reopening, new correction lane or automation
maintenance. The independent authority preflight found no new human gate for this
bounded delta; preserve W1 records and migration authority.

Before implementation, add draft/mapping/rights/digest and worker-admission
regressions. Keep raw IR immutable, unknown rights restrictive and stale revisions
rejecting. Subsequent integration checks must establish actual persistence and
native behavior; domain-only success is not task completion.

## In-progress boundary observations

- The lifecycle-created-project regression reproduced the v7-only worker rejection;
  the narrow bridge adjustment passes creation/enqueue and invalid/wrong-project
  denials. Job identity remains UUIDv7.
- Draft/mapping tests were added before their implementation. Independent read-only
  preflight found no blocking groundwork defect; final service proof must bind the
  immutable mapping revision and include mapping/exclusion diagnostics in reports.
- Object readers retain a writer reservation until closed. Ordered encrypted source
  chunks (128 KiB maximum) release this barrier before each parser read returns;
  actual encrypted-object replay permits a second connection to reserve the writer
  after every read. This is not native/production composition qualification.
- Independent storage preflight requires new preview chunk references to join object
  deletion authority. Never delete a shared chunk when one preview is cancelled;
  incomplete intake and pages must remain distinct from verified complete source.

Next: protected preview repository/migration and reference accounting, then durable
job composition, native intake, Core/client/renderer integration, focused real-boundary
qualification and formal independent commit-bound review. No task completion claimed.

## Draft-review acceptance closure

Checkpoint-03 review at `a6219124afd9165414b4ccefd0e0ff9cb714aa76` found
that undo could remove a current per-record inspection restriction. Immediate
cause: the rights guard covered direct decisions but not restored history.
Extend the current-rights row to every history jump: restoring an older draft
must not broaden any current action permission implicitly. Add denial → undo →
raw/historical read regression before remediation. Preserve the adverse review;
do not integrate its candidate until this boundary passes independent re-review.

Checkpoint-05 review at `4e328d5f41c63c8abae9270168407cc52e0d0ebb` found
that initial protected restart-lock state was not latched when native recovery
authority was bound. Extend recovery proof to initial state as well as later
events: Ordinary marker → initialized ApplicationRestart lock → bound latch
must rotate the epoch, while an unlocked ordinary restart may retain it. Preserve
the adverse finding and re-review this boundary before integration.

Checkpoint-06 review at `8ac575a70c62a0c07aef930ef9fba141fb064a00` found
that response checks referenced mutable caller input after awaiting transport.
Extend API identity proof across the asynchronous boundary: the request must own
one immutable snapshot before dispatch, and the response must bind to that exact
snapshot even if the caller changes its object. Add deferred-response mutation
tests for all seven import methods before remediation; preserve this P2 finding.
