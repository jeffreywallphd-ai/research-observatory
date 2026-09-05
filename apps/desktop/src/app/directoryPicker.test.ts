import { afterEach, describe, expect, it, vi } from "vitest";

import {
  chooseProjectDirectory,
  decodeDefaultProjectParent,
  decodeDirectorySelection,
  defaultProjectParent,
  projectDirectoryName,
  projectDestination,
} from "./directoryPicker";

const native = vi.hoisted(() => vi.fn());
vi.mock("@tauri-apps/api/core", () => ({ invoke: native }));
afterEach(() => { vi.unstubAllGlobals(); native.mockReset(); });

describe("bounded folder selection and destination", () => {
  it("derives a bounded stable Core-compatible leaf without altering the parent", () => {
    const fallback = "a1b2c3d4e5f6";
    expect(projectDirectoryName("Study One", fallback)).toBe("study-one");
    expect(projectDirectoryName("  Crème — Study / 2  ", fallback)).toBe("creme-study-2");
    expect(projectDirectoryName("研究", fallback)).toBe("project-a1b2c3d4e5f6");
    expect(projectDirectoryName("研究", fallback)).toBe(projectDirectoryName("研究", fallback));
    expect(projectDirectoryName("", fallback)).toBe("");
    for (const name of ["CON", "Prn", "aux", "NUL", "COM1", "COM9", "LPT1", "lpt9"]) {
      expect(projectDirectoryName(name, fallback)).toBe(`project-${name.toLowerCase()}`);
    }
    for (const name of ["a".repeat(120), "a-".repeat(70), "COM10", "安全研究", "123", "Security"]) {
      expect(projectDirectoryName(name, fallback)).toMatch(/^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$/);
    }
    expect(projectDirectoryName("Security", fallback)).toBe("security");
    expect(projectDestination("C:\\研究 Folder", "study-one")).toBe("C:\\研究 Folder\\study-one");
    expect(projectDestination("C:/Research", "study-one")).toBe("C:/Research/study-one");
    expect(projectDestination("C:\\", "study-one")).toBe("C:\\study-one");
    expect(projectDestination("", "study-one")).toBe("");
    expect(projectDestination("C:/Research", "../escape")).toBe("");
    expect(projectDestination("C:/" + "a".repeat(4090), "study-one")).toBe("");
    expect(() => projectDirectoryName("研究", "../escape")).toThrow();
  });

  it("accepts only exact outcomes and never exposes a path in a failure", () => {
    expect(decodeDirectorySelection({ status: "selected", path: "C:\\研究 Folder" }))
      .toEqual({ status: "selected", path: "C:\\研究 Folder" });
    expect(decodeDefaultProjectParent({ status: "available", path: "C:/Research" }))
      .toEqual({ status: "available", path: "C:/Research" });
    for (const status of ["cancelled", "unavailable", "failed"]) {
      expect(decodeDirectorySelection({ status })).toEqual({ status });
      expect(decodeDirectorySelection({ status, path: "C:/Private" })).toBeNull();
    }
    for (const path of ["relative", "C:relative", "\\\\server\\share", "\\\\?\\C:\\Folder", "C:/../escape",
      "C:/folder/./child", "C:/folder:stream", "C:/bad\u0000", "C:/bad\u007f", "C:/bad\u0085", "C:/bad\ud800", "C:/" + "a".repeat(4096)]) {
      expect(decodeDirectorySelection({ status: "selected", path })).toBeNull();
      expect(decodeDefaultProjectParent({ status: "available", path })).toBeNull();
    }
    for (const value of [null, [], "selected", { status: "selected" }, { status: "future" },
      { status: "selected", path: "C:/Research", extra: true },
      new Proxy({}, { ownKeys: () => { throw Error("private"); } })]) {
      expect(decodeDirectorySelection(value)).toBeNull();
    }
    expect(decodeDefaultProjectParent({ status: "selected", path: "C:/Research" })).toBeNull();
    expect(decodeDefaultProjectParent({ status: "unavailable", path: "C:/Private" })).toBeNull();
  });

  it("uses only narrow native commands and an argument-free default lookup", async () => {
    vi.stubGlobal("window", { __TAURI_INTERNALS__: {} });
    native.mockResolvedValueOnce({ status: "available", path: "C:/Research" });
    expect(await defaultProjectParent()).toEqual({ status: "available", path: "C:/Research" });
    expect(native).toHaveBeenNthCalledWith(1, "default_project_parent");
    native.mockResolvedValueOnce({ status: "selected", path: "C:/Research" });
    const request = { purpose: "create-parent", previousLocation: "C:/Research" } as const;
    expect(await chooseProjectDirectory(request)).toEqual({ status: "selected", path: "C:/Research" });
    expect(native).toHaveBeenNthCalledWith(2, "choose_project_directory", { request });
    native.mockRejectedValueOnce(new Error("Bearer private C:/private"));
    expect(await chooseProjectDirectory({ purpose: "open-project" })).toEqual({ status: "failed" });
    expect(native.mock.calls.every(([command]) => command !== "core_api_request")).toBe(true);
  });

  it("retains single admission until a cancelled native waiter actually completes", async () => {
    vi.stubGlobal("window", { __TAURI_INTERNALS__: {} });
    let release!: (value: unknown) => void;
    native.mockImplementationOnce(() => new Promise((resolve) => { release = resolve; }));
    const owner = new AbortController();
    const pending = chooseProjectDirectory({ purpose: "create-parent" }, owner.signal);
    owner.abort();
    expect(await chooseProjectDirectory({ purpose: "open-project" })).toEqual({ status: "unavailable" });
    expect(native).toHaveBeenCalledTimes(1);
    release({ status: "selected", path: "C:/Private" });
    expect(await pending).toEqual({ status: "cancelled" });
    native.mockResolvedValueOnce({ status: "cancelled" });
    expect(await chooseProjectDirectory({ purpose: "open-project" })).toEqual({ status: "cancelled" });
    expect(native).toHaveBeenCalledTimes(2);
  });

  it("rejects invalid requests before native calls and does not invent a browser default", async () => {
    expect(await defaultProjectParent()).toEqual({ status: "unavailable" });
    expect(await chooseProjectDirectory({ purpose: "open-project" })).toEqual({ status: "unavailable" });
    vi.stubGlobal("window", { __TAURI_INTERNALS__: {} });
    for (const request of [{ purpose: "future" }, { purpose: "open-project", previousLocation: null },
      { purpose: "create-parent", previousLocation: "relative" }, { purpose: "open-project", path: "C:/Research" }]) {
      expect(await chooseProjectDirectory(request as Parameters<typeof chooseProjectDirectory>[0])).toEqual({ status: "failed" });
    }
    const owner = new AbortController(); owner.abort();
    expect(await chooseProjectDirectory({ purpose: "open-project" }, owner.signal)).toEqual({ status: "cancelled" });
    expect(native).not.toHaveBeenCalled();
  });
});
