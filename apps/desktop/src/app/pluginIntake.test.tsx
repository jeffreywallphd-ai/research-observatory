import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { ProjectProjection } from "@research-observatory/contracts/core-api";
import { grantMatchesPackage, PluginReviewPane, samePackageIdentity } from "./PluginReviewPane";
import { choosePluginPackage, decodePluginIntakeOutcome, type ReviewedPluginPackage } from "./pluginIntake";
import { decodeGrantState, decodeTrustState, disablePlugin, enablePlugin, removePluginPublisherTrust } from "./pluginActions";

const project: ProjectProjection = { schemaVersion: "1.0", projectId: "01900000-0000-4000-8000-000000000001", displayName: "Synthetic", templateId: "theory-synthesis", lifecycleState: "active", root: "C:/Research/synthetic", open: true, revision: 1, accessMode: "read-write", compatibilityState: "compatible", packageFormatVersion: "1.0.0", backupRequiredBeforeRepair: false, recoveryAction: "none", deleteConfirmation: "delete:01900000-0000-4000-8000-000000000001" };
const digest = (letter: string): string => "sha256:" + letter.repeat(64);
const destination = { scheme: "https" as const, host: "repository.example.invalid", port: 443, pathTemplate: "/records/{repository_id}" };
const reviewed: ReviewedPluginPackage = {
  packageToken: "a".repeat(64), expiresAt: "2099-01-01T00:00:00.000Z",
  review: { pluginId: "example.repository", pluginVersion: "1.0.0", publisherKeyId: "example.publisher", sourceDisplayName: "Example repository",
    manifestSha256: digest("b"), packageSha256: digest("c"), signatureSha256: digest("d"), permissions: ["provider-network"],
    destinations: [destination], operations: ["repository-metadata"], dataClasses: ["public-metadata"], credentialScopes: [],
    resourceProfile: { committedMemoryMiB: 256, maxJobsPerProject: 1, wallTimeSeconds: 60 }, trustStatus: "untrusted", grantStatus: "disabled", runtimeStatus: "unavailable" },
};

