# CAP-05.S02.T03 measured performance owner acceptance

The repository owner accepted the specific warm timing observation and directed
that no more time be spent investigating it:

> I accept that slight overage. Please don't spend more time over the 2 second overage.

This decision is recorded in the immutable
`artifacts/evidence/CAP-05.S02.T03.R01.json` submission at candidate
`c17511401808d003eaa2c74ff0b866e65a6955d9`, canonical SHA-256
`5e629932746a0a97bae8933bb5038e65dab93c39727b8ac238b850e83bea2205`.

Performance report `artifacts/tmp/CAP-05.S02.T03.performance-124.benchmark.json`
has SHA-256
`fc1b2ca099d8b400806e7e3340c9a0a2a25982f0f6716006a22947865eb51f77`.
Its cold p95 is 59.7308133 seconds against the 90-second target; warm p95 is
62.5333542 seconds against the 60-second target, an overage of 2.5333542 seconds.
The aggregate report remains FAIL with exit code 1. All eleven child executions
passed their functional, resource and portable handoff checks; those results do
not turn the timing budget failure into a pass.

The accepted observation is nonblocking for this task and S02 slice closeout and
is carried into W2 qualification review. The original targets, adverse reports,
raw samples, layout uncertainty and resource boundaries remain unchanged. No
further investigation, tuning or repetition of this overage is authorized by
the current direction. This acceptance does not approve W2 release or confer a
general performance exemption.
