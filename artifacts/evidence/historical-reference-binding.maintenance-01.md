# Historical governed-reference binding maintenance

Predecessor: `63d916a56359742a863241c7521d1b7703f24bc7`.
Authority: the AGENTS post-GOV-MIG-0001 bounded-maintenance rule. Risk tier 2
(evidence/control validation), requiring independent commit-bound review before
use. No task, lease, hold, approval, product, reference or release mutation is
included. W1/A08 remain paused; A09 B00 is approved but not materialized.

The preflight demonstrates a current/history mismatch: ECR-0005/0006/0007 bind
approved 1.5 files under the active reference path. Publishing the separately
approved 1.6 package changes three, three and four of those bindings respectively.
The validators currently require those historical bytes to remain at the active
path forever, so a lawful successor would invalidate retained approval history.
The review renderer also reads the successor's approval as the older reference's
status. No original packet or adverse evidence may be rewritten to correct this.

## Smallest intended delta

Keep the existing strict current-file validator and its default behavior. Add a
shared resolver for governed-experience sources. Only a genuinely authenticated
immutable ECR approval may resolve active-reference bindings from its exact
packet commit, and only when the current clean, committed reference is a fully
authenticated approved successor of that historical package. Validate the old
declared hashes and package, every intervening new-ID/supersedes transition, the
new approval authority, and unchanged package content since approval. Other
bound files, including inert proposals, retain strict live-byte validation.

This bounded resolver supports the existing direct amendment publication route
used by the approved correction. A future Wave/slice proposed-to-approved
handoff remains explicitly unsupported and fail-closed here; its different
proposal-parent protocol is not broadened by this repair. Historical validation
of the old Wave/slice-approved package itself remains supported.

Use existing approval/package authentication, not a new controller, exception by
ECR identity, hash ratification, relaxed renderer or tolerance. The review page
must expose historical source commit/status distinctly from the active reference.
This is historical-source readability, not an effective-reference adoption: A08
does not acquire 1.6 execution authority before A09's qualified adoption.

## Acceptance and selected checks

- HR-01: reproduce rejection with real Git predecessor/successor commits before
  implementation; authenticate a lawful successor without changing old packets.
- HR-02: deny missing/dirty/substituted approval, packet, governed bytes, wrong or
  forked history, pending or same-ID reference, false supersedes, and package
  changes after approval. Clean CRLF worktrees retain normalized Git comparison.
  Publication must match the separately reviewed complete proposed inventory,
  allowing only the specified approval metadata and derived manifest hash. This
  prevents a self-consistent but never-approved initial content substitution.
  Exact authority paths must be clean in both index and worktree. Historical
  file display must not require a superseded file to exist at its mutable path.
- HR-03: proposals/non-reference files stay strict; historical approval status
  and exact source commit render truthfully and generated links remain valid.
- HR-04: existing ECR approval/paused-parent and site validation regressions pass;
  no backlog, product, baseline or approved reference changes. Full product/W1
  qualification remains deferred because this increment changes no such paths.

The new exceptional-path import exposed a pre-existing mypy error in the reused
UI history validator (`matches = []`). One explicit local list annotation fixes
that existing inference error without altering runtime behavior or any UI check.

Local-main integration remains deferred because existing branch ancestry has
unmet A08 gates. Review may authorize using only this maintenance on the current
campaign branch without approving that ancestry, reference activation or G1.
