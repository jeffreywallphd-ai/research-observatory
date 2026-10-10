import { describe,expect,it } from "vitest";
import { decodeReprocessingAccepted,decodeReprocessingBatch,decodeReprocessingPage,decodeReprocessingQueue } from "./documentReprocessing";
import { correctionSource,correctionIdentity } from "../../../../tests/desktop/fixtures/document-correction";
import { reprocessingAcceptedFixture,reprocessingBatchFixture,reprocessingPageFixture,reprocessingBatchRevision,reprocessingItemId } from "../../../../tests/desktop/fixtures/document-reprocessing";
const project=correctionSource.projectId;
const page=(value: unknown)=>decodeReprocessingPage(value,project,reprocessingBatchRevision,reprocessingItemId);
describe("authenticated reparse comparison display",()=> {
  it("retains explicit ambiguity, unresolved corrections and inert prior/candidate text",()=> {
    const p=reprocessingPageFixture();p.anchorCounts.ambiguous=7;p.nextOffset=20;
    expect(page(p)?.unresolvedCount).toBe(1);expect(page(p)?.anchorCounts.ambiguous).toBe(7);
    expect(page(p)?.obligations[0]?.oldPreview).toContain("<script>");
    expect(decodeReprocessingBatch(reprocessingBatchFixture(),project)?.items[0]?.state).toBe("ready");
    expect(decodeReprocessingAccepted(reprocessingAcceptedFixture(),project,reprocessingBatchRevision,reprocessingItemId)?.impactState).toBe("completed");
  });
  it("denies substituted project/batch/item/source, overlarge pages and hidden unresolved tails",()=> {
    for (const changed of [
      {projectId:correctionIdentity(89)}, {batchRevisionId:correctionIdentity(90)}, {itemId:correctionIdentity(91)},
      {source:{...correctionSource,projectId:correctionIdentity(92)}}, {state:"ready-to-accept"}, {unresolvedCount:2},
      {candidateNodes:Array.from({length:21},()=>reprocessingPageFixture().candidateNodes[0])},
      {obligations:Array.from({length:33},()=>reprocessingPageFixture().obligations[0])},
      {confirmationSha256:"a".repeat(64)}, {nextOffset:-1}, {scholarlyVerification:"verified"}, {actorId:correctionIdentity(93)},
    ]) expect(page({...reprocessingPageFixture(),...changed})).toBeNull();
    const p=reprocessingPageFixture();p.candidateNodes[0]!.preview="📚".repeat(161);expect(page(p)).toBeNull();
  });
  it("never executes accessors and denies duplicate obligations or nested invented probability",()=> {
    let touched=false;const p=reprocessingPageFixture();Object.defineProperty(p,"source",{get:()=> {touched=true;return correctionSource;}});
    expect(page(p)).toBeNull();expect(touched).toBe(false);
    const repeated=reprocessingPageFixture();repeated.obligations.push({...repeated.obligations[0]!});expect(page(repeated)).toBeNull();
    const quality=reprocessingPageFixture();Object.assign(quality.newQuality.dimensions.sections,{acceptanceProbability:0.9});expect(page(quality)).toBeNull();
    const unknown=reprocessingPageFixture();Object.assign(unknown.impact,{releaseApproved:true});expect(page(unknown)).toBeNull();
  });
  it("requires per-document accepted identity and exact batch selectors",()=> {
    const b=reprocessingBatchFixture();b.items.push({...b.items[0]!});expect(decodeReprocessingBatch(b,project)).toBeNull();
    const accepted=reprocessingAcceptedFixture();accepted.revisionId=accepted.previousRevisionId;expect(decodeReprocessingAccepted(accepted,project,reprocessingBatchRevision,reprocessingItemId)).toBeNull();
    expect(decodeReprocessingAccepted(reprocessingAcceptedFixture(),project,reprocessingBatchRevision,correctionIdentity(66))).toBeNull();
    expect(decodeReprocessingQueue({schemaVersion:"1.0",projectId:project,items:[reprocessingBatchFixture()],nextAfterBatchId:null},project)?.items).toHaveLength(1);
  });
});
