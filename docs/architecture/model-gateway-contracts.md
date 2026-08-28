# Model gateway contracts

ADR-0021 establishes the provider-neutral boundary for model work. The Draft
2020-12 authority is
`packages/contracts/model-gateway/model-task.schema.json`; deterministic
TypeScript and Python runtimes are generated from that file and checked into
their consuming source trees.

## Boundary

The contract expresses eight operations: embedding, reranking, classification,
NLI, structured extraction, generation, moderation, and tool call. Each has a
task-specific input shape. Research content is represented only by immutable
aggregate, revision, and content-hash references. The contract contains no raw
prompt or result text, local path, credential, provider SDK object, transport,
or database handle.

Task requirements make citation policy, data classification, deadline, input
and output token bounds, and required model features explicit. Execution is
either dynamic or pinned. A pinned request fixes provider, model, runtime,
configuration, and evaluation identities and versions.

## Result invariants

Every result records the request hash and trace identity plus:

- the selected provider/model/runtime/configuration/evaluation route, or a
  stable reason that no route was selected;
- the exact policy decision and reason codes;
- queue, execution, and total latency;
- reported token counts or an explicit not-reported/not-applicable state;
- output validation and content hash;
- confidence and calibration state;
- citation state and immutable source references; and
- stable retry and partial-output diagnostics.

Successful or degraded results require an allowed decision, selected route,
accepted validation, and a task-matching output. Non-success results cannot
carry output. Reported token totals must add up and remain within the task
bounds; successful latency must stay within the task deadline. Accepted
artifact validation uses the artifact content hash, validation state controls
hash/error metadata, every supplied citation points to a task input, and
indexed scores remain within task-specific input/label/cardinality bounds.
Selected routes for pinned tasks must match every pin.

Unsupported required features fail before provider execution with
`model-task-feature-unsupported`. The failure has no provider route, output, or
research content. Silent fallback is forbidden for a pinned task.

## Ownership

`packages/contracts/model-gateway/generated.ts` is the portable TypeScript
consumer surface. Core uses
`services/core-api/src/research_observatory_core/model_gateway_contracts.py`.
Provider adapters introduced by later CAP-07 tasks translate at their boundary;
they do not change or leak into these types.

Regenerate after an authorized schema change and reject drift with:

```powershell
node packages/contracts/model-gateway/generate.mjs
node packages/contracts/model-gateway/generate.mjs --check
```
