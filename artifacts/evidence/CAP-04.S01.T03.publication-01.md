# CAP-04.S01.T03 — atomic publication increment

Parent checkpoint: `78952f814ec496da6f037dbf01b82b3ccc1a9998`.
Work in progress; this does not complete the task or expose a service/UI action.

The existing protected database transaction now contains canonical source
assertions, manifest/membership/seal, per-aggregate provenance/dependencies/outbox,
staged workflow output and accepted worker completion. Existing Core UUIDv7 and
aggregate/queue mechanisms remain authoritative. Full membership is stored in
paged relations and bound by an ordered digest, never truncated into the generic
event's bounded input list. Actual parser receipt revisions are retained as
typed dependencies and provenance inputs. Rights are not flattened to allowed:
canonical envelopes remain unknown, with exact per-record/default action rights
retained in immutable draft/manifest decision authority.

Re-import reuses source assertion IDs; scientific replay reuses the accepted
manifest. Changed files retain old assertions and compare against the explicit
sealed predecessor. Equal raw bytes with changed accepted fields/rights are
updates; multiple candidates on either side remain ambiguous, not Work merges.
Exact command replay authenticates the original attempt and accepted output,
rechecks current preview/draft access, and returns without adding facts.

## Tests first and adverse observations

- Publication test initially failed because the method did not exist. Happy
  publication, rollback after output completion and expiry during publication
  passed after implementation. Fault coverage was expanded to all six material
  publication boundaries; every failure retains the prior canonical counts.
- Lost-reply replay initially failed against the expired completed lease. It
  now verifies immutable attempt capability plus current access and replays the
  exact accepted output. The first replay implementation read the output wrapper
  as a list; the regression caught that shape error before correction.
- A deliberately forged staged exclusion initially published. The new
  pre-publication verification compares every retained staged field against the
  real current draft in bounded pages, rechecks store/inspect rights and the
  worker lease, then compares the final transaction's streamed identity with
  that independently reconstructed identity. The negative regression now passes.
- Raw-equal corrected mapping initially reported unchanged; comparing accepted
  fields and effective rights fixed that failure. Two current DOI candidates
  initially both reported certain updates; one grouped current-candidate lookup
  per stream now preserves ambiguity and avoids per-row current-batch scans.
- Source identity now reuses the already reviewed pure source-assertion helper.
  Scientific replay additionally requires actual prior workflow success and its
  exact output manifest, not merely an import seal.

Exploratory tests cover fresh success, six injected rollback points, fresh-clock
expiry, cancellation before publication, same-input/new-request replay,
same-file/new-preview reuse, changed-file comparison, corrected mapping,
ambiguous candidates, forged staging and 101 included records/102 complete
members. These are synthetic real-repository tests, not Windows DPAPI/native
principal or large-input performance qualification. Independent disposition and
fresh exact-candidate checks follow.

Still pending: portable publication/read ports, complete accepted-manifest reads,
explicit executor handling for already-atomic completion, current service
Intent/policy/session guards, service replay/restart wiring, API/generated client,
governed UI, protected native/packaged checks and the large-input publication
budget. Publication does not heartbeat inside its writer transaction and must
finish within its real durable lease; expiry rolls back. Do not claim 100k commit
or responsiveness qualification from the bounded 101-record proof.
