import { describe, expect, it } from "vitest";
import { decodeCorrectionPage, decodeCorrectionDraft, decodeCorrectionQuality } from "./documentCorrections";
import { correctionSource, correctionRevision, correctionIdentity, correctionPageFixture, correctionDraftFixture, correctionQualityFixture } from "../../../../tests/desktop/fixtures/document-correction";
describe("protected correction selectors and bounded observations",()=> {
  it("keeps original text, unknown quality and explicit human drafts separate",()=> {
    expect(decodeCorrectionPage(correctionPageFixture(),correctionSource.projectId,correctionRevision)?.nodes[0]?.preview).toContain("<script>");
    expect(decodeCorrectionDraft(correctionDraftFixture(),correctionSource.projectId)?.record.state).toBe("draft");
    expect(decodeCorrectionQuality(correctionQualityFixture(),correctionSource.projectId,correctionIdentity(905))?.assessment.dimensions["sections"]?.state).toBe("unknown");
  });
  it("rejects swapped source, base, duplicate elements, extra actor authority and enlarged previews",()=> {
    const cases=[
      (p: ReturnType<typeof correctionPageFixture>)=> {p.source={...p.source,projectId:correctionIdentity(77)};},
      (p: ReturnType<typeof correctionPageFixture>)=> {p.revisionId=correctionIdentity(88);},
      (p: ReturnType<typeof correctionPageFixture>)=> {p.nodes.push({...p.nodes[0]!});},
      (p: ReturnType<typeof correctionPageFixture>)=> {Object.assign(p,{actorId:correctionIdentity(77)});},
      (p: ReturnType<typeof correctionPageFixture>)=> {p.nodes[0]!.preview="📚".repeat(161);},
    ];
    for(const mutate of cases) {const p=correctionPageFixture();mutate(p);expect(decodeCorrectionPage(p,correctionSource.projectId,correctionRevision)).toBeNull();}
    const d=correctionDraftFixture();d.record.patch.operations[0]!.expectedNodeSha256="invalid";expect(decodeCorrectionDraft(d,correctionSource.projectId)).toBeNull();
  });
  it("never evaluates untrusted getters or coercion and rejects nested additions",()=> {
    let called=false;const p=correctionPageFixture();Object.defineProperty(p,"nodes",{get:()=> {called=true;return [];}});
    expect(decodeCorrectionPage(p,correctionSource.projectId,correctionRevision)).toBeNull();expect(called).toBe(false);
    const q=correctionQualityFixture();Object.assign(q.assessment.dimensions.sections,{inventedProbability:0.99});
    expect(decodeCorrectionQuality(q,correctionSource.projectId,correctionIdentity(905))).toBeNull();
    const d=correctionDraftFixture();Object.defineProperty(d.record.patch.operations[0],"op",{get:()=> {called=true;return "relabel";}});
    expect(decodeCorrectionDraft(d,correctionSource.projectId)).toBeNull();expect(called).toBe(false);
  });
});
