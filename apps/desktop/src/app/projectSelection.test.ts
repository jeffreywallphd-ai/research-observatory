import { describe, expect, it } from "vitest";

import {
  PROJECT_RECENTS_STORAGE_KEY,
  forgetRecentProject,
  loadProjectPreferences,
  orderRecentProjects,
  projectIntent,
  saveProjectPreferences,
  type RecentProject,
} from "./projectSelection";

const PROJECTS: readonly RecentProject[] = [
  {
    id: "project-zeta",
    title: "Zeta",
    useCase: "Theory synthesis",
    lastOpenedAt: "2026-08-01T12:00:00Z",
    availability: "available",
  },
  {
    id: "project-alpha",
    title: "Alpha",
    useCase: "Critical inquiry",
    lastOpenedAt: "2026-08-02T12:00:00Z",
    availability: "missing",
  },
];
const ZETA = PROJECTS[0]!;
const ALPHA = PROJECTS[1]!;

class MemoryStorage {
  readonly values = new Map<string, string>();

  getItem(key: string): string | null {
    return this.values.get(key) ?? null;
  }

  setItem(key: string, value: string): void {
    this.values.set(key, value);
  }
}

describe("project selection", () => {
  it("orders recent projects deterministically and applies removals", () => {
    const preferences = { schemaVersion: 1 as const, removedProjectIds: ["project-alpha"] };
    expect(orderRecentProjects(PROJECTS, preferences).map(({ id }) => id)).toEqual(["project-zeta"]);
    expect(orderRecentProjects([...PROJECTS].reverse(), { schemaVersion: 1, removedProjectIds: [] })).toEqual([
      ALPHA,
      ZETA,
    ]);
  });

  it("rejects ambiguous or malformed catalog entries", () => {
    expect(() => orderRecentProjects([...PROJECTS, ZETA], { schemaVersion: 1, removedProjectIds: [] })).toThrow(
      "duplicate recent project id",
    );
    expect(() =>
      orderRecentProjects([{ ...ZETA, id: "../replacement" }], {
        schemaVersion: 1,
        removedProjectIds: [],
      }),
    ).toThrow("invalid recent project id");
  });

  it("loads a strict versioned preference record and recovers without rewriting malformed state", () => {
    const storage = new MemoryStorage();
    expect(loadProjectPreferences(storage)).toEqual({
      preferences: { schemaVersion: 1, removedProjectIds: [] },
      recovery: null,
    });

    storage.values.set(PROJECT_RECENTS_STORAGE_KEY, '{"schemaVersion":2,"removedProjectIds":[]}');
    expect(loadProjectPreferences(storage)).toEqual({
      preferences: { schemaVersion: 1, removedProjectIds: [] },
      recovery: "unsupported-or-invalid-project-recents",
    });
    expect(storage.values.get(PROJECT_RECENTS_STORAGE_KEY)).toContain('"schemaVersion":2');
  });

  it("persists idempotent removals in canonical order", () => {
    const storage = new MemoryStorage();
    const preferences = forgetRecentProject(
      forgetRecentProject({ schemaVersion: 1, removedProjectIds: ["project-zeta"] }, "project-alpha"),
      "project-alpha",
    );
    expect(preferences.removedProjectIds).toEqual(["project-alpha", "project-zeta"]);
    expect(saveProjectPreferences(storage, preferences)).toBeNull();
    expect(storage.values.get(PROJECT_RECENTS_STORAGE_KEY)).toBe(
      '{"schemaVersion":1,"removedProjectIds":["project-alpha","project-zeta"]}',
    );
  });

  it("requires explicit repair for a missing project and never creates a replacement", () => {
    expect(projectIntent(ZETA, "open")).toEqual({ type: "open-existing", projectId: "project-zeta" });
    expect(projectIntent(ALPHA, "locate")).toEqual({
      type: "locate-existing",
      projectId: "project-alpha",
    });
    expect(projectIntent(ALPHA, "remove")).toEqual({
      type: "remove-recent",
      projectId: "project-alpha",
    });
    expect(() => projectIntent(ALPHA, "open")).toThrow("missing project requires explicit repair");
    expect(() => projectIntent(ZETA, "locate")).toThrow("available project does not require repair");
  });
});
