import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { ProjectProjection } from "@research-observatory/contracts/core-api";
import type { CorpusReportDrillPage, CorpusReportSnapshot } from "@research-observatory/contracts/corpus-reports";
import {
  CorpusCanvasWorkspace, ReportPathStatus, corpusReportCommandId, createCorpusReportWithRecovery,
  drillMatchesSelection, focusCorpusRecoveryControl, readCorpusReportRecovery,
  rememberVerifiedCorpusReportSnapshot, recoveryActionForInterruptedOperation,
  sourceBoundaryComparison, suspendedCorpusReportState,
} from "./CorpusCanvasWorkspace";
import { implementedWorkspaceForStage } from "./workflowNavigationModel";

const project: ProjectProjection = {
  schemaVersion: "1.0", projectId: "01900000-0000-4000-8000-000000000001",
  displayName: "Synthetic", templateId: "theory-synthesis", lifecycleState: "active",
  root: "C:/Research/synthetic", open: true, revision: 1, accessMode: "read-write",
  compatibilityState: "compatible", packageFormatVersion: "1.0.0",
  backupRequiredBeforeRepair: false, recoveryAction: "none",
  deleteConfirmation: "delete:01900000-0000-4000-8000-000000000001",
};
const snapshot = {
  schemaVersion: "1.0",
  contractVersion: "1.0.0",
  documentType: "research-observatory-corpus-report-snapshot",
  snapshotId: "01900000-0000-7000-8000-000000000010",
  projectId: project.projectId,
  intentRevisionId: "01900000-0000-7000-8000-000000000011",
  protocolRevisionId: "01900000-0000-7000-8000-000000000018",
  ruleVersion: "corpus-report/1.0.0",
  createdAt: "2026-09-24T12:00:00.000Z",
  memberCount: 2,
  discoveryPathCount: 3,
  unattributedDiscoveryPathCount: 0,
  membersSha256: "a".repeat(64),
  sourceContributions: [{ sourceKey: "import:01900000-0000-7000-8000-000000000019", itemCount: 1, discoveryPathCount: 1 }, { sourceKey: "connector:openalex", itemCount: 2, discoveryPathCount: 2 }],
  sourceOverlaps: [{ leftSourceKey: "import:01900000-0000-7000-8000-000000000019", rightSourceKey: "connector:openalex", itemCount: 1, discoveryPathPairCount: 1 }],
  routeContributions: [{ route: "import-member", itemCount: 1, discoveryPathCount: 1 }, { route: "connector-record", itemCount: 2, discoveryPathCount: 2 }, { route: "citation", itemCount: 0, discoveryPathCount: 0 }, { route: "recommendation", itemCount: 0, discoveryPathCount: 0 }, { route: "manual", itemCount: 0, discoveryPathCount: 0 }],
  routeOverlaps: [{ leftRoute: "import-member", rightRoute: "connector-record", itemCount: 1, discoveryPathPairCount: 1 }],
  coverage: [
    { dimension: "identifier", known: 1, notReported: 1, unknown: 0, unavailable: 0 },
    { dimension: "year", known: 1, notReported: 0, unknown: 1, unavailable: 0 },
    { dimension: "venue", known: 0, notReported: 1, unknown: 1, unavailable: 0 },
    { dimension: "language", known: 0, notReported: 0, unknown: 1, unavailable: 1 },
    { dimension: "discipline", known: 0, notReported: 0, unknown: 2, unavailable: 0 },
    { dimension: "oa", known: 0, notReported: 0, unknown: 1, unavailable: 1 },
    { dimension: "full-text", known: 0, notReported: 0, unknown: 1, unavailable: 1 },
  ],
  membershipCounts: [{ membership: "candidate", itemCount: 2 }, { membership: "included", itemCount: 0 }, { membership: "excluded", itemCount: 0 }, { membership: "withdrawn", itemCount: 0 }],
  duplicateLinkedItemCount: 1,
  unattributedItemCount: 0,
  valueDistributions: [
    { dimension: "year", buckets: [{ value: "2024", itemCount: 1 }], otherKnownCount: 0, truncated: false },
    { dimension: "venue", buckets: [], otherKnownCount: 0, truncated: false },
    { dimension: "language", buckets: [], otherKnownCount: 0, truncated: false },
    { dimension: "discipline", buckets: [], otherKnownCount: 0, truncated: false },
    { dimension: "oa", buckets: [], otherKnownCount: 0, truncated: false },
    { dimension: "full-text", buckets: [], otherKnownCount: 0, truncated: false },
  ],
} as const satisfies CorpusReportSnapshot;
const allFilter = {
  kind: "all", membership: null, sourceKey: null, route: null, leftSourceKey: null, rightSourceKey: null,
  leftRoute: null, rightRoute: null, dimension: null, state: null, value: null,
} as const;
const drill = {
  schemaVersion: "1.0",
  contractVersion: "1.0.0",
  documentType: "research-observatory-corpus-report-drill-page",
  snapshotId: snapshot.snapshotId,
  projectId: project.projectId,
  filter: allFilter,
  members: [{
    schemaVersion: "1.0",
    contractVersion: "1.0.0",
    documentType: "research-observatory-corpus-report-member",
    snapshotId: snapshot.snapshotId,
    projectId: project.projectId,
    itemId: "01900000-0000-7000-8000-000000000012",
    itemRevisionId: "01900000-0000-7000-8000-000000000013",
    workId: "01900000-0000-7000-8000-000000000014",
    workRevisionId: "01900000-0000-7000-8000-000000000015",
    membership: "candidate",
    duplicateOfItemId: null,
    displayLabel: "<script>untrusted title</script>",
    paths: [{ pathId: "01900000-0000-7000-8000-000000000016", sourceRevisionId: "01900000-0000-7000-8000-000000000017", contextRevisionId: "01900000-0000-7000-8000-000000000020", sourceKey: "connector:openalex", route: "connector-record", metadataAssertionStatus: "retained", reportInspectStatus: "allowed", rightsPolicyRevisionId: "01900000-0000-7000-8000-000000000021", rightsExpiresAt: null, sourceCopyAvailability: "unknown" }],
    fields: [
      { dimension: "identifier", state: "known", value: "10.1/example", witnessRevisionId: "01900000-0000-7000-8000-000000000017" },
      { dimension: "year", state: "known", value: "2024", witnessRevisionId: "01900000-0000-7000-8000-000000000017" },
      { dimension: "venue", state: "not-reported", value: null, witnessRevisionId: null },
      { dimension: "language", state: "unknown", value: null, witnessRevisionId: null },
      { dimension: "discipline", state: "unknown", value: null, witnessRevisionId: null },
      { dimension: "oa", state: "unknown", value: null, witnessRevisionId: null },
      { dimension: "full-text", state: "unknown", value: null, witnessRevisionId: null },
    ],
  }],
  nextCursor: "opaque-next",
  total: 2,
} as const satisfies CorpusReportDrillPage;

