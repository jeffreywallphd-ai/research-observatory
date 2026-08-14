import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { win32, posix } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import {
  PROJECT_LAYOUT_V1,
  PROJECT_MANIFEST_SEMANTIC_RULES_V1,
  decodeProjectLayout,
  decodeProjectManifest,
  portableProjectInventory,
  type ProjectManifest,
} from "./index";

const validManifest: ProjectManifest = {
  schemaVersion: "1.0",
  documentType: "research-observatory-project-manifest",
  projectId: "018f47a2-4d6b-4f78-9f2e-7fb76c86d9a1",
  projectRevision: 0,
  packageFormatVersion: "1.0.0",
  layoutVersion: "1.0",
  lifecycleState: "active",
  applicationCompatibility: {
    minimum: "0.1.0",
    maximumExclusive: "1.0.0",
  },
  databaseProfile: "sqlite-wal-v1",
  objectFormat: "encrypted-content-addressed-v1",
  createdAt: "2026-08-13T00:00:00Z",
  modifiedAt: "2026-08-13T00:00:00Z",
};

describe("project package contract", () => {
  it("decodes the exact non-sensitive manifest and denies unknown or path-bearing fields", () => {
    const fixturePath = fileURLToPath(new URL("./fixtures/valid-project-manifest.v1.json", import.meta.url));
    const invalidPath = fileURLToPath(new URL("./fixtures/invalid-project-manifest-extra-path.json", import.meta.url));
    expect(decodeProjectManifest(JSON.parse(readFileSync(fixturePath, "utf8")))).toEqual(validManifest);
    expect(decodeProjectManifest(JSON.parse(readFileSync(invalidPath, "utf8")))).toBeNull();
    expect(decodeProjectManifest(validManifest)).toEqual(validManifest);
    expect(decodeProjectManifest({ ...validManifest, absolutePath: "C:\\private\\study" })).toBeNull();
    expect(decodeProjectManifest({ ...validManifest, credential: "secret" })).toBeNull();
    expect(
      decodeProjectManifest({
        ...validManifest,
        applicationCompatibility: { minimum: "1.0.0", maximumExclusive: "0.1.0" },
      }),
    ).toBeNull();
    expect(decodeProjectManifest({ ...validManifest, projectRevision: 9_007_199_254_740_992 })).toBeNull();
    expect(decodeProjectManifest({ ...validManifest, modifiedAt: "2026-08-12T23:59:59Z" })).toBeNull();
    expect(
      decodeProjectManifest({
        ...validManifest,
        createdAt: "2026-08-13T00:00:00+00:00",
        modifiedAt: "2026-08-13T00:00:00+00:00",
      }),
    ).toBeNull();
  });

  it("binds cross-field validation to the exact portable semantic-rule document", () => {
    const path = fileURLToPath(new URL("./project-manifest.semantic-rules.json", import.meta.url));
    expect(JSON.parse(readFileSync(path, "utf8"))).toEqual(PROJECT_MANIFEST_SEMANTIC_RULES_V1);
  });

  it("binds the executable layout to the exact governed JSON document", () => {
    const path = fileURLToPath(new URL("./project-layout.v1.json", import.meta.url));
    const bytes = readFileSync(path);
    const document: unknown = JSON.parse(bytes.toString("utf8"));
    expect(decodeProjectLayout(document)).toEqual(PROJECT_LAYOUT_V1);
    expect(Object.isFrozen(PROJECT_LAYOUT_V1)).toBe(true);
    expect(PROJECT_LAYOUT_V1.entries.every(Object.isFrozen)).toBe(true);
    expect(createHash("sha256").update(bytes).digest("hex")).toMatch(/^[0-9a-f]{64}$/);

    const hostile = structuredClone(PROJECT_LAYOUT_V1) as unknown as { entries: Array<{ relativePath: string }> };
    hostile.entries[0]!.relativePath = "C:\\private\\project.sqlite3";
    expect(decodeProjectLayout(hostile)).toBeNull();
  });

  it("uses only relocatable project-relative paths under Windows and POSIX roots", () => {
    for (const entry of PROJECT_LAYOUT_V1.entries) {
      expect(win32.isAbsolute(entry.relativePath)).toBe(false);
      expect(posix.isAbsolute(entry.relativePath)).toBe(false);
      expect(entry.relativePath.split("/")).not.toContain("..");
      expect(win32.resolve("D:\\research\\alpha", entry.relativePath)).toContain("D:\\research\\alpha");
      expect(posix.resolve("/srv/research/alpha", entry.relativePath)).toContain("/srv/research/alpha");
    }
  });

  it("exports authoritative project content while excluding every transient or rebuildable class", () => {
    const inventory = portableProjectInventory();
    expect(inventory).toEqual([
      "project.ro.json",
      "state/project.sqlite3",
      "objects",
      "config",
      "exports",
    ]);
    expect(inventory).not.toContain("indexes");
    expect(inventory).not.toContain("cache");
    expect(inventory).not.toContain("models");
    expect(inventory).not.toContain("logs");
    expect(inventory).not.toContain(".locks");
    expect(inventory).not.toContain(".tmp");
  });
});
