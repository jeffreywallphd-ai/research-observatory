# Benchmark and golden-output registry

`evaluation/registry.json` is the authoritative catalog for deterministic evaluation cases. Its schema requires every case to identify:

- a SHA-256-pinned dataset and approved expected output;
- an executor and benchmark kind;
- an exact tolerance policy;
- model ID, version, and revision, including an explicit deterministic non-model identity;
- prompt ID, version, and hash, or an explicit `none` declaration;
- all input schemas by path and hash; and
- baseline version, prior history, and current approval.

`tools/benchmark_registry.py` validates the registry and all confined, non-redirected inputs from immutable read snapshots, then executes every case without network access. Its deterministic JSON report records the registry and baseline versions, input and expected hashes, canonical actual-output hash, tolerance, exact-match metric, status, and diagnostic.

The foundation profile runs two initial cases:

1. A golden parser normalizes the synthetic scholarly metadata corpus, including author variants, duplicate DOI identity, partial dates, missing fields, and Unicode.
2. A contract benchmark validates a representative normalized record against a strict Draft 2020-12 JSON Schema and compares the exact validation result.

## Baseline changes

The runner has no baseline-update command and never writes under `evaluation/baselines/`. A mismatch fails. `--proposal-dir artifacts/tmp/benchmark-proposals` may write isolated candidates for inspection; it cannot approve or apply them.

Version 1 is the independently reviewed initial baseline. Every subsequent version must:

1. increment exactly one version;
2. append the exact previous version, hash, and approval to history;
3. change the expected-output hash;
4. reference an immutable approval JSON under `evaluation/approvals/`;
5. identify a `human:` approver distinct from the generator; and
6. record adjacent versions, exact old/new hashes, a timezone-aware approval time, and rationale.

Git-aware validation compares a dirty tree with `HEAD`, or a clean commit with its parent, so changing expected output without matching version/history/approval fails. Static lineage and approval checks remain available in source exports without Git history.

Run locally:

```powershell
.venv\Scripts\python.exe tools\benchmark_registry.py --repo . --report artifacts\tmp\benchmark-results.json
.venv\Scripts\python.exe tools\verify.py --profile foundation
```
