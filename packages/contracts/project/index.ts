export type ProjectLifecycleState = "active" | "archived" | "trash";

export interface ProjectManifest {
  readonly schemaVersion: "1.0";
  readonly documentType: "research-observatory-project-manifest";
  readonly projectId: string;
  readonly projectRevision: number;
  readonly packageFormatVersion: "1.0.0";
  readonly layoutVersion: "1.0";
  readonly lifecycleState: ProjectLifecycleState;
  readonly applicationCompatibility: {
    readonly minimum: string;
    readonly maximumExclusive: string;
  };
  readonly databaseProfile: "sqlite-wal-v1";
  readonly objectFormat: "encrypted-content-addressed-v1";
  readonly createdAt: string;
  readonly modifiedAt: string;
}

export type ProjectStorageClass =
  | "database"
  | "objects"
  | "indexes"
  | "caches"
  | "models"
  | "configuration"
  | "exports"
  | "logs"
  | "locks"
  | "temporary";

export interface ProjectLayoutEntry {
  readonly storageClass: ProjectStorageClass;
  readonly kind: "file" | "directory";
  readonly relativePath: string;
  readonly authority: "authoritative" | "derived" | "cache" | "operational" | "transient";
  readonly retention: "project-lifetime" | "rebuildable" | "bounded" | "lease-bound" | "operation-scoped";
  readonly backup: "required" | "excluded";
  readonly deletion:
    | "recoverable-project-delete"
    | "rebuildable-delete"
    | "cache-eviction"
    | "retention-expiry"
    | "close-or-stale-recovery"
    | "operation-cleanup";
  readonly portableExport: "include" | "exclude";
}

export interface ProjectLayout {
  readonly schemaVersion: "1.0";
  readonly documentType: "research-observatory-project-layout";
  readonly manifestFile: "project.ro.json";
  readonly entries: readonly ProjectLayoutEntry[];
}

export const PROJECT_MANIFEST_SEMANTIC_RULES_V1 = Object.freeze({
  schemaVersion: "1.0",
  documentType: "research-observatory-project-manifest-semantic-rules",
  rules: Object.freeze([
    Object.freeze({
      ruleId: "application-compatibility-range-ascending",
      operator: "semver-less-than",
      leftPointer: "/applicationCompatibility/minimum",
      rightPointer: "/applicationCompatibility/maximumExclusive",
    }),
    Object.freeze({
      ruleId: "modified-at-not-before-created-at",
      operator: "instant-not-after",
      leftPointer: "/createdAt",
      rightPointer: "/modifiedAt",
    }),
  ]),
} as const);

export const PROJECT_LAYOUT_V1 = {
  schemaVersion: "1.0",
  documentType: "research-observatory-project-layout",
  manifestFile: "project.ro.json",
  entries: [
    { storageClass: "database", kind: "file", relativePath: "state/project.sqlite3", authority: "authoritative", retention: "project-lifetime", backup: "required", deletion: "recoverable-project-delete", portableExport: "include" },
    { storageClass: "objects", kind: "directory", relativePath: "objects", authority: "authoritative", retention: "project-lifetime", backup: "required", deletion: "recoverable-project-delete", portableExport: "include" },
    { storageClass: "indexes", kind: "directory", relativePath: "indexes", authority: "derived", retention: "rebuildable", backup: "excluded", deletion: "rebuildable-delete", portableExport: "exclude" },
    { storageClass: "caches", kind: "directory", relativePath: "cache", authority: "cache", retention: "bounded", backup: "excluded", deletion: "cache-eviction", portableExport: "exclude" },
    { storageClass: "models", kind: "directory", relativePath: "models", authority: "derived", retention: "rebuildable", backup: "excluded", deletion: "rebuildable-delete", portableExport: "exclude" },
    { storageClass: "configuration", kind: "directory", relativePath: "config", authority: "authoritative", retention: "project-lifetime", backup: "required", deletion: "recoverable-project-delete", portableExport: "include" },
    { storageClass: "exports", kind: "directory", relativePath: "exports", authority: "authoritative", retention: "project-lifetime", backup: "required", deletion: "recoverable-project-delete", portableExport: "include" },
    { storageClass: "logs", kind: "directory", relativePath: "logs", authority: "operational", retention: "bounded", backup: "excluded", deletion: "retention-expiry", portableExport: "exclude" },
    { storageClass: "locks", kind: "directory", relativePath: ".locks", authority: "operational", retention: "lease-bound", backup: "excluded", deletion: "close-or-stale-recovery", portableExport: "exclude" },
    { storageClass: "temporary", kind: "directory", relativePath: ".tmp", authority: "transient", retention: "operation-scoped", backup: "excluded", deletion: "operation-cleanup", portableExport: "exclude" },
  ],
} as const satisfies ProjectLayout;

for (const entry of PROJECT_LAYOUT_V1.entries) Object.freeze(entry);
Object.freeze(PROJECT_LAYOUT_V1.entries);
Object.freeze(PROJECT_LAYOUT_V1);

const MANIFEST_KEYS = ["schemaVersion", "documentType", "projectId", "projectRevision", "packageFormatVersion", "layoutVersion", "lifecycleState", "applicationCompatibility", "databaseProfile", "objectFormat", "createdAt", "modifiedAt"] as const;
const COMPATIBILITY_KEYS = ["minimum", "maximumExclusive"] as const;
const PROJECT_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const RELEASE_SEMVER = /^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$/;
const UTC_TIMESTAMP = /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,3}))?Z$/;
const PORTABLE_SEGMENT = /^[A-Za-z0-9._-]+$/;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasExactKeys(value: Record<string, unknown>, expected: readonly string[]): boolean {
  const actual = Object.keys(value).sort();
  return actual.length === expected.length && [...expected].sort().every((key, index) => key === actual[index]);
}

