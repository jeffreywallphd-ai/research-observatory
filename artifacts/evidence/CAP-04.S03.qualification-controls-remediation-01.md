# CAP-04.S03 qualification-controls remediation 01

Predecessor: `d1e43e9303c80c0713863939184a5fb255c234cf`.
Adverse independent review:
`artifacts/evidence/CAP-04.S03.qualification-controls-review-01.md`.
This is a bounded slice-evidence control correction; no product authority,
scoring, fixture gold, task approval, reference or release rule changes.

F-S03-PERF-01: the warm feature observer now starts before public batch
preparation and enqueue, and remains active through the authoritative terminal
status. A bounded terminal poll covers the case where the real background worker
already owns the job. The focused regression forces a feature computation from
the schedule response before it returns and requires rejection. Before the
producer edit, that test failed because the required observer boundary did not
exist; it now passes.

F-S03-PERF-02: the measured page path now decodes every strict candidate
explanation and hashes its complete content. After the timed requests, it
authenticates the cold and warm durable candidate sets and every stored ordinal
and pair hash in the protected SQLCipher database. The complete cold/warm
inventories must agree, and every API item hash must match its exact durable
ordinal. A content-free aggregate digest is retained in the sample. The focused
regression rejects a repeated later-page pair and a substituted pair while
counts and cursors remain unchanged. It failed before the verifier existed and
passes after remediation.

Nonqualifying local smoke on the revised workload completed at the working
candidate and is retained at
`artifacts/tmp/CAP-04.S03.workload-remedy-smoke-03.log` (SHA-256
`d9e7fa3c3ab92b5a7e22e3a1a0336d8c3308611633d40e95728a93cfad487d09`).
It observed 2463 frozen records, 105451 comparisons, 1273 total/1142
cross-source retrieved pairs, 1092 true positives and 1115 gold pairs. The
protected project retained 203 sources and 103 candidates. Distinct cold/warm
jobs took about 33.85/29.20 seconds, with zero warm feature computations; the
100-item and three-item pages took about 13.05/13.10 seconds. Their exact stored
content matched across the two jobs, and the measured path made zero provider
calls. This smoke has one process, no peak-memory result, and is neither
calibration nor performance qualification.

The first remediation smoke exposed a nonterminal background-worker race; the
second exposed the API JSON-to-strict-model decoding requirement. Their failed
logs remain ignored at `artifacts/tmp/CAP-04.S03.workload-remedy-smoke.log` and
`artifacts/tmp/CAP-04.S03.workload-remedy-smoke-02.log`. No failing test or
adverse finding was deleted. The next step is an independent incremental review
of the committed remediation candidate before calibration.
