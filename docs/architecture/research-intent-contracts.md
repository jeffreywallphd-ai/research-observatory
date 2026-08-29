# Research intent contracts

## Boundary

`packages/contracts/intent/research-intent.schema.json` is the portable authority
for immutable Research Intent revisions and compact governing references. It is
framework-, persistence-, provider-, and deployment-neutral. The deterministic
generator emits checked-in TypeScript and Python validators whose embedded
schema hash must match the canonical UTF-8/LF schema bytes.

This T01 boundary does not persist a current revision, render the guided intent
workspace, compute downstream impact, or enforce tools. Those duties remain in
`CAP-03.S02.T02`, `CAP-03.S02.T03`, `CAP-03.S05`, and `CAP-03.S06`.

## Revision and authority model

A revision records stable intent, revision, and project UUIDv7 identities; an
exact contract version; immutable content identity; creation actor/time; state;
researcher rationale; complete intent payload; and any terminal decision. The
first revision has no parent. Every later revision points to the immediately
prior revision number, identity, and content hash. Prior content is retained by
the authoritative content/persistence boundary and is never embedded or
rewritten by a new revision.

Draft and proposed revisions have no decision and may retain explicit unknown
fields and unresolved decisions. Accepted, rejected, and superseded records
carry a matching terminal decision. Acceptance is human-only. Only a complete,
valid accepted revision can produce a downstream
`research-observatory-research-intent-reference`; the reference binds intent and
revision identity, revision number, contract version, and content hash.

## Mode-sensitive fields

Shared fields preserve researcher-authored narrative alongside structured
research question, intended contribution, phenomenon, unit/level, source scope,
evidence types, novelty standard, autonomy, stopping, egress, and unresolved
decisions. A discriminated branch adds requirements for systematic, theory,
technical, hermeneutic, critical, novelty, or empirical work.

Mode, primary use case, and stopping condition must agree. Systematic,
technical, novelty, and empirical accepted intent requires a specified unit and
level. Theory, hermeneutic, and critical work may use an explicit
not-applicable state with rationale. Unknown is never treated as not applicable.
The `manuscript-review-revision` use case may retain the existing project's
epistemic mode.

## Researcher authority and safety

Autonomy never grants authority to accept intent or change scope. Those human
gates are mandatory, as is human confirmation of stopping. Allowed actions are
drawn from a closed vocabulary and cannot exceed the selected human-only,
suggest, prepare-reversible, or execute-reversible level. Intent acceptance,
scope mutation, and direct external-egress authority are not actions in that
vocabulary. Every stopping condition must belong to the selected mode; a shared
resource-budget condition is secondary and cannot replace the mode's required
condition. Local-only egress has neither destinations nor an external-egress
gate; approved egress modes name at least one opaque approved destination and
require that human gate. T03 must evaluate these declarations at service
boundaries and record the governing revision; this contract does not claim that
enforcement early.

Both generated decoders fail closed on unknown or unsafe keys, invalid portable
identities, inconsistent lineage/status/decision, incomplete accepted intent,
mode/use-case/stopping mismatch, reversed temporal scope, inconsistent egress,
or weakened human authority. Successful decoding takes ownership and returns a
deeply immutable snapshot. Narrative is untrusted bounded data, never an
instruction to the application or model.

## Core service boundary

The local Core API completes the authority handoff after draft creation:

- `POST /projects/intent/acceptances` creates a new immutable `accepted`
  revision only when a human confirms the exact current decision-complete draft
  revision and content hash. The revision, provenance event, outbox event, and
  idempotency binding commit atomically.
- `POST /projects/intent/policy/evaluations` resolves the latest accepted
  revision and evaluates one typed action against its epistemic mode, autonomy
  level, human gates, local-only egress rule, output label, and stopping
  conditions. It returns `allow`, `deny`, `recommend-human`, or
  `require-confirmation` with the compact governing reference.

Policy evaluation is not a capability token and cannot satisfy a human gate.
Gate-bound actions always return a non-allow decision, local-only intent denies
external egress, and stopping remains human-confirmed. Every evaluation writes
a content-free decision record and matching provenance fact before returning;
an audit failure therefore fails the requested action closed. Downstream
services supply trusted subject context, call this boundary before
consequential work, and retain the returned governing reference with resulting
artifacts or operations.

The Core service caches the effective policy snapshot by project and accepted
revision. Human acceptance and policy evaluation share one synchronization
boundary, so a committed acceptance replaces the cached governing snapshot
before any later evaluation can begin. A process restart rebuilds the cache
from the immutable revision history; drafts never invalidate or populate it.

Policy audit excludes research questions, source content, manuscript text, and
attempted payloads. It retains only action, subject type, outcome, reason,
required gates, working-output label, stopping-confirmation state, and the
immutable governing reference.

## Compatibility and packaging

The contract version is `1.0.0`; no earlier Research Intent schema exists.
Future additive revisions require compatible fixtures. Breaking evolution
requires a bridge/migration and accepted ADR under the domain compatibility
policy. The schema is a build-manifest input, and the generated Python decoder
is a required hidden module in the Windows Core sidecar package.

Governed decisions: ADR-0022 and ADR-0023.
