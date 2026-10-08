import React from "react";
import { createRoot } from "react-dom/client";
import { SourceAnchorReader } from "../../../apps/desktop/src/app/SourceAnchorReader";
import { decodeReaderOutline, decodeSourceAnchor, type SourceAnchor } from "../../../apps/desktop/src/app/sourceAnchors";
import "../../../packages/ui-tokens/index.css";
import "../../../packages/ui-components/src/styles.css";
import "../../../apps/desktop/src/app.css";

declare global {
  interface Window {
    __ANCHOR_FIXTURE__: { anchor: SourceAnchor; outline: unknown; anchorIds: readonly string[] };
    __ANCHOR_READER_TEST__: { mount: (active: boolean) => void; holdRead: boolean; releaseRead: (() => void) | null;
      denyRead: boolean; calls: readonly { command: string; request: unknown }[]; returns: number };
  }
}
const fixture = window.__ANCHOR_FIXTURE__;
const anchor = decodeSourceAnchor(fixture.anchor, fixture.anchor.target.projectId, fixture.anchor.target.revisionId);
if (!anchor || !decodeReaderOutline(fixture.outline, anchor.target.projectId, anchor.target.revisionId)) throw new Error("Invalid synthetic Core fixture");
const calls: { command: string; request: unknown }[] = [];
const rootElement = document.getElementById("root");
if (!rootElement) throw new Error("Missing reader fixture root");
const root = createRoot(rootElement);
const state = window.__ANCHOR_READER_TEST__ = {
  mount(active: boolean): void {
    root.render(<SourceAnchorReader source={anchor.target.source} revisionId={anchor.target.revisionId} active={active}
      announce={() => undefined} onReturn={() => { state.returns += 1; }} />);
  }, holdRead: false, releaseRead: null as (() => void) | null, denyRead: false, calls, returns: 0,
};
// Declared Tauri invoke double. Responses were produced by the real Core
// native/session/encryption composition; this fixture does not emulate OS authority.
Object.assign(window, { __TAURI_INTERNALS__: { invoke: async (command: string, args: { request: Record<string, unknown> }) => {
  calls.push({ command, request: args.request });
  if (command === "document_reader_outline") return fixture.outline;
  if (command === "document_reader_anchor_list") return { anchorIds: fixture.anchorIds };
  if (command === "document_reader_anchor_read" || command === "document_reader_anchor_create") {
    if (state.holdRead) await new Promise<void>((resolve) => { state.releaseRead = resolve; });
    return state.denyRead ? null : anchor;
  }
  return null;
} } });
state.mount(true);
