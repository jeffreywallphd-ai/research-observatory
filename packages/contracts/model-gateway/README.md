# Model gateway contracts

This directory owns the provider-neutral model task and result boundary from
ADR-0021. `model-task.schema.json` is the language-neutral authority;
`generated.ts` and Core's generated Python decoder are deterministic products
of `generate.mjs` and must not be edited directly.

Task envelopes carry immutable content identities instead of research text.
Provider SDK objects, credentials, local paths, network details, and model
weights are outside this package.

Check committed generation and run focused tests with:

```powershell
node packages/contracts/model-gateway/generate.mjs --check
npm test --prefix packages/contracts -- --run model-gateway/model-task.test.ts
.venv\Scripts\python.exe -m unittest tests.ai.test_model_gateway_contracts
```
