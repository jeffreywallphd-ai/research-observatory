import { describe, expect, it } from "vitest";
import type { ReviewContext, WorkState } from "@research-observatory/contracts/core-api";
import { reconciliationReviewPlan } from "./reconciliationReviewModel";

const id = (n: number) => `01900000-0000-7000-8000-${String(n).padStart(12, "0")}`;
const work = (n: number, members: number[]): WorkState => ({ schemaVersion: "1.0", workId: id(n), revisionId: id(n + 10), previousRevisionId: null,
  disposition: "active", aliasTarget: null, assertionRevisionIds: members.map(id), decisionRevisionId: null });
const context = (works: WorkState[]): ReviewContext => ({ schemaVersion: "1.0", algorithm: "scholarly-duplicate-ranking/1.0.0",
  featureVersion: "scholarly-duplicate-features/1.0.0", configurationSha256: "b3e04c16bcfbb8588a718d55a94217a21a02ba1877fa9ea6ba187ebcdfc98dfc",
  evidenceSha256: "a".repeat(64), works, inboundAliases: [], unassignedAssertionRevisionIds: [], sources: [] });
const choice = { action: "merge" as const, survivor: id(1), separated: [], aliasGroups: {}, rationale: "Synthetic researcher decision." };

describe("explicit reversible reconciliation choices", () => {
  it("preserves every source and binds retired identities to the selected survivor", () => {
    const result = reconciliationReviewPlan(context([work(1, [21]), work(2, [22])]), choice)!;
    expect(result.partitions).toEqual([{ group: "retained", existingWorkId: id(1), assertionRevisionIds: [id(21), id(22)] }]);
    expect(result.aliases).toEqual([{ workId: id(2), revisionId: id(12), targetGroup: "retained" }]);
    expect(result.conflictDisposition).toBe("retain-all");
  });
  it("requires a nonempty split, a rationale, and explicit routing for inherited aliases", () => {
    const current: ReviewContext = { ...context([work(1, [21, 22])]),
      inboundAliases: [{ ...work(3, []), previousRevisionId: id(14), decisionRevisionId: id(15), disposition: "alias", aliasTarget: id(1) }] };
    expect(reconciliationReviewPlan(current, { ...choice, action: "split", separated: [id(22)] })).toBeNull();
    const plan = reconciliationReviewPlan(current, { ...choice, action: "split", separated: [id(22)], aliasGroups: { [id(3)]: "separate" } });
    expect(plan?.partitions[1]?.assertionRevisionIds).toEqual([id(22)]);
    expect(plan?.aliases[0]?.targetGroup).toBe("separate");
    expect(reconciliationReviewPlan(current, { ...choice, action: "split", separated: [] })).toBeNull();
    expect(reconciliationReviewPlan(current, { ...choice, rationale: "  " })).toBeNull();
  });
  it("can assign unassigned assertions without inventing a Work identity", () => {
    const current = { ...context([]), unassignedAssertionRevisionIds: [id(21)] };
    expect(reconciliationReviewPlan(current, { ...choice, action: "assign", survivor: null })?.partitions[0]?.existingWorkId).toBeNull();
  });
});
