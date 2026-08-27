# Governance automation simplification

## Status and purpose

This is the migration design for replacing incident-specific deterministic
controllers with a small, stable governance kernel. The kernel and generic
store remain evidence-only while live W1 mutations use the existing `taskctl`
compatibility adapter. `GOV-MIG-0001` retires new incident-numbered controller
escalation without rewriting historical evidence or granting W1 execution
authority.

The existing controls preserved source history and prevented unsafe mutation,
but recovery growth made the control system a competing product: `taskctl`,
`recoveryctl`, and successive `gcrNctl` programs duplicate validation,
publication, review, and recovery semantics. Each newly discovered controller
defect can require another controller before the original work can resume.

GCR-0007 is the cutoff for that pattern. Its independently approved R04 remains
inert because the immutable transaction schema binds the original adoption
evidence path while the safe retry requires an append-only attempt-scoped path.
No GCR-0008 or further incident-numbered controller should be created.

## Selected target

Build one small kernel with five protocol operations:

1. `verify` authenticates source bytes, event ancestry, invariants, and the
   current projection.
2. `append` records one typed event with compare-and-swap publication.
3. `project` derives backlog, review, and human-readable views from the event
   history.
4. `recover` completes or rolls back one generic interrupted append using the
   same protocol as normal publication.
5. `next_legal_action` returns one structured decision, its reason, its risk
   tier, and any unmet authority.

Canonical history becomes a typed append-only event stream with periodic
authenticated checkpoints. Existing backlog and review pages remain readable
projections during migration. Protocol capabilities replace integer reader
ceilings; a reader declares the event and invariant capabilities it understands.

## Risk tiers

| Tier | Meaning | Default approval |
|---|---|---|
| 0 | Read-only inspection, validation, projection, or diff | None |
| 1 | Routine reversible mutation inside already approved scope | None; automatic receipt and independent review where currently required |
| 2 | Scope, security, migration, or authority-bound change | Independent review; human approval only when authority expands |
| 3 | Destructive, external, irreversible, costly, or release-authorizing action | Explicit human approval |

Human approval is not required merely because a controller is repairing its own
implementation. It remains required when product scope or execution authority
expands, data may be lost, an external side effect occurs, or a release decision
is made.

## Migration sequence

### 1. Shadow next-action projection

`python tools/governancectl.py --repo . next --shadow --json` is read-only. It:

- validates the current backlog schema;
- hashes the exact source bytes;
- emits one typed decision with risk and approval metadata;
- compares its decision category with legacy `taskctl next`; and
- verifies that backlog bytes and modification time did not change.

It is advisory until representative fixtures show agreement for active Wave,
task, amendment, gate, recovery, and complete-roadmap states. The command has no
mutation subcommand.

### 2. Typed event and projection kernel

Introduce versioned event envelopes, invariant capabilities, checkpoint-plus-tail
verification, and deterministic projections. Dual-run the event projection
beside the backlog without changing current authority.

The shadow implementation uses `tools/governance_kernel.py`, a pure module with
no filesystem, Git, clock, or process operations. `governancectl next` now wraps
its decision in a deterministic `next-action-observed` event, verifies the hash
chain from a fixed genesis, projects the event, builds an integrity-bound
checkpoint, and verifies an empty tail from that checkpoint. Protocol capability
names replace another integer reader ceiling. The complete event, projection,
and checkpoint remain output-only; no event journal is written in this increment.
The emitted checkpoint is explicitly marked `self-check-only`: its hash proves
internal consistency, not external authority. Persisted replay will require the
checkpoint hash from a separately trusted anchor.

### 3. Generic mutation receipts

Replace hand-built evidence packets for routine transitions with automatic
receipts containing source hash, event hash, changed projection fields, selected
checks, and exact Git binding. Review records findings against the receipt rather
than requiring a new bespoke state machine.

The first receipt increment is still shadow-only. `governancectl next` emits an
output-only `governance-transition-receipt` that binds the event, observed source,
exact projection delta, selected check results, and the producer commit/branch.
Receipt trust is explicitly `producer-asserted` and authority is `evidence-only`.
A dirty tracked worktree or legacy disagreement yields a truthful failed receipt,
not an exception and never execution authority. Git state is sampled before and
after generation to reject a racing producer-state change. The protocol requires
a nonempty, internally consistent check selection but deliberately does not
prescribe one universal checklist; callers select checks from the affected risk
surface and reviewers judge adequacy. Overall status also derives from bound
facts, so omitting a check cannot turn dirty producer state, source divergence,
or shadow disagreement into a passing receipt. No receipt journal or mutation
route exists in this increment; routing routine transitions through the receipt
protocol remains a later cutover step.

