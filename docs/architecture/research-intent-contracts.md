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

## Compatibility and packaging

The contract version is `1.0.0`; no earlier Research Intent schema exists.
Future additive revisions require compatible fixtures. Breaking evolution
requires a bridge/migration and accepted ADR under the domain compatibility
policy. The schema is a build-manifest input, and the generated Python decoder
is a required hidden module in the Windows Core sidecar package.

Governed decisions: ADR-0022 and ADR-0023.
