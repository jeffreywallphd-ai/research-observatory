import { afterEach, describe, expect, it, vi } from "vitest";
import { configureSource, decodeConfigurationOutcome, configurationMessage } from "./sourceConfiguration";
const native = vi.hoisted(() => vi.fn());
vi.mock("@tauri-apps/api/core", () => ({ invoke: native }));
afterEach(() => { vi.unstubAllGlobals(); native.mockReset(); });
const project = { root: "C:/Research/synthetic", projectId: "01900000-0000-4000-8000-000000000001" };

describe("private native connector configuration", () => {
  it("sends only project/provider identity, never credential values", async () => {
    vi.stubGlobal("window", { __TAURI_INTERNALS__: {} });
    native.mockResolvedValueOnce({ status: "saved" });
    expect(await configureSource(project, "unpaywall")).toEqual({ status: "saved" });
    const [command, { request }] = native.mock.calls[0]!;
    expect(command).toBe("configure_scholarly_source");
    expect(Object.keys(request).sort()).toEqual(["operationId", "projectId", "providerId", "root"]);
    expect(request.operationId).toMatch(/^[0-9a-f]{32}$/);
    expect(configurationMessage({ status: "saved" })).toContain("No connection was tested");
  });
  it("cancels the exact operation and retains exclusion until its result", async () => {
    vi.stubGlobal("window", { __TAURI_INTERNALS__: {} });
    native.mockResolvedValue(undefined);
    let release!: (value: unknown) => void;
    native.mockImplementationOnce(() => new Promise((resolve) => { release = resolve; }));
    const owner = new AbortController();
    const pending = configureSource(project, "openalex", owner.signal);
    const operationId = native.mock.calls[0]![1].request.operationId;
    owner.abort();
    expect(native).toHaveBeenLastCalledWith("cancel_scholarly_source_configuration", { operationId });
    expect(await configureSource(project, "crossref")).toEqual({ status: "unavailable" });
    release({ status: "save-unconfirmed" });
    expect(await pending).toEqual({ status: "save-unconfirmed" });
  });
  it("never relabels unknown post-dispatch results as cancelled or unsaved", async () => {
    vi.stubGlobal("window", { __TAURI_INTERNALS__: {} });
    native.mockRejectedValueOnce(new Error("synthetic private exception"));
    expect(await configureSource(project, "semantic-scholar")).toEqual({ status: "save-unconfirmed" });
    expect(decodeConfigurationOutcome({ status: "saved", key: "synthetic" })).toBeNull();
    let read = false;
    expect(decodeConfigurationOutcome({ get status() { read = true; return "saved"; } })).toBeNull();
    expect(read).toBe(false);
  });
  it("requires a native host and performs no call for prior cancellation", async () => {
    expect(await configureSource(project, "unpaywall")).toEqual({ status: "unavailable" });
    const owner = new AbortController(); owner.abort();
    expect(await configureSource(project, "unpaywall", owner.signal)).toEqual({ status: "cancelled" });
    expect(native).not.toHaveBeenCalled();
  });
});
