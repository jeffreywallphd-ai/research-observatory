# CAP-04.S01.T03 — bounded manifest reads and publication preparation

This increment remains inside the approved task. It is not task completion,
100k qualification, a native-window proof or a new performance baseline.

- Preserve transport-02's P2 finding. Preview cancellation now states that
  retained source/audit and already committed records remain unchanged. The
  built-renderer regression asserts the announcement and actual retained
  database counts. Initial RED: 14.596s; development PASS: 14.746s.
- Repeated manifest paging previously rescanned every member's rights on every
  header/page call. Retain one adapter-local successful scan, keyed by sealed
  manifest, parse attempt and exact historical/current draft revisions. Always
  recheck active preview, accepted queue output and current head in the read
  transaction. No durable cache or renderer-supplied authority. Writers/replay
  force a complete scan; revocation, undo and cold adapters recheck authority.
  Initial three-case scaffold: one RED (3.053s); implementation PASS (3.248s).
- Preparation now retains the project/launch guard per bounded read, not across
  the complete verification scan. Recheck cancellation and refresh the lease
  immediately before independently guarded atomic publication. No heartbeat
  opens a competing writer inside that transaction. The common guard protocol
  moves unchanged into the portable import port. No lease/deadline relaxation.
  Two new guard/late-authority tests were RED (1.993s); six activity cases then
  passed (5.949s). Actual large writer duration remains to be measured.

Additional characterization covers off-page/default revocation, permitted undo,
cold adapter reads, preview cancellation and cancellation before the writer.
An initial test incorrectly tried undo after default inspect revocation (the
existing repository closes that path), and another passed a PreviewActor where
the queue requires WorkflowActor. Those were fixture errors, not passing proof;
corrected targeted cases passed (3.113s). Product denial rules were unchanged.

The missed integration risk was intake-only cancellation prose surviving the
new post-commit state. The performance risk is repeated full authorization work
per page, not permission checks themselves. The guard risk is holding the
lifecycle lock across all bounded verification pages. Tests select those exact
boundaries plus atomic publication/rollback and the real renderer/Core journey;
unchanged parser, summary, W1 and full profiles are not routinely replayed.
Exact committed checks and independent disposition follow this implementation
note; exploratory timings above are not commit-bound qualification.
