# CAP-04.S01.T02 — protected paging observation and correction

Candidate `4df1c099b95d81c6c287193a44d248911ce44675` remained fixed.
Retained synthetic report:
`artifacts/tmp/import-review-scale-windows-261eazds/diagnostic.json`.
Raw report SHA-256:
`7def1f692fb2b1f80327fea43b41d6f48c53a8f56899d84f1c1318e8892ab22d`.
The run failed its unchanged 1200-second observer at 1200.707 seconds during
review paging. This is not a qualifying performance baseline or a parser timeout.

- Actual protected parser: 100,001 rows, 78.681 seconds, accepted output.
- Actual summary worker: 100,001 rows, 249.791 seconds, accepted output;
  expected counts, coverage and duplicate groups passed.
- 865 successful review requests, maximum 1.125 seconds and 29,461 bytes.
  Complete traversal, candidate membership and reopen were not reached.
- Peak whole-process working set: 133,722,112 bytes; canonical records: zero.
- HEAD and recorded source inputs unchanged; fixture retained. Test process
  absence verified before editing. No deadlines or functional assertions relaxed.

Root cause of repeated overhead: each public review page opened a protected
repository read per record; duplicate members repeated that path per member.
A new structural regression failed with 100 reads instead of one (0.973 seconds).
The sparse-selection test initially failed because that bounded port was absent;
its integration regression then failed because the member route did not use it.

Correction shares bounded row projection and current/historical rights checks.
Ordinary pages use one existing bounded read; sparse member pages select at most
100 ordered unique ordinals, without reading intervening records. Both retain
the 16 MiB repository cap and the complete 900,000-byte response cap. Cursors
advance only over emitted records. No caching, pooling, encryption, migration,
reference or permission change. Focused exact-commit verification and independent
disposition remain required before this correction or task can be accepted.

A selected encrypted predecessor regression also exposed an obsolete expected
v11 endpoint after this task added v12. Its first run failed (0.388 seconds).
The test now expects both actual migration IDs and schema v12 while retaining
the exact encrypted v10 backup assertions and checking no historical summary
completion is fabricated. No production migration or predecessor fixture changes.
