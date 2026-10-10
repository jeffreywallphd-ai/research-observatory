// Authored wire values for comparison/UI tests. No parser or authority proof.
import { correctionIdentity as identity, correctionQualityFixture, correctionSource, correctionRevision, correctionNode } from "./document-correction";
export const reprocessingBatchId=identity(8000), reprocessingBatchRevision=identity(8001), reprocessingItemId=identity(8002);
export function reprocessingBatchFixture() {
  return {schemaVersion:"1.0",projectId:correctionSource.projectId,batchId:reprocessingBatchId,batchRevisionId:reprocessingBatchRevision,state:"active",items:[{itemId:reprocessingItemId,baseRevisionId:correctionRevision,jobId:identity(8003),state:"ready",acceptedRevisionId:null as string | null}]};
}
export function reprocessingPageFixture() {
  return {schemaVersion:"1.0",projectId:correctionSource.projectId,batchId:reprocessingBatchId,batchRevisionId:reprocessingBatchRevision,itemId:reprocessingItemId,baseRevisionId:correctionRevision,currentRevisionId:correctionRevision,
    source:correctionSource,jobId:identity(8003),attemptId:identity(8004),resultId:identity(8005),comparisonRevisionId:identity(8006),candidateRevisionId:identity(8007),planRevisionId:null as string | null,confirmationSha256:null as string | null,
    generation:0,generationCount:1,totalObligations:1,unresolvedCount:1,
    obligations:[{obligationId:"a".repeat(64),originalDraftRevisionId:identity(8008),originalBaseRevisionId:correctionRevision,operationIndex:0,operation:"relabel",oldNodeId:correctionNode,oldNodeSha256:"b".repeat(64),oldPreview:"SYNTHETIC <script>inert</script> 📚 prior",relatedOldNodeId:null,originalReferenceId:null,originalAuthor:identity(8009),originalRationale:"SYNTHETIC original human rationale"}],
    candidateNodes:[{nodeId:identity(8010),parentId:null,order:0,kind:"paragraph",preview:"SYNTHETIC <script>inert</script> 📚 candidate",nodeSha256:"c".repeat(64),referenceId:null}],
    differences:[{kind:"node",oldId:correctionNode,newId:identity(8010),state:"modified",oldPreview:"SYNTHETIC <script>inert</script> prior",newPreview:"SYNTHETIC <script>inert</script> candidate",oldLocator:{kind:"unavailable",reason:"format-has-no-pages"},newLocator:{kind:"unavailable",reason:"format-has-no-pages"}}],
    differenceCounts:{unchanged:0,moved:0,modified:1,added:0,removed:0,ambiguous:0,unresolvable:0},anchorCandidates:[],anchorCounts:{unchanged:0,moved:0,modified:0,added:0,removed:0,ambiguous:0,unresolvable:0},nextOffset:null as number | null,
    oldQuality:correctionQualityFixture().assessment,newQuality:correctionQualityFixture().assessment,impact:{graphSha256:"d".repeat(64),affectedCount:1,informationalCount:1,legacyUnreportedCount:0,state:"prospective-rechecked-at-acceptance"},state:"review",scholarlyVerification:"unverified"};
}
export function reprocessingAcceptedFixture() {
  return {schemaVersion:"1.0",projectId:correctionSource.projectId,batchId:reprocessingBatchId,batchRevisionId:reprocessingBatchRevision,itemId:reprocessingItemId,previousRevisionId:correctionRevision,revisionId:identity(8011),machineRevisionId:identity(8012),impactRunId:identity(8013),impactState:"completed",impactCheckpointSha256:"e".repeat(64),processedItems:1,totalItems:1,scholarlyVerification:"unverified"};
}
