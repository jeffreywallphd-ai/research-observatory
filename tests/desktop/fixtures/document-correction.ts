// Authored synthetic wire values for decoder/component tests only.
import { sourceAnchorFixture } from "./anchor-contract";
import { decodeSourceAnchor } from "../../../apps/desktop/src/app/sourceAnchors";
export const correctionIdentity=(n: number): string=>`00000000-0000-7000-8000-${n.toString(16).padStart(12,"0")}`;
export const correctionSource={...decodeSourceAnchor(sourceAnchorFixture(),"00000000-0000-7000-8000-000000000001","00000000-0000-7000-8000-000000000003")!.target.source,format:"plain-text" as const};
export const correctionRevision=correctionIdentity(903), correctionNode=correctionIdentity(904);
export function correctionPageFixture() {
  return {schemaVersion:"1.0",projectId:correctionSource.projectId,source:correctionSource,documentId:correctionSource.documentId,revisionId:correctionRevision,currentRevisionId:correctionRevision,
    acceptedBy:correctionIdentity(900),acceptedAt:"2026-10-10T00:00:00.000Z",machineRevisionId:correctionRevision,attachmentId:correctionSource.attachmentId,jobId:correctionIdentity(905),structureSha256:"a".repeat(64),
    nodes:[{nodeId:correctionNode,parentId:null,order:0,kind:"paragraph",expectedNodeSha256:"b".repeat(64),preview:"SYNTHETIC <script>inert</script> 📚 correction text",label:null as string | null,textStart:0,textEnd:47,
      locator:{kind:"unavailable",reason:"format-has-no-pages"},referenceId:null,expectedReferenceSha256:null,state:"accepted"}],
    previewNodes:[],nextOffset:null,draft:null,drafts:[],acceptedLabels:[],acceptedReferenceMatches:[],acceptedDecision:null,scholarlyVerification:"unverified"};
}
export function correctionDraftFixture() {
  return {record:{schemaVersion:"1.0",documentType:"document-correction-draft",correctionVersion:"document-correction-1",projectId:correctionSource.projectId,draftId:correctionIdentity(906),revisionId:correctionIdentity(907),previousDraftRevisionId:null,
    source:correctionSource,patch:{schemaVersion:"1.0",baseRevisionId:correctionRevision,expectedStructureSha256:"a".repeat(64),operations:[{op:"relabel",nodeId:correctionNode,expectedNodeSha256:"b".repeat(64),label:"SYNTHETIC human label"}]},rationale:"SYNTHETIC rationale",authoredBy:correctionIdentity(900),authoredActorType:"human",authoredAt:"2026-10-10T00:00:00.000Z",intentRevisionId:correctionIdentity(908),intentSha256:"c".repeat(64),policySha256:"d".repeat(64),commandId:correctionIdentity(909),commandKind:"save",commandSha256:"e".repeat(64),previewSha256:"f".repeat(64),state:"draft"},confirmationSha256:"2".repeat(64)};
}
export function correctionQualityFixture() {
  const structure={state:"unknown",basis:"retained-parser-observation",observedCount:null,expectedCount:null,missingCount:null}, count={state:"unknown",basis:"retained-parser-observation",count:null};
  const confidence={state:"unknown",reportedCount:null,unknownCount:null,notReportedCount:null,notApplicableCount:null,unavailableCount:null,lowReportedCount:null,triageThreshold:0.8};
  return {schemaVersion:"1.0",source:correctionSource,producer:{parserId:"native",version:"1",kind:"native",inputFormats:["plain-text"],configurationVersion:"1",configurationSha256:"a".repeat(64),assets:[]},selectionSha256:"a".repeat(64),inputSha256:"b".repeat(64),jobId:correctionIdentity(905),attemptId:correctionIdentity(910),activityVersion:"document-parse-1",jobState:"succeeded",diagnosticCode:null,resultId:correctionIdentity(911),resultRevisionId:correctionIdentity(912),resultSha256:"c".repeat(64),
    assessment:{schemaVersion:"1.0",definitionVersion:"parsing-quality-definitions-1",ruleVersion:"parsing-quality-triage-1",availability:"available",dimensions:{textCoverage:{...structure,ratio:null},pageTextCoverage:{...structure,state:"not-applicable",ratio:null},encoding:count,readingOrder:{state:"reported-order",warningCount:0,basis:"retained-parser-observation"},sections:structure,references:structure,expectedBlocks:structure,
      anchorCoverage:{...structure,basis:"nonempty-text-node-locators",ambiguousCount:null,parserObservation:{state:"unknown",value:null}},unresolvedReferences:count,extractionConfidence:confidence,tableCellConfidence:confidence,parserTableCellConfidence:confidence,tableGeometry:count,parserWarnings:{state:"not-reported",count:null,informationCount:null,warningCount:null,errorCount:null,codes:[],codesTruncated:false}},reviewRequired:false,reviewReasons:[],humanInspectionAvailable:true,scholarlyVerification:"unverified"}};
}
