# Baseline approvals

Version-1 baselines are established by their reviewed implementation task. Version 2 and later require one immutable JSON approval record in this directory, validated by `evaluation/baseline-approval.schema.json`. The record must contain exactly the governed fields and identify the benchmark, adjacent from/to versions, old/new SHA-256 hashes, generator, distinct nonempty `human:` approver, approval time, and rationale. Its exact byte SHA-256 is pinned in current and historical baseline lineage; Git-aware validation rejects rewrites and removals after the record is tracked.

Approval records are evidence of a decision, not a mechanism for silently updating output. The benchmark runner validates them but never creates them.
