# Baseline approvals

Version-1 baselines are established by their reviewed implementation task. Version 2 and later require one immutable JSON approval record in this directory. The record must identify the benchmark, adjacent from/to versions, old/new SHA-256 hashes, generator, distinct `human:` approver, approval time, and rationale.

Approval records are evidence of a decision, not a mechanism for silently updating output. The benchmark runner validates them but never creates them.
