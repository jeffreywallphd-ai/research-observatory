# CAP-04.S01.T02 — bounded batching disposition

Independent reviewer `w2_document_packet_preflight` conditionally approved
`86ddb4e6ff25511a93d53cd4caaba8982d4916d0` relative to `4df1c099`;
no material finding. Fresh 39 draft/review/API/protected migration tests passed
in 24.132 seconds; Ruff/format, Mypy, architecture, backlog and clean build checks
passed. The reviewer executed no additional tests.

The complete protected scale run passed at that fixed candidate in 535.329
seconds (runner): 100,001 review rows/1,001 pages, 100,000 DOI group members/1,000
pages, counts/coverage, close and fresh-runtime reopen. Canonical records stayed
zero, protected headers remained encrypted, HEAD and recorded inputs unchanged.
Retained report `artifacts/tmp/import-review-scale-windows-v_tyt82l/diagnostic.json`,
SHA-256 `dbc71c3ce773922dad4ba98220079596fabc2ee26cfb366f9b13d0b77378ede3`.
Measurements are descriptive, not an approved performance baseline.

The fresh built-renderer test failed in 13.981 seconds waiting for its queued
badge. Root cause: fixture setup enters the application lifespan, starting the
automatic worker while this test also advances the real worker explicitly.
A diagnostic invocation suppressing only `ImportPreviewService.start` passed
the whole interaction in 12.887 seconds. A late Playwright TargetClosed warning
after OK remains disclosed; it is not an application page-error finding.

The test-only correction patches scheduler startup solely during fixture setup,
retaining real explicit worker execution and every outcome assertion. It does
not qualify automatic pump startup; the protected scale test does. Independent
review found this seam appropriate. Fresh corrected renderer and protected-scale
proof must run at the final candidate; the result above stays ancestral evidence,
not relabeled as fresh after the fixture-only commit. No broad suite replay.