describe("native connector package review", () => {
  it("accepts only a bounded identity-bearing native review and never sends a renderer path", async () => {
    const transport = vi.fn(async (_command: string, _arguments?: Record<string, unknown>) => ({ status: "reviewed", ...reviewed }));
    const result = await choosePluginPackage(project, undefined, transport);
    expect(result).toEqual({ status: "reviewed", package: reviewed });
    expect(transport).toHaveBeenCalledTimes(1);
    expect(transport.mock.calls[0]![0]).toBe("select_connector_package");
    const request = transport.mock.calls[0]![1] as { request: Record<string, unknown> };
    expect(Object.keys(request.request).sort()).toEqual(["operationId", "projectId", "root"]);
    expect(request.request.root).toBe(project.root);
    for (const forged of [
      { status: "reviewed", ...reviewed, path: "C:/secret" },
      { status: "reviewed", ...reviewed, packageToken: "bad" },
      { status: "reviewed", ...reviewed, review: { ...reviewed.review, runtimeStatus: "ready", destinations: [{ ...destination, scheme: "file" }] } },
      { status: "reviewed", ...reviewed, review: { ...reviewed.review, packageSha256: digest("e"), rawSecret: "fixture" } },
    ]) expect(decodePluginIntakeOutcome(forged)).toBeNull();
  });

  it("shows exact permission scope and an unavailable worker without an enabled action", () => {
    const html = renderToStaticMarkup(<PluginReviewPane project={project} announce={() => undefined} active initialPackage={reviewed} />);
    for (const phrase of ["Review connector access", reviewed.review.packageSha256, "repository-metadata", "repository.example.invalid", "Signed isolated runtime unavailable", "The signed isolated worker is not installed and verified", "No credential scope requested"]) expect(html).toContain(phrase);
    expect(html).toMatch(/disabled=""[^>]*aria-describedby="connector-enable-help"[^>]*>Enable for this project/);
    expect(html).not.toContain(project.root);
    expect(html).not.toContain("Connected");
  });

  it("binds current trust and project grant before sending an enable request", async () => {
    const trust = decodeTrustState({ publisherKeyId: "example.publisher", status: "active", revision: 1, publicKeySha256: digest("f") });
    expect(decodeTrustState({ publisherKeyId: "example.publisher", status: "active", revision: 1, publicKeySha256: null })).toBeNull();
    const grant = decodeGrantState({ pluginId: "example.repository", status: "disabled", revision: null, packageSha256: null, manifestSha256: null, permissions: [], destinations: [] });
    expect(trust && grant).toBeTruthy();
    const transport = vi.fn(async () => ({ status: "ok", value: { status: "enabled" } }));
    expect(await enablePlugin(project, reviewed, trust!, grant!, transport)).toEqual({ status: "unavailable" });
    expect(transport).not.toHaveBeenCalled();
  });

  it("passes only identity hints to native human-decision actions", async () => {
    const trust = decodeTrustState({ publisherKeyId: "example.publisher", status: "active", revision: 2, publicKeySha256: digest("f") })!;
    const disabled = decodeGrantState({ pluginId: "example.repository", status: "disabled", revision: 3,
      packageSha256: null, manifestSha256: null, permissions: [], destinations: [] })!;
    const selected = { ...reviewed, review: { ...reviewed.review, trustStatus: "active", runtimeStatus: "ready" as const } };
    const transport = vi.fn(async () => ({ status: "ok", value: {} }));
    expect(await enablePlugin(project, selected, trust, disabled, transport)).toEqual({ status: "ok", value: {} });
    expect(transport).toHaveBeenLastCalledWith("connector_plugin_action", { request: {
      root: project.root, projectId: project.projectId, kind: "grant-enable", packageToken: selected.packageToken,
    } });
    const enabled = decodeGrantState({ pluginId: "example.repository", status: "enabled", revision: 4,
      packageSha256: reviewed.review.packageSha256, manifestSha256: reviewed.review.manifestSha256,
      permissions: ["provider-network"], destinations: [destination] })!;
    await disablePlugin(project, enabled, transport);
    expect(transport).toHaveBeenLastCalledWith("connector_plugin_action", { request: {
      root: project.root, projectId: project.projectId, kind: "grant-revoke", pluginId: enabled.pluginId,
    } });
    await removePluginPublisherTrust(project, trust, transport);
    expect(transport).toHaveBeenLastCalledWith("connector_plugin_action", { request: {
      root: project.root, projectId: project.projectId, kind: "trust-revoke", publisherKeyId: trust.publisherKeyId,
    } });
  });

  it("keeps manifest, signature and publisher identity bound when package file bytes match", () => {
    expect(samePackageIdentity(reviewed, reviewed)).toBe(true);
    for (const change of [
      { manifestSha256: digest("e") }, { signatureSha256: digest("e") },
      { publisherKeyId: "other.publisher" }, { pluginId: "other.repository" },
    ]) expect(samePackageIdentity(reviewed, { ...reviewed, review: { ...reviewed.review, ...change } })).toBe(false);
    const grant = decodeGrantState({ pluginId: reviewed.review.pluginId, status: "enabled", revision: 1,
      packageSha256: reviewed.review.packageSha256, manifestSha256: reviewed.review.manifestSha256,
      permissions: [], destinations: [] });
    expect(grantMatchesPackage(grant, reviewed)).toBe(true);
    expect(grantMatchesPackage(grant, { ...reviewed, review: { ...reviewed.review, manifestSha256: digest("e") } })).toBe(false);
  });

  it("discards a late package token after selection is cancelled", async () => {
    let finish: ((value: unknown) => void) | undefined;
    const transport = vi.fn((command: string, _arguments?: Record<string, unknown>): Promise<unknown> =>
      command === "select_connector_package" ? new Promise((resolve) => { finish = resolve; }) : Promise.resolve({ status: "ok", value: {} }));
    const controller = new AbortController();
    const result = choosePluginPackage(project, controller.signal, transport);
    controller.abort();
    finish?.({ status: "reviewed", ...reviewed });
    expect(await result).toEqual({ status: "cancelled" });
    const discard = transport.mock.calls.find(([command]) => command === "connector_plugin_action");
    expect(discard?.[1]).toEqual({ request: { root: project.root, projectId: project.projectId, kind: "discard", packageToken: reviewed.packageToken } });
  });
});