describe("Corpus Canvas", () => {
  it("maps the approved page into the existing guided workflow", () => {
    expect(implementedWorkspaceForStage({ pageContractId: "corpus-canvas.html" })).toBe("corpus");
  });

  it("does not retain or render report data without an open compatible project", () => {
    const absent = renderToStaticMarkup(<CorpusCanvasWorkspace project={null} announce={() => undefined} />);
    expect(absent).toContain("No project open");
    const closed = renderToStaticMarkup(<CorpusCanvasWorkspace project={{ ...project, open: false }} announce={() => undefined} />);
    expect(closed).toContain("No project open");
    const incompatible = renderToStaticMarkup(<CorpusCanvasWorkspace project={{ ...project, compatibilityState: "newer-unsupported" }} announce={() => undefined} />);
    expect(incompatible).toContain("Corpus report unavailable");
    expect(incompatible).not.toContain(project.root);
  });

  it("starts without invented clusters, overlap percentages, or source values", () => {
    const html = renderToStaticMarkup(<CorpusCanvasWorkspace project={project} announce={() => undefined} />);
    for (const label of ["Corpus Canvas", "Discovery paths", "Selected cluster", "Selected records", "Corpus reflexivity", "Source overlap", "Boundary sensitivity", "Missingness risks"]) {
      expect(html).toContain(label);
    }
    expect(html).toContain("Semantic clusters unavailable");
    expect(html).toContain("Boundary comparison unavailable");
    expect(html).not.toContain("Creative cognition");
    expect(html).not.toContain("3,842");
    expect(html).not.toContain("58%");
    expect(html).not.toContain(project.root);
  });

  it("renders canonical source and missingness counts from one saved snapshot without copying illustrative values", () => {
    const html = renderToStaticMarkup(<CorpusCanvasWorkspace project={project} announce={() => undefined} initialSnapshot={snapshot} initialDrill={drill} />);
    expect(html).toContain("2 distinct canonical item revisions");
    expect(html).toContain("import:01900000");
    expect(html).toContain("connector:openalex");
    expect(html).toContain("Items shared by source pairs");
    expect(html).toContain("Not reported");
    expect(html).toContain("Unavailable");
    expect(html).toContain("Inspect Year value 2024: 1 item");
    expect(html).toContain("Inspect all known records");
    expect(html).toContain("Items shared by discovery route pairs");
    expect(html).toContain("Discovery paths</dt><dd>3");
    expect(html).toContain("Discovery path pairs");
    expect(html).toContain("Inspect candidate items: 2");
    expect(html).toContain("Inspect duplicate-linked items: 1");
    expect(html).toContain("Inspect items with at least one unattributed source path: 0");
    expect(html).toContain("01900000-0000-7000-8000-000000000010");
    expect(html).toContain("&lt;script&gt;untrusted title&lt;/script&gt;");
    expect(html).not.toContain("<script>untrusted title</script>");
    expect(html).not.toContain("58%");
  });

  it("qualifies per-path metadata authority without treating it as full-text copy permission", () => {
    const retained = drill.members[0]!.paths[0]!;
    const allowed = renderToStaticMarkup(<ReportPathStatus path={retained} />);
    expect(allowed).toContain("Metadata assertion: retained");
    expect(allowed).toContain("Report-metadata inspection: allowed under policy");
    expect(allowed).toContain(retained.rightsPolicyRevisionId!);
    expect(allowed).toContain("Source full-text copy: unknown");
    const noExternal = { ...retained, route: "manual" as const, sourceKey: null,
      metadataAssertionStatus: "no-external-assertion" as const, reportInspectStatus: "unassessed" as const,
      rightsPolicyRevisionId: null, rightsExpiresAt: null };
    const unknown = renderToStaticMarkup(<ReportPathStatus path={noExternal} />);
    expect(unknown).toContain("no external assertion");
    expect(unknown).toContain("unassessed for this path");
    expect(unknown).not.toContain("allowed under policy");
  });

  it("compares attributed source boundaries inside one saved snapshot without inventing a counterfactual", () => {
    const first = snapshot.sourceContributions[0]!.sourceKey;
    const second = snapshot.sourceContributions[1]!.sourceKey;
    expect(sourceBoundaryComparison(snapshot, first, second)).toEqual({
      firstCount: 1, secondCount: 2, sharedCount: 1,
      firstPathCount: 1, secondPathCount: 2, sharedPathPairCount: 1,
    });
    expect(sourceBoundaryComparison(snapshot, first, null)).toEqual({
      firstCount: 2, secondCount: 1, sharedCount: null,
      firstPathCount: 3, secondPathCount: 1, sharedPathPairCount: null,
    });
    expect(sourceBoundaryComparison(snapshot, first, "connector:missing")).toBeNull();
    expect(sourceBoundaryComparison(snapshot, first, first)).toBeNull();
    const withoutOverlap = { ...snapshot, sourceOverlaps: [] };
    expect(sourceBoundaryComparison(withoutOverlap, first, second)?.sharedCount).toBe(0);
    expect(sourceBoundaryComparison(withoutOverlap, first, second)?.sharedPathPairCount).toBe(0);
    const soleSource = { ...snapshot, sourceContributions: [snapshot.sourceContributions[0]!], sourceOverlaps: [] };
    const singleHtml = renderToStaticMarkup(<CorpusCanvasWorkspace project={project} announce={() => undefined} initialSnapshot={soleSource} />);
    expect(singleHtml).toContain("All canonical items");
    expect(singleHtml).toContain("Inspect second boundary");
    expect(singleHtml).not.toContain("Items in both source boundaries");
    const html = renderToStaticMarkup(<CorpusCanvasWorkspace project={project} announce={() => undefined} initialSnapshot={snapshot} initialDrill={drill} />);
    expect(html).toContain("Source-boundary comparison");
    expect(html).toContain("Items in both source boundaries");
    expect(html).toContain("Within-item path pairs across boundaries");
    expect(html).toContain("Inspect shared items");
    expect(html).toContain(snapshot.snapshotId);
    expect(html).toContain("does not model a new search, eligibility rule, or cluster change");
    expect(html).not.toContain("Boundary comparison unavailable");
  });

  it("does not attach a drill page from another snapshot or filter", () => {
    expect(drillMatchesSelection(snapshot, allFilter, drill)).toBe(true);
    expect(drillMatchesSelection(snapshot, { ...allFilter, kind: "source", sourceKey: "connector:openalex" }, drill)).toBe(false);
    expect(drillMatchesSelection(snapshot, { ...allFilter, kind: "membership", membership: "candidate" }, drill)).toBe(false);
    expect(drillMatchesSelection(snapshot, allFilter, { ...drill, snapshotId: "01900000-0000-7000-8000-000000000099" })).toBe(false);
    expect(drillMatchesSelection(snapshot, allFilter, { ...drill, projectId: "01900000-0000-4000-8000-000000000099" })).toBe(false);
    expect(drillMatchesSelection(snapshot, allFilter, { ...drill, filter: { ...allFilter, sourceKey: "connector:openalex" } })).toBe(false);
    const wrongPage = renderToStaticMarkup(<CorpusCanvasWorkspace project={project} announce={() => undefined} initialSnapshot={snapshot} initialDrill={{ ...drill, snapshotId: "01900000-0000-7000-8000-000000000099" }} />);
    expect(wrongPage).not.toContain("&lt;script&gt;untrusted title&lt;/script&gt;");
    const otherProject = renderToStaticMarkup(<CorpusCanvasWorkspace project={project} announce={() => undefined} initialSnapshot={{ ...snapshot, projectId: "01900000-0000-4000-8000-000000000099" }} initialDrill={drill} />);
    expect(otherProject).not.toContain(snapshot.snapshotId);
    expect(otherProject).toContain("No report selected");
  });

  it("reuses one UUIDv7 command identity for an uncertain creation retry", () => {
    const commandId = corpusReportCommandId(null);
    expect(commandId).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
    expect(corpusReportCommandId(commandId)).toBe(commandId);
  });

  it("keeps report creation disabled for read-only projects without promising saved access", () => {
    const html = renderToStaticMarkup(<CorpusCanvasWorkspace project={{ ...project, accessMode: "read-only" }} announce={() => undefined} />);
    expect(html).toContain("generation requires a writable project");
    expect(html).toContain("Core determines");
    expect(html).toContain("Open saved report");
    expect(html).toMatch(/disabled=\"\"[^>]*>Generate report/);
  });

  it("persists the command before Core call and reuses it after a failed call and remount", async () => {
    const values = new Map<string, string>();
    const storage = {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => { values.set(key, value); },
    };
    let firstCommand = "";
    await expect(createCorpusReportWithRecovery(storage, project, async ({ commandId }) => {
      firstCommand = commandId;
      expect(readCorpusReportRecovery(storage, project).pendingCommandId).toBe(commandId);
      throw new Error("response lost");
    })).rejects.toThrow("response lost");
    const retry = vi.fn(async ({ commandId }: { commandId: string }) => {
      expect(commandId).toBe(firstCommand);
      return snapshot;
    });
    const result = await createCorpusReportWithRecovery(storage, project, retry);
    expect(result.snapshot.snapshotId).toBe(snapshot.snapshotId);
    expect(result.recoverySaved).toBe(true);
    expect(retry).toHaveBeenCalledTimes(1);
    expect(readCorpusReportRecovery(storage, project)).toEqual({
      pendingCommandId: null, lastVerifiedSnapshotId: snapshot.snapshotId,
    });
  });

  it("does not call Core if local recovery cannot be persisted", async () => {
    const storage = {
      getItem: () => null,
      setItem: () => { throw new Error("storage denied"); },
    };
    const create = vi.fn(async () => snapshot);
    await expect(createCorpusReportWithRecovery(storage, project, create)).rejects.toThrow("RO-CORPUS-LOCAL-RECOVERY-UNAVAILABLE");
    expect(create).not.toHaveBeenCalled();
  });

  it("keeps the command pending when Settings suspends an in-flight response", async () => {
    const values = new Map<string, string>();
    const storage = {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => { values.set(key, value); },
    };
    let firstCommand = "";
    const stale = await createCorpusReportWithRecovery(storage, project, async ({ commandId }) => {
      firstCommand = commandId;
      return snapshot;
    }, () => false);
    expect(stale.recoverySaved).toBe(false);
    expect(readCorpusReportRecovery(storage, project).pendingCommandId).toBe(firstCommand);
    expect(readCorpusReportRecovery(storage, project).lastVerifiedSnapshotId).toBeNull();
    const retry = await createCorpusReportWithRecovery(storage, project, async ({ commandId }) => {
      expect(commandId).toBe(firstCommand);
      return snapshot;
    });
    expect(retry.recoverySaved).toBe(true);
    expect(readCorpusReportRecovery(storage, project).pendingCommandId).toBeNull();
  });

  it("retains an uncertain command through unrelated saved inspection and scopes recovery to the exact project", async () => {
    const values = new Map<string, string>();
    const storage = {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => { values.set(key, value); },
    };
    await expect(createCorpusReportWithRecovery(storage, project, async () => { throw new Error("interrupted"); })).rejects.toThrow("interrupted");
    const before = readCorpusReportRecovery(storage, project);
    expect(before.pendingCommandId).toMatch(/-7[0-9a-f]{3}-/);
    expect(rememberVerifiedCorpusReportSnapshot(storage, project, snapshot.snapshotId)).toBe(true);
    expect(readCorpusReportRecovery(storage, project).pendingCommandId).toBe(before.pendingCommandId);
    expect(readCorpusReportRecovery(storage, { ...project, root: "C:/Research/other" }).pendingCommandId).toBeNull();
    expect(readCorpusReportRecovery(storage, { ...project, projectId: "01900000-0000-4000-8000-000000000099" }).pendingCommandId).toBeNull();
    const html = renderToStaticMarkup(<CorpusCanvasWorkspace project={project} announce={() => undefined} recoveryStorage={storage} />);
    expect(html).toContain(`value="${snapshot.snapshotId}"`);
    expect(html).toContain("Retry generation");
    expect(html).toContain("No report selected");
    expect(html).not.toContain("2 distinct canonical item revisions");
  });

  it("maps each Settings-suspended operation to a persistent recovery control", () => {
    expect(recoveryActionForInterruptedOperation("create")).toBe("generate");
    expect(recoveryActionForInterruptedOperation("inspect")).toBe("open");
    expect(recoveryActionForInterruptedOperation("drill")).toBe("open");
    expect(recoveryActionForInterruptedOperation(null)).toBeNull();
    for (const action of ["create", "inspect", "drill"] as const) {
      expect(suspendedCorpusReportState(action)).toEqual({
        reportState: "interrupted", drillState: "idle",
        focus: action === "create" ? "generate" : "open",
      });
    }
    const generateFocus = vi.fn();
    const openFocus = vi.fn();
    expect(focusCorpusRecoveryControl("generate", {
      generate: { disabled: false, focus: generateFocus }, open: { disabled: false, focus: openFocus }, storage: null,
    })).toBe(true);
    expect(generateFocus).toHaveBeenCalledTimes(1);
    expect(focusCorpusRecoveryControl("open", {
      generate: { disabled: true, focus: generateFocus }, open: { disabled: false, focus: openFocus }, storage: null,
    })).toBe(true);
    expect(openFocus).toHaveBeenCalledTimes(1);
    expect(focusCorpusRecoveryControl("generate", {
      generate: { disabled: true, focus: generateFocus }, open: { disabled: false, focus: openFocus }, storage: null,
    })).toBe(false);
    const html = renderToStaticMarkup(<CorpusCanvasWorkspace project={project} announce={() => undefined} />);
    expect(html).toContain('data-corpus-recovery="generate"');
    expect(html).toContain('data-corpus-recovery="open"');
  });
});
