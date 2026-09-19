import { afterEach, describe, expect, it, vi } from "vitest";
import { chooseImportSource, decodeImportOutcome } from "./importIntake";

const native = vi.hoisted(() => vi.fn());
vi.mock("@tauri-apps/api/core", () => ({ invoke: native }));
afterEach(() => { vi.unstubAllGlobals(); native.mockReset(); });
const project = { root: "C:/Research/synthetic", projectId: "01900000-0000-4000-8000-000000000001" };
const options = { formatName: "csv", encoding: "utf-8", localUseConfirmed: true } as const;
const result = () => ({ status: "prepared", sourceName: "synthetic.csv", preview: {
  previewId: "01900000-0000-7000-8000-000000000001", state: "source-sealed", byteLength: 10, chunkCount: 1,
  jobId: "01900000-0000-7000-8000-000000000002", jobState: "runnable",
} });

describe("native import intake", () => {
  it("requires explicit local rights and a native host; never invents a browser file input", async () => {
    expect(await chooseImportSource(project, options)).toEqual({ status: "unavailable" });
    vi.stubGlobal("window", { __TAURI_INTERNALS__: {} });
    expect(await chooseImportSource(project, { ...options, localUseConfirmed: false })).toEqual({ status: "failed" });
    expect(native).not.toHaveBeenCalled();
  });
  it("sends only explicit local rights and project context without a file path", async () => {
    vi.stubGlobal("window", { __TAURI_INTERNALS__: {} });
    native.mockResolvedValueOnce(result());
    expect(await chooseImportSource(project, options)).toMatchObject({ status: "prepared", preview: { sourceName: "synthetic.csv" } });
    const [command, { request }] = native.mock.calls[0]!;
    expect(command).toBe("import_selected_file");
    expect(request.operationId).toMatch(/^[0-9a-f]{32}$/);
    expect(Object.keys(request).sort()).toEqual(["encoding", "formatName", "operationId", "projectId", "rights", "root"]);
    expect(request.rights.store).toEqual({ value: "permitted", basis: "researcher-confirmed" });
    expect(request.rights.export).toEqual({ value: "unknown", basis: "not-reported" });
  });
  it("cancels the exact native operation and retains admission until its waiter returns", async () => {
    vi.stubGlobal("window", { __TAURI_INTERNALS__: {} });
    native.mockResolvedValue(undefined);
    let release!: (value: unknown) => void;
    native.mockImplementationOnce(() => new Promise((resolve) => { release = resolve; }));
    const owner = new AbortController();
    const pending = chooseImportSource(project, options, owner.signal);
    const operationId = native.mock.calls[0]![1].request.operationId;
    owner.abort();
    expect(native).toHaveBeenLastCalledWith("cancel_import_file", { operationId });
    expect(await chooseImportSource(project, options)).toEqual({ status: "unavailable" });
    release({ status: "cancelled" });
    expect(await pending).toEqual({ status: "cancelled" });
  });
  it("rejects unknown fields, paths and accessor responses without disclosing their text", () => {
    expect(decodeImportOutcome(result(), options)).not.toBeNull();
    expect(decodeImportOutcome({ ...result(), sourceName: "C:/private.csv" }, options)).toBeNull();
    expect(decodeImportOutcome({ status: "failed", error: "private" }, options)).toBeNull();
    let invoked = false;
    expect(decodeImportOutcome({ get status() { invoked = true; return "failed"; } }, options)).toBeNull();
    expect(invoked).toBe(false);
  });
});
