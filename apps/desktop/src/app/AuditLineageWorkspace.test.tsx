import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import type { ProjectProjection, ProvenanceLineagePage } from "@research-observatory/contracts/core-api";

import {
  AuditLineageWorkspace,
  lineageAvailability,
  lineageNodeRole,
  provenanceLineageRequest,
} from "./AuditLineageWorkspace";

const project: ProjectProjection = {
  schemaVersion: "1.0",
  projectId: "6f93073a-5af0-47ef-b9cf-d5027e0ded99",
  displayName: "Local study",
  templateId: "theory-synthesis",
  lifecycleState: "active",
  root: "C:/Research/study-one",
  open: true,
  revision: 4,
  accessMode: "read-write",
  compatibilityState: "compatible",
  packageFormatVersion: "1.0.0",
  backupRequiredBeforeRepair: false,
  recoveryAction: "none",
  deleteConfirmation: "delete:6f93073a-5af0-47ef-b9cf-d5027e0ded99",
};

const lineage: ProvenanceLineagePage = {
  schemaVersion: "1.0",
  revisionId: "01890f47-eae3-7cc0-98c4-dc0c0c073981",
  direction: "ancestors",
  items: [
    {
      revisionId: "01890f47-eae3-7cc0-98c4-dc0c0c073981",
      entityId: "01890f47-eae3-7cc0-88c4-dc0c0c073982",
      entityKind: "synthesis.sentence",
      depth: 0,
      eventId: "01890f47-eae3-7cc0-98c4-dc0c0c073983",
      eventType: "org.research-observatory.synthesis.created.v1",
      activityId: "01890f47-eae3-7cc0-98c4-dc0c0c073984",
      activityType: "synthesis.insert",
      activityStatus: "succeeded",
      configurationId: "model.synthesis-prompt",
      configurationVersion: "3.2.0",
      configurationHash: `sha256:${"1".repeat(64)}`,
      agentId: "01890f47-eae3-7cc0-98c4-dc0c0c073985",
      agentType: "model",
      agentRole: "synthesis.writer",
      occurredAt: "2026-08-29T19:00:00Z",
    },
    {
      revisionId: "01890f47-eae3-7cc0-98c4-dc0c0c073986",
      entityId: "01890f47-eae3-7cc0-88c4-dc0c0c073982",
      entityKind: "synthesis.sentence",
      depth: 1,
      eventId: "01890f47-eae3-7cc0-98c4-dc0c0c073987",
      eventType: "org.research-observatory.synthesis.invalidated.v1",
      activityId: "01890f47-eae3-7cc0-98c4-dc0c0c073988",
      activityType: "synthesis.revise",
      activityStatus: "succeeded",
      configurationId: "decision.revision",
      configurationVersion: "1.0.0",
      configurationHash: `sha256:${"2".repeat(64)}`,
      agentId: "01890f47-eae3-7cc0-98c4-dc0c0c073989",
      agentType: "human",
      agentRole: "claim.reviewer",
      occurredAt: "2026-08-29T18:00:00Z",
    },
    {
      revisionId: "01890f47-eae3-7cc0-98c4-dc0c0c07398a",
      entityId: "01890f47-eae3-7cc0-88c4-dc0c0c07398b",
      entityKind: "evidence.passage",
      depth: 1,
      eventId: "01890f47-eae3-7cc0-98c4-dc0c0c07398c",
      eventType: "org.research-observatory.evidence.recorded.v1",
      activityId: "01890f47-eae3-7cc0-98c4-dc0c0c07398d",
      activityType: "evidence.extract",
      activityStatus: "succeeded",
      configurationId: "extract.evidence-passage",
      configurationVersion: "2.1.0",
      configurationHash: `sha256:${"3".repeat(64)}`,
      agentId: "01890f47-eae3-7cc0-98c4-dc0c0c07398e",
      agentType: "software",
      agentRole: "evidence.extractor",
      occurredAt: "2026-08-29T17:00:00Z",
    },
  ],
  missingRevisionIds: ["01890f47-eae3-7cc0-98c4-dc0c0c07398f"],
  nextCursor: 3,
  integrityState: "integrity-review",
  legacyEventCount: 1,
};

describe("audit and lineage workspace", () => {
  it("keeps read-only inspection available while failing closed for unavailable projects", () => {
    expect(lineageAvailability(null)).toEqual({ available: false, reason: "Open a local project to trace lineage." });
    expect(lineageAvailability({ ...project, accessMode: "read-only" })).toEqual({ available: true, reason: null });
    expect(lineageAvailability({ ...project, open: false, accessMode: "closed" })).toEqual({
      available: false,
      reason: "Open this project before tracing lineage.",
    });
  });

  it("builds one bounded exact-revision request after workspace navigation", () => {
    expect(provenanceLineageRequest(project, lineage.revisionId, "ancestors", 0)).toEqual({
      root: project.root,
      revisionId: lineage.revisionId,
      direction: "ancestors",
      cursor: 0,
      pageSize: 50,
      maxDepth: 8,
    });
    expect(() => provenanceLineageRequest(project, "not-a-revision", "ancestors", 0)).toThrow(
      "RO-CORE-REQUEST-INVALID",
    );
  });

  it("keeps selected, superseded, and alternate source records visible with integrity context", () => {
    const root = lineage.items[0]!;
    expect(lineageNodeRole(root, root)).toBe("Selected output");
    expect(lineageNodeRole(lineage.items[1]!, root)).toBe("Superseded revision");
    expect(lineageNodeRole(lineage.items[2]!, root)).toBe("Source or alternate input");

    const html = renderToStaticMarkup(
      <AuditLineageWorkspace
        project={project}
        announce={() => undefined}
        initialRevisionId={lineage.revisionId}
        initialTrace={lineage}
      />,
    );

    expect(html).toContain('data-audit-lineage-workspace="true"');
    expect(html).toContain("Exact output revision ID");
    expect(html).toContain("Trace lineage");
    expect(html).toContain("Selected output");
    expect(html).toContain("Superseded revision");
    expect(html).toContain("Source or alternate input");
    expect(html).toContain("Stale or invalidated");
    expect(html).toContain("Integrity review required");
    expect(html).toContain(lineage.missingRevisionIds[0]);
    expect(html).toContain("1 legacy event");
    expect(html).toContain("not hidden model rationale or chain-of-thought");
    expect(html).toContain("model.synthesis-prompt");
    expect(html).toContain("3.2.0");
    for (const node of lineage.items) {
      expect(html).toContain(node.revisionId);
      expect(html).toContain(node.eventId);
      expect(html).toContain(node.activityId);
    }
  });

  it("renders a recovery-oriented empty state without offering a trace against no project", () => {
    const html = renderToStaticMarkup(<AuditLineageWorkspace project={null} announce={() => undefined} />);
    expect(html).toContain("Open a local project to trace lineage.");
    expect(html).not.toContain('data-trace-lineage="true"');
  });
});
