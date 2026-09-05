# Bounded paused-amendment correction maintenance

Predecessor: `07473e15a6212995fa48ece9909f0d51be7ebc26`.
No live backlog transition is part of this increment.
Authority: AGENTS post-GOV-MIG-0001 maintenance rule and the already selected
entry/return contract in ECR-0008, including its UX addendum. Risk tier 2:
control/evidence boundaries, requiring independent review before integration.

## Intended projection delta

Add one generic, opt-in correction relation through a v4.1 proposal schema and
taskctl compatibility projection. Existing packets and histories remain valid
without that relation. The relation authenticates one exact, quiescent, paused
immediate predecessor, its approval and complete serialized record at a real
Git commit. Bootstrap may append the correction without altering its parent;
materialization transfers sole hold ownership; independently qualified adoption
returns the hold to the same paused predecessor rather than ordinary Wave
scope. Explicit predecessor activation remains necessary. No nested or competing
corrections, false adoption, new control revision, GRR/GCR, separate controller,
kernel/store live-journal cutover or product/reference authority is introduced.

The parent freezes at the successful bootstrap append, not at external packet
approval. Entry revalidates its complete unchanged bytes. Before append, the
existing parent remains the sole hold owner under its existing authority; an
intervening parent change makes the proposed binding stale and entry fails.
The separate proposal-schema version preserves the exact existing v4 schema
bytes, which are themselves referenced by immutable older packets. It is not a
control-plane revision or a new controller.

Use a pure kernel projection for relation/hold invariants, and the existing
taskctl lock/CAS, append-only lifecycle events, approval authentication and
review/adoption checkpoint paths for persistence. Failures before publication
leave the predecessor unchanged. Existing atomic publication cannot yield a
partially transferred hold; retries inspect the same current projection and
may not duplicate entry/adoption. Unsupported withdrawal/disposal remains denied
rather than claiming a reviewed recovery that does not exist.

## Acceptance closure / first tests

- MA-01 Source/authority: exact packet-approved relation equals projected relation;
  complete paused parent bytes and approval match the separately bound Git
  snapshot. Reject wrong commit, fork, stale parent, approval substitution and
  recomputed self-asserted hashes without the authoritative Git source.
- MA-02 State: one owner before entry, during correction and after adoption. Parent
  remains frozen until adoption; it must have no active task/review or lease.
  Prevent parent activation, ordinary Wave resume and competing corrections.
- MA-03 History: preserve all old lifecycle/task/review/checkpoint records; reject
  relation removal, substitution, nested/duplicate/forked correction and
  unqualified/partial adoption. Old packet/schema histories replay unchanged.
- MA-04 Persistence: use real temporary Git repositories and the existing CAS writer
  to test stale source and interrupted publication. No fixture reads the
  repository's protected witness or researcher data.
- MA-05 Experience / product: not applicable to this maintenance implementation.
  New UX and reference changes remain inert until their separate exact approval.
- MA-06 Verification: narrow pure projection, schema, affected v4 validation,
  amendment bootstrap/materialize/activate/adopt and real Git/CAS tests; affected
  lint/types and generated-view checks. Full product/W1 qualification is deferred
  because no product, native, UI or deployment behavior changes here.

The maintenance is incomplete until both entry and return are wired and tested,
independent review accepts the exact commit, and a safe integration disposition
is recorded. Merely accepting a paused predecessor in packet validation is not
a repair and must not unlock execution.

## Implemented boundary and review preparation

The adapter uses the existing bootstrap/materialize/activate/adopt commands,
not a new correction command. Historical entry/quiescence checks apply to new
packets; an existing packet is treated as historical only after authenticating
its committed amendment row and approval introduction. A bare current YAML row
cannot bypass readiness. The paused Git snapshot independently rejects ordinary
active/review tasks, recovery holds, extra amendment owners, later amendments,
and leases. The approved child packet must descend from that snapshot.

The independently requested preflight led to explicit replay tests for the
historical snapshot's own quiescence, missing returned-parent review history,
injected historical rows and distinct schema identity. A repeated correction
adoption now fails before adding a second checkpoint. Successful return keeps
the prior completed task records unchanged, permits new parent work and requires
an explicit parent activation.

The tests use synthetic temporary authority for narrow adapter persistence
cases, with real schema/state validation and real CAS/locking/replacement. They
separately authenticate real temporary Git approval/snapshot ancestry and real
Git adoption checkpoints. They do not claim a synthetic packet or review is
production approval. Historical Windows line-ending behavior is retained: CAS
hashes exact file bytes, while existing evidence hashes retain their canonical
text convention.

All product findings F01/F02 and UX01-UX06 remain open. W1 and A08 remain paused;
no correction packet, reference approval, task claim, checkpoint, release gate,
or local-main integration is part of this maintenance increment. The separate
preparation records remain immutable. The maintenance's commit-bound evidence
and independent review are subsequent append-only artifacts.