function releaseVersion(value: unknown): readonly [number, number, number] | null {
  if (typeof value !== "string") return null;
  const match = RELEASE_SEMVER.exec(value);
  if (!match) return null;
  const version = [Number(match[1]), Number(match[2]), Number(match[3])] as const;
  return version.every(Number.isSafeInteger) ? version : null;
}

function compareReleaseVersions(left: readonly number[], right: readonly number[]): number {
  for (let index = 0; index < 3; index += 1) {
    const difference = (left[index] ?? 0) - (right[index] ?? 0);
    if (difference !== 0) return difference;
  }
  return 0;
}

function isUtcTimestamp(value: unknown): value is string {
  if (typeof value !== "string") return false;
  const match = UTC_TIMESTAMP.exec(value);
  if (!match) return false;
  const expected = `${match[1]}.${(match[2] ?? "").padEnd(3, "0")}Z`;
  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp) && new Date(timestamp).toISOString() === expected;
}

function deepExactEqual(left: unknown, right: unknown): boolean {
  if (Object.is(left, right)) return true;
  if (Array.isArray(left) || Array.isArray(right)) {
    return Array.isArray(left) && Array.isArray(right) && left.length === right.length && left.every((item, index) => deepExactEqual(item, right[index]));
  }
  if (!isRecord(left) || !isRecord(right)) return false;
  const leftKeys = Object.keys(left).sort();
  const rightKeys = Object.keys(right).sort();
  return leftKeys.length === rightKeys.length && leftKeys.every((key, index) => key === rightKeys[index] && deepExactEqual(left[key], right[key]));
}

export function isPortableProjectRelativePath(value: unknown): value is string {
  if (typeof value !== "string" || value.length === 0 || value.length > 160 || value.includes("\\")) return false;
  if (value.startsWith("/") || /^[A-Za-z]:/.test(value)) return false;
  const segments = value.split("/");
  return segments.every((segment) => segment !== "" && segment !== "." && segment !== ".." && PORTABLE_SEGMENT.test(segment));
}

export function projectManifestSemanticErrors(manifest: ProjectManifest): readonly string[] {
  const minimum = releaseVersion(manifest.applicationCompatibility.minimum);
  const maximum = releaseVersion(manifest.applicationCompatibility.maximumExclusive);
  const errors: string[] = [];
  if (!minimum || !maximum || compareReleaseVersions(minimum, maximum) >= 0) {
    errors.push(PROJECT_MANIFEST_SEMANTIC_RULES_V1.rules[0]!.ruleId);
  }
  if (Date.parse(manifest.createdAt) > Date.parse(manifest.modifiedAt)) {
    errors.push(PROJECT_MANIFEST_SEMANTIC_RULES_V1.rules[1]!.ruleId);
  }
  return errors;
}

export function decodeProjectManifest(value: unknown): ProjectManifest | null {
  try {
    if (!isRecord(value) || !hasExactKeys(value, MANIFEST_KEYS)) return null;
    const compatibility = value.applicationCompatibility;
    if (!isRecord(compatibility) || !hasExactKeys(compatibility, COMPATIBILITY_KEYS)) return null;
    const minimum = releaseVersion(compatibility.minimum);
    const maximum = releaseVersion(compatibility.maximumExclusive);
    if (!minimum || !maximum) return null;
    if (!isUtcTimestamp(value.createdAt) || !isUtcTimestamp(value.modifiedAt)) return null;
    if (
      value.schemaVersion !== "1.0" ||
      value.documentType !== "research-observatory-project-manifest" ||
      typeof value.projectId !== "string" ||
      !PROJECT_ID.test(value.projectId) ||
      !Number.isSafeInteger(value.projectRevision) ||
      (value.projectRevision as number) < 0 ||
      value.packageFormatVersion !== "1.0.0" ||
      value.layoutVersion !== "1.0" ||
      !(["active", "archived", "trash"] as const).includes(value.lifecycleState as ProjectLifecycleState) ||
      value.databaseProfile !== "sqlite-wal-v1" ||
      value.objectFormat !== "encrypted-content-addressed-v1"
    ) return null;
    const manifest: ProjectManifest = {
      schemaVersion: "1.0",
      documentType: "research-observatory-project-manifest",
      projectId: value.projectId,
      projectRevision: value.projectRevision as number,
      packageFormatVersion: "1.0.0",
      layoutVersion: "1.0",
      lifecycleState: value.lifecycleState as ProjectLifecycleState,
      applicationCompatibility: { minimum: compatibility.minimum as string, maximumExclusive: compatibility.maximumExclusive as string },
      databaseProfile: "sqlite-wal-v1",
      objectFormat: "encrypted-content-addressed-v1",
      createdAt: value.createdAt,
      modifiedAt: value.modifiedAt,
    };
    return projectManifestSemanticErrors(manifest).length === 0 ? manifest : null;
  } catch {
    return null;
  }
}

export function decodeProjectLayout(value: unknown): ProjectLayout | null {
  try {
    if (!isRecord(value) || !hasExactKeys(value, ["schemaVersion", "documentType", "manifestFile", "entries"])) return null;
    if (!deepExactEqual(value, PROJECT_LAYOUT_V1)) return null;
    return PROJECT_LAYOUT_V1;
  } catch {
    return null;
  }
}

export function portableProjectInventory(): readonly string[] {
  return [PROJECT_LAYOUT_V1.manifestFile, ...PROJECT_LAYOUT_V1.entries.filter((entry) => entry.portableExport === "include").map((entry) => entry.relativePath)];
}
