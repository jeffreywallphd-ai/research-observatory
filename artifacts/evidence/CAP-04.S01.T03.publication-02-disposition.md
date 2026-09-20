# CAP-04.S01.T03 publication-02 independent disposition

**APPROVED for this bounded remediation and activity/port increment.**
Reviewer: `w2_document_packet_preflight`.
Candidate: `32f5bc5becb2ddece497858b6447d7c54d4dca4a`.
Incremental base: `60b50c1cfbd6ac7e57fd2ab5239061d41bef5b68`.
Original adverse publication candidate: `e7523d782f1bb4145ea1dc4aadf96f585d297b72`.
This is not task completion or service/API/UI/native/large-input qualification.

## Prior findings

- **T03-PUBLICATION-01-F01 — CLOSED.** `_manifest_access` authenticates a sealed
  manifest's preview/draft binding, current active/default rights and matching
  historical/current parse lineage. It walks all members, not only matching or
  first-page candidates, resolving current effective decisions through the
  existing undo-aware history selector. Historical and current effective
  store/inspect permissions must both permit the action. The check occurs under
  the final writer before predecessor comparison and also protects scientific
  reuse and completed-response replay. No historical rights are rewritten and
  no other rights dimension is granted. The new regression reproduces the
  revoked-predecessor case and requires denial with unchanged canonical counts.
- **T03-PUBLICATION-01-F02 — CLOSED.** Succeeded replay now reconstructs the
  expected scientific identity from authenticated current draft rows and the
  exact retained preparation, using immutable attempt authentication instead of
  incorrectly requiring a still-running completed lease. The output must resolve
  to a real sealed import manifest with that identity and pass manifest access;
  the unchanged queue replay then checks the full accepted output/attempt. The
  parser-receipt substitution regression stages and completes an actual generic
  queue output after preparation, then requires publication replay denial with
  no added canonical facts. Valid lost-reply and same-scientific/new-request
  cases remain covered; the original manifest attempt is not incorrectly bound
  to the new request's attempt.

The publication-01 adverse disposition remains intact. The remediation note and
task-start addendum retain both initial RED regressions and their distinct root
causes rather than replacing the prior result with an approval.

## Incremental review

The new portable port exposes typed inputs, claims, actors and bounded-operation
callbacks without storage handles or paths. The activity delegates actual
authority to the repository and supplied existing action guard, checks
cancellation between preparation pages, heartbeats the current claim, rejects
nonadvancing or out-of-range cursors, and returns the independently reviewed
atomic-completion marker only after publication. Expected preview failures are
mapped to fixed workflow diagnostics; cancellation remains observable through
the established worker path. Its tests use real isolated queue/repository
fixtures for publication, cancellation, cursor failure and heartbeat.

Packaging build-contract, verifier and strict test inventories include the new
activity and port. No migration or historical fixture change is introduced by
this increment. No additional reproducible material blocker was found.

Owner-reported fresh exact-candidate checks: 14 publication, four activity and
one packaging test PASS (19 total) in 23.033 seconds; Ruff/format seven files,
mypy three files and architecture PASS. The two new regressions previously
failed before remediation (two failures in 2.752 seconds). This independent
review inspected the exact Git source/test/evidence delta and reused the
completed narrow checks; no suite was rerun.

## Limits

Current Intent/privacy/native-session service composition is not yet exposed or
approved here. The activity's supplied guard lifetime across pre-publication
verification and the final writer, cancellation responsiveness and aggregate
memory cost of the member-rights pass still require the pending integrated and
large-input qualification. In particular, a row-count page bound is not a
measured byte/memory bound. These limits do not reclassify the existing bounded
fixture checks as real-principal or 100k evidence and do not waive later task or
slice criteria.
