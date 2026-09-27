import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createCoreApiClient, decodeVersionContext, decodeVersionPlan, decodeVersionOutcome, decodeVersionPreview, decodeVersionWorkPage } from "../../packages/contracts/core-api/generated.ts";
const values = JSON.parse(readFileSync(process.argv[2], "utf8"));
for (const [name, decode] of Object.entries({context: decodeVersionContext, updated: decodeVersionContext, plan: decodeVersionPlan, outcome: decodeVersionOutcome, preview: decodeVersionPreview, page: decodeVersionWorkPage})) {
  assert.deepEqual(JSON.parse(JSON.stringify(decode(values[name]))), values[name], name);
}
const root = "C:/Research/synthetic";
let reply;
const client = createCoreApiClient(async () => ({status: 200, contentType: "application/json", traceId: "a".repeat(32), etag: null, body: JSON.stringify(reply)}));
const contextRequest = {root, workIds: values.context.works.map((work) => work.workId)};
reply = values.context;
await client.inspectScholarlyVersionContext(contextRequest);
reply = {...values.context, contextSha256: "0".repeat(64)};
await assert.rejects(client.inspectScholarlyVersionContext(contextRequest), /RO-CORE-RESPONSE-INVALID/);
reply = values.updated;
await client.inspectScholarlyVersionContext(contextRequest);
for (const patch of [
  {placements: values.context.placements.slice(1)},
  {versions: [...values.context.versions, values.context.versions[0]]},
  {preferenceStates: values.context.preferenceStates.slice(1)},
  {sources: []},
]) assert.equal(decodeVersionContext({...values.context, ...patch}), null);
assert.equal(decodeVersionPlan({...values.plan, version: values.plan.relation.source}), null);
assert.equal(decodeVersionPlan({...values.plan, relation: {...values.plan.relation, target: values.plan.relation.source}}), null);
assert.equal(decodeVersionPlan({...values.plan, relation: {...values.plan.relation, date: {precision: "day", value: "2025-02-29"}}}), null);
reply = values.preview;
await client.previewScholarlyVersionDecision({root, plan: values.plan});
await assert.rejects(client.previewScholarlyVersionDecision({root, plan: {...values.plan, rationale: "Changed plan"}}), /RO-CORE-RESPONSE-INVALID/);
reply = values.outcome;
await client.commitScholarlyVersionDecision({root, command: values.command});
for (const patch of [{versionRevisions: []}, {relationRevisionId: null}, {workStates: []}, {dependencyRunIds: []}, {planSha256: "0".repeat(64)}]) {
  reply = {...values.outcome, ...patch};
  await assert.rejects(client.commitScholarlyVersionDecision({root, command: values.command}), /RO-CORE-RESPONSE-INVALID/);
}
reply = values.page;
await client.listScholarlyVersionWorks({root, after: null, limit: 32});
console.log("Actual version client contracts: PASS");
