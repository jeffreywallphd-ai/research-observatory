# Evaluation registry

This directory contains deterministic, offline benchmark definitions and approved golden outputs. `registry.json` is the authoritative registry; `registry.schema.json` defines its machine-readable contract.

Each benchmark pins its dataset, canonical expected-output path, tolerance, executor, model version, prompt identity, schemas, and baseline lineage by SHA-256. Prompt-free benchmarks use the exact `none` declaration; all other prompts use a canonical, hashed file under `prompts/`. Initial version-1 baselines are created by an independently reviewed task. Every later baseline version must preserve the previous path, version, hash, approval path, and approval hash in `history` and reference an explicit approval record in `approvals/`. The approver must use a nonempty `human:` identity and must differ from the generator.

Run the complete registry:

```powershell
.venv\Scripts\python.exe tools\benchmark_registry.py --repo . --report artifacts\tmp\benchmark-results.json
```

The runner never overwrites a baseline. On a mismatch, use `--proposal-dir artifacts/tmp/benchmark-proposals` to write isolated candidate outputs for review. A baseline change is then a normal reviewed repository change: add a schema-valid approval record, pin its SHA-256, append the exact prior lineage, increment the baseline version, update the canonical expected output/hash, and run the foundation profile. Approval JSON is immutable once tracked. Never edit a golden output merely to make a regression green.

The initial cases are:

- `golden-metadata-normalization-v1`: normalizes the synthetic scholarly JSON fixture and compares exact canonical JSON.
- `contract-normalized-record-v1`: validates a representative normalized record against a strict JSON Schema and compares the deterministic validation result.
