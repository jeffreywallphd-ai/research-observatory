// Actual synthetic repository projections supplied by test_client_contract.py.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createCoreApiClient, decodeCandidatePage, decodeReviewContext, decodeReviewPlan,
  decodeReconciliationInspection, decodeReviewPreview, decodeReviewOutcome } from "../../packages/contracts/core-api/generated.ts";

const values = JSON.parse(readFileSync(process.argv[2], "utf8"));
for (const [name, decode] of Object.entries({ candidates: decodeCandidatePage, inspection: decodeReconciliationInspection,
  context: decodeReviewContext, plan: decodeReviewPlan, preview: decodeReviewPreview, outcome: decodeReviewOutcome })) {
  assert.deepEqual(JSON.parse(JSON.stringify(decode(values[name]))), values[name], name);
}
assert.equal(decodeCandidatePage({ ...values.candidates, items: [{ ...values.candidates.items[0], score: 0 }] }), null);
assert.equal(decodeReviewPlan({ ...values.plan, partitions: values.plan.partitions.slice(0, 1) }), null);
assert.equal(decodeReviewContext({ ...values.context, sources: values.context.sources.slice(0, 1) }), null);
assert.equal(decodeReviewOutcome({ ...values.outcome, workStates: [...values.outcome.workStates, values.outcome.workStates[0]] }), null);
const root = "C:/Research/synthetic";
let reply;
const client = createCoreApiClient(async () => ({ status: 200, contentType: "application/json", traceId: "a".repeat(32),
  etag: null, body: JSON.stringify(reply) }));
reply = values.inspection;
await client.inspectScholarlyReconciliation({ root, assertionRevisionId: values.inspection.result.assertionRevisionId });
reply = values.context;
const command = { root, workIds: values.context.works.map((work) => work.workId), unassignedAssertionRevisionIds: [] };
await client.inspectScholarlyReviewContext(command);
reply = { ...reply, evidenceSha256: "0".repeat(64) };
await assert.rejects(client.inspectScholarlyReviewContext(command), /RO-CORE-RESPONSE-INVALID/);
reply = values.preview;
await client.previewScholarlyReview({ root, plan: values.plan });
await assert.rejects(client.previewScholarlyReview({ root, plan: { ...values.plan, rationale: "Different decision" } }), /RO-CORE-RESPONSE-INVALID/);
reply = values.outcome;
await client.commitScholarlyReview({ root, command: values.command });
await assert.rejects(client.commitScholarlyReview({ root, command: { ...values.command, commandId: values.preview.commandId } }), /RO-CORE-RESPONSE-INVALID/);
const syntheticId = (n) => `01900000-0000-7000-8000-${n.toString(16).padStart(12, "0")}`;
const active = values.outcome.workStates;
for (const workStates of [
  active.slice(0, 1),
  active.map((work, i) => i === 0 ? { ...work, assertionRevisionIds: [syntheticId(1)] } : work),
  active.map((work, i) => i === 0 ? { ...work, previousRevisionId: syntheticId(2) } : work),
  active.map((work, i) => i === 0 ? { ...work, workId: syntheticId(3) } : work),
  active.map((work, i) => i === 1 ? { ...work, previousRevisionId: syntheticId(4) } : work),
]) {
  reply = { ...values.outcome, workStates };
  await assert.rejects(client.commitScholarlyReview({ root, command: values.command }), /RO-CORE-RESPONSE-INVALID/);
}
reply = { ...values.outcome, dependencyRunIds: [] };
await assert.rejects(client.commitScholarlyReview({ root, command: values.command }), /RO-CORE-RESPONSE-INVALID/);
reply = values.mergedOutcome;
await client.commitScholarlyReview({ root, command: values.mergedCommand });
for (const workStates of [
  values.mergedOutcome.workStates.filter((work) => work.disposition === "active"),
  ...[ { aliasTarget: syntheticId(5) }, { previousRevisionId: syntheticId(6) }, { workId: syntheticId(7) } ]
    .map((change) => values.mergedOutcome.workStates.map((work) => work.disposition === "alias" ? { ...work, ...change } : work)),
]) {
  reply = { ...values.mergedOutcome, workStates };
  await assert.rejects(client.commitScholarlyReview({ root, command: values.mergedCommand }), /RO-CORE-RESPONSE-INVALID/);
}
reply = { ...values.preview,
  affectedOutputRevisionIds: Array.from({ length: 20000 }, (_, i) => syntheticId(i + 1)),
  unknownImpactRevisionIds: Array.from({ length: 20000 }, (_, i) => syntheticId(i + 20001)),
};
assert.ok(Buffer.byteLength(JSON.stringify(reply)) > 1048576);
assert.deepEqual(JSON.parse(JSON.stringify(decodeReviewPreview(reply))), reply);
await client.previewScholarlyReview({ root, plan: values.plan });
const previewText = JSON.stringify(reply);
const boundedClient = (body) => createCoreApiClient(async () => ({ status: 200, contentType: "application/json",
  traceId: "a".repeat(32), etag: null, body }));
await boundedClient(previewText.padEnd(4194304)).previewScholarlyReview({ root, plan: values.plan });
await assert.rejects(boundedClient(previewText.padEnd(4194305)).previewScholarlyReview({ root, plan: values.plan }), /RO-CORE-RESPONSE-INVALID/);
await assert.rejects(boundedClient(JSON.stringify(values.outcome).padEnd(1048577))
  .commitScholarlyReview({ root, command: values.command }), /RO-CORE-RESPONSE-INVALID/);
console.log("Actual reconciliation client contracts: PASS");
