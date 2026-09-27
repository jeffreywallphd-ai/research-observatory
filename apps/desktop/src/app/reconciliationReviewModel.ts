import { decodeReviewPlan, type ReviewContext, type ReviewPlan } from "@research-observatory/contracts/core-api";

export interface ReconciliationChoice {
  readonly action: ReviewPlan["action"];
  readonly survivor: string | null;
  readonly separated: readonly string[];
  readonly aliasGroups: Readonly<Record<string, string>>;
  readonly rationale: string;
}

/** Build a complete, explicit proposal. Core rechecks current membership and rights. */
export function reconciliationReviewPlan(context: ReviewContext, choice: ReconciliationChoice): ReviewPlan | null {
  if (!choice.rationale.trim()) return null;
  const members = [...context.works.flatMap((work) => work.assertionRevisionIds), ...context.unassignedAssertionRevisionIds].sort();
  const split = choice.action === "split", separated = new Set(choice.separated);
  if (split && (choice.separated.length !== separated.size || choice.separated.some((id) => !members.includes(id)))) return null;
  const survivor = split ? context.works[0]?.workId ?? null : choice.survivor;
  const partitions = split ? [
    { group: "retained", existingWorkId: survivor, assertionRevisionIds: members.filter((id) => !separated.has(id)) },
    { group: "separate", existingWorkId: null, assertionRevisionIds: members.filter((id) => separated.has(id)) },
  ] : [{ group: "retained", existingWorkId: survivor, assertionRevisionIds: members }];
  const aliases = [...context.works.filter((work) => work.workId !== survivor), ...context.inboundAliases]
    .map((work) => ({ workId: work.workId, revisionId: work.revisionId, targetGroup: split ? choice.aliasGroups[work.workId] ?? "" : "retained" }));
  return decodeReviewPlan({ schemaVersion: "1.0", action: choice.action, works: context.works,
    unassignedAssertionRevisionIds: context.unassignedAssertionRevisionIds, partitions, aliases,
    conflictDisposition: "retain-all", evidenceSha256: context.evidenceSha256, rationale: choice.rationale });
}