The next increment adds the append/recovery mechanism without activating it.
`tools/governance_store.py` has no CLI and no live-backlog path. It writes only
three fixed files inside an existing caller-supplied fixture directory: an
authenticated journal, one pending append transaction, and an operating-system
lock. Fixture roots nested in any Git worktree are rejected. Preparation is
inert; commit uses the caller's expected state and
transaction hashes as compare-and-swap boundaries. A single generic recovery
operation can complete or roll back either crash boundary. Receipts are built
automatically from the event transition. Stored hashes prove internal
consistency; CAS and recovery trust comes from the expected hash retained by the
caller, not from accepting the store's own current hash. Live governance
authority, maintenance operations, and legacy-controller retirement remain
outside this increment.

### 4. Generic recovery and maintenance

Use one `recover` protocol for interrupted appends. Add bounded `maintenance
apply` for controller/schema corrections that do not expand product authority.
Maintenance remains append-only, independently reviewable, and Tier 2 when it
changes security or migration invariants; it must not require a new numbered
recovery controller.

### 5. Cutover and retirement

Promote `next_legal_action` only after fixture and live shadow agreement is
stable. Freeze old controllers as historical validators, route new transitions
through the kernel, and remove duplicated mutation paths only after replaying all
retained histories. Historical evidence is never rewritten.

The first bounded live cutover is `planning/governance-migrations/GOV-MIG-0001.json`.
It releases the obsolete `HOLD-W1-GRR-0002` interruption, leaves W1 explicitly
PAUSED, and repairs the already implemented durable resume-record boundary in
the compatibility adapter. The record's pre-resume commit is immutable
transition authority; the later clean current `HEAD` is the compare-and-swap
identity. Recovery requires that `HEAD` be the direct child of the recorded
pre-resume commit and that it modify exactly the five generated resume paths.
This prevents the prior self-contradictory equality while denying hidden source,
product, policy, evidence, or controller changes in the resume commit.

The old ECR, GRR, GCR, amendment, review, and evidence files remain historical
authority and validation input. No new incident-numbered controller should be
created. Until the generic journal becomes live authority, `taskctl` remains the
bounded compatibility mutation adapter for ordinary W1 transitions.

## Invariants retained

- Exact source hashes and compare-and-swap publication.
- Append-only approvals, reviews, findings, closures, and adverse attempts.
- Independent review at security, migration, public-contract, and release
  boundaries.
- Fail-closed behavior for unsupported events or invariants.
- Protected witness and researcher data safety.
- No task, Wave, gate, hold, or remote mutation from shadow mode.

## Verification for the first increment

- Unit tests cover recovery precedence and typed decision fields.
- A repository-level subprocess test proves the command emits valid JSON and
  leaves the backlog byte-for-byte unchanged.
- CLI tests prove shadow and JSON flags are mandatory.
- Ruff, mypy, and the governed quality-scope check include the new tool and test.

## Verification for the event-kernel increment

- Identical inputs produce identical event and projection hashes.
- Full replay equals checkpoint-plus-tail replay.
- Payload tampering, checkpoint tampering, sequence gaps, forks, unknown or
  missing required capabilities, and execution-authority substitution fail
  closed.
- Canonical hashing rejects Python-only containers and non-string object keys;
  decision and program subcontracts reject missing, extra, or invalid fields
  even when an attacker recomputes every enclosing hash.
- The live shadow command validates its emitted event/checkpoint and still leaves
  backlog bytes and modification time unchanged.

## Verification for the receipt increment

- Deterministic receipts bind the exact event, source observation, projection
  delta, selected check results, and producer Git state.
- Rehashed projection-delta, required-check, result, event, capability, and Git
  substitutions fail closed against independently supplied transition inputs.
- Dirty producer state and shadow disagreement remain evidence-only failed
  receipts; they cannot be converted into execution authority.
- The live command independently validates its receipt while preserving backlog
  bytes and modification time.

## Verification for the fixture append/recovery increment

- Preparation leaves journal state unchanged; commit appends exactly one event
  and its automatically generated receipt.
- Stale state hashes, competing pending transactions, substituted transaction
  hashes, rewritten transaction contents, and off-boundary recovery fail closed.
- Recovery completes a prepared append or rolls back a materialized successor
  after a simulated crash between state replacement and transaction cleanup.
- Static tests prove the store exposes no CLI and contains no live-backlog path;
  every write is confined to temporary fixture directories.

## Verification for the W1 compatibility cutover

- The live backlog validates with every retained recovery/control generation
  unchanged, `HOLD-W1-GRR-0002` terminally released, W1 PAUSED, and T03 still
  BLOCKED until an explicit later resume.
- Shadow and legacy next-action readers agree that the legal next transition is
  W1 resume and require no new Wave approval.
- T03 recovery rejects a missing or rewritten resume record, an uncommitted or
  non-direct-child `HEAD`, and every added, deleted, renamed, copied,
  type-changed, substituted, extra, or omitted resume path.
- A real Git fixture proves the pre-resume authority and committed current
  `HEAD` are distinct and the exact five-path modification-only transition is
  accepted.
- Independent control/security review precedes integration into local `main`;
  W1 is not resumed or claimed during the cutover.
