import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Button, Notification, StatusBadge } from "@research-observatory/ui-components";
import { decodeAnchorIds, decodeAnchorResolution, codepointRangeToUtf16, pageRegionPixels,
  type SourceAnchorResolution } from "./sourceAnchors";
import { viewerSourcesMatch, type DocumentViewerAnchorPort, type ViewerMainAdmission, type ViewerMetadata } from "./documentViewer";
import type { SourceAnchorPort } from "./sourceAnchorsNative";
import type { ViewerDeepLink } from "./viewerDeepLinks";

interface Props {
  readonly metadata: ViewerMetadata;
  readonly revisionId: string;
  readonly initial: ViewerDeepLink | null;
  readonly main: ViewerMainAdmission;
  readonly reserveCore: () => () => void;
  readonly port: DocumentViewerAnchorPort;
  readonly anchors: SourceAnchorPort;
  readonly overlay: HTMLElement | null;
  readonly viewport: { readonly width: number; readonly height: number; readonly page: number };
  readonly onPage: (page: number) => void;
  readonly onRemember?: ((link: ViewerDeepLink) => boolean) | undefined;
  readonly onReturn: () => void;
  readonly onFailure: (code: string) => void;
  readonly onActionAnchor?: (anchorId: string) => void;
}
interface HeldContext { readonly number: number; readonly value: SourceAnchorResolution; readonly release: () => void }

/** Only two protected contexts remain visible; the rest of the link is opaque IDs. */
export function ViewerAnchorContexts(props: Props): ReactNode {
  const [ids, setIds] = useState<readonly string[]>([]), [more, setMore] = useState(false);
  const [windowStart, setWindowStart] = useState(0), [contexts, setContexts] = useState<readonly HeldContext[]>([]);
  const [busy, setBusy] = useState(false), [status, setStatus] = useState("Loading saved source anchors…");
  const held = useRef<readonly HeldContext[]>([]), generation = useRef(0), live = useRef(false);
  const focus = useRef<HTMLHeadingElement>(null);
  const projectId = props.metadata.source.projectId;
  const initial = props.initial?.selector.normalizedRevisionId === props.revisionId ? props.initial : null;
  const initialKey = initial?.anchorIds.join(",") ?? "";
  function clear(): void { for (const item of held.current) item.release(); held.current = []; setContexts([]); }

  useEffect(() => {
    live.current = true; const ticket = ++generation.current;
    clear(); setIds([]); setMore(false); setWindowStart(0); setBusy(true);
    const current = (): boolean => live.current && generation.current === ticket;
    if (initial) { setIds(initial.anchorIds); setBusy(false); setStatus("Checking exact linked anchors…"); }
    else void props.anchors.list(projectId, props.revisionId).then(value => {
      if (!current()) return;
      const selected = decodeAnchorIds({ anchorIds: value });
      setIds(selected ?? []); setMore(selected?.length === 100); setBusy(false);
      setStatus(selected === null ? "Saved anchors are unavailable or no longer permitted."
        : selected.length ? "Choose a numbered anchor to inspect its exact source context." : "No saved anchors for this accepted revision.");
    }).catch(() => { if (current()) { setBusy(false); setStatus("Saved anchors could not be confirmed."); } });
    return () => { live.current = false; generation.current += 1; for (const item of held.current) item.release(); held.current = []; };
  }, [projectId, props.revisionId, props.metadata, props.anchors, initialKey]);

  useEffect(() => {
    if (!ids.length) return;
    const ticket = ++generation.current;
    const current = (): boolean => live.current && generation.current === ticket;
    clear(); setBusy(true); setStatus("Checking exact source contexts and current permission…");
    void (async () => {
      const loaded: HeldContext[] = [];
      try {
        for (let n = windowStart; n < Math.min(windowStart + 2, ids.length); n++) {
          let releaseContext = (): void => undefined, releaseCore = (): void => undefined, terminal = true;
          try {
            releaseContext = props.main.context(); releaseCore = props.reserveCore(); terminal = false;
            const result = await props.port.resolve(projectId, { attachmentId: props.metadata.source.attachmentId,
              documentRevisionId: props.metadata.source.documentRevisionId, normalizedRevisionId: props.revisionId }, ids[n]!);
            terminal = true;
            const value = decodeAnchorResolution(result, projectId, props.revisionId, ids[n]!);
            if (!current() || !value || !viewerSourcesMatch(value.source, props.metadata.source)) {
              releaseContext();
              if (current()) setStatus("An exact anchor is unavailable or no longer permitted. No different passage was substituted.");
              continue;
            }
            loaded.push({ number: n + 1, value, release: releaseContext });
            // Charge retained context until its visible window is evicted.
          } catch (error) {
            // Fixed resource/never-issued denial is known; all other issued errors
            // are physically ambiguous and retain Core and main admission.
            const code = error instanceof Error ? error.message : "viewer-owned-read-drain-pending";
            terminal = terminal || code === "viewer-resource-limit" || code === "viewer-source-unavailable";
            if (terminal) releaseContext();
            if (current()) {
              setStatus(code === "viewer-resource-limit" ? "This anchor context exceeds the local Viewer limit. Its original and revision remain retained."
                : "Anchor access could not be confirmed. Return to source review.");
              if (!terminal) props.onFailure("viewer-owned-read-drain-pending");
            }
            break;
          } finally { if (terminal) releaseCore(); }
          if (!current()) break;
        }
        if (!current()) { for (const item of loaded) item.release(); return; }
        held.current = loaded; setContexts(loaded); setBusy(false);
        if (loaded.length) {
          setStatus(`Showing ${loaded.length} exact revision context${loaded.length === 1 ? "" : "s"}. Extraction remains unverified.`);
          const target = loaded[0]!.value.target?.pageRegion;
          if (target) props.onPage(target.pageNumber);
          const saved = props.onRemember?.({ schemaVersion: "1.0", projectId, selector: {
            attachmentId: props.metadata.source.attachmentId, documentRevisionId: props.metadata.source.documentRevisionId,
            normalizedRevisionId: props.revisionId }, anchorIds: ids });
          if (saved === false) setStatus("Source contexts displayed. This Reader link could not be saved for restart.");
          focus.current?.focus();
        }
      } catch { if (current()) { setBusy(false); setStatus("Anchor context could not be confirmed."); } }
    })();
    return () => { generation.current += 1; };
  }, [ids, windowStart, props.revisionId, props.metadata, props.main, props.port]);

  async function moreAnchors(): Promise<void> {
    const ticket = generation.current; setBusy(true);
    const next = decodeAnchorIds({ anchorIds: await props.anchors.list(projectId, props.revisionId, ids.at(-1)).catch(() => null) });
    if (!live.current || ticket !== generation.current) return;
    setBusy(false);
    // Replace rather than accumulating unbounded ID pages.
    if (next) { setIds(next); setWindowStart(0); setMore(next.length === 100); }
    else setStatus("The next saved anchor page could not be confirmed.");
  }
  function geometry(value: SourceAnchorResolution): ReturnType<typeof pageRegionPixels> | null {
    const region = value.target?.pageRegion, view = props.viewport;
    if (!region || region.pageNumber !== view.page || view.width <= 0 || view.height <= 0) return null;
    const rotated = region.rotation === 90 || region.rotation === 270;
    const ratio = rotated ? region.sourceHeight / region.sourceWidth : region.sourceWidth / region.sourceHeight;
    if (Math.abs(view.width / view.height - ratio) > 0.01) return null;
    return pageRegionPixels(region, 100, 100);
  }
  return <section className="ro-stack ro-wrap-anywhere" aria-label="Source anchor contexts" aria-busy={busy}>
    <h2 ref={focus} tabIndex={-1}>Selected passages</h2><p role="status">{status}</p>
    <ol className="source-anchor-list">{ids.map((id, n) => <li key={id}><Button disabled={busy} aria-pressed={n >= windowStart && n < windowStart + 2}
      onClick={() => setWindowStart(Math.floor(n / 2) * 2)}>Anchor {n + 1} · {id}</Button></li>)}</ol>
    {more ? <Button disabled={busy} onClick={() => void moreAnchors()}>More saved anchors</Button> : null}
    {contexts.map(({ number, value }) => {
      const context = value.target?.context;
      const range = context ? codepointRangeToUtf16(context.text, context.highlight) : null;
      const region = value.target?.pageRegion;
      const coordinates = geometry(value);
      return <section className="viewer-anchor-context" key={value.anchorId} aria-label={`Anchor ${number} context`}>
        <h3>Anchor {number} · {value.metadata.displayLabel}</h3>
        {context && range ? <p className="anchor-passage-text">{context.text.slice(0, range.start)}<mark aria-label={`Anchor ${number} selected source passage`}>{context.text.slice(range.start, range.end)}</mark>{context.text.slice(range.end)}</p> : null}
        {value.status === "missing" || value.status === "broken" ? <Notification tone="warning" title={`Anchor ${value.status}`}>
          Its exact accepted revision is retained. Return to the selected Work/version to review this source and select a new anchor; the historical anchor remains unchanged.
          <Button onClick={props.onReturn}>Review source for missing anchor</Button></Notification> : null}
        <dl><dt>Accepted revision</dt><dd>{value.metadata.revisionId}</dd><dt>Accepted at</dt><dd>{value.metadata.acceptedAt}</dd>
          <dt>Processing status</dt><dd>{value.status} · extraction unverified</dd><dt>Confidence</dt><dd>{value.target?.confidence.state === "reported" ? value.target.confidence.value : value.target?.confidence.state.replaceAll("-", " ") ?? "Unavailable"}</dd></dl>
        {region ? <Button onClick={() => props.onPage(region.pageNumber)}>Go to anchor {number} on page {region.pageNumber}</Button> : null}
        <p>{coordinates ? "Numbered page region available; select its equivalent anchor control for context." : "Structural/text fallback: page geometry is unavailable here or does not match the rendered page. No page location was invented."}</p>
        <StatusBadge tone="info">Unverified extraction</StatusBadge>
        {value.target && value.status !== "missing" && value.status !== "broken" && props.onActionAnchor
          ? <Button onClick={() => props.onActionAnchor?.(value.anchorId)}>Use anchor {number} for source actions</Button> : null}
        {coordinates && props.overlay ? createPortal(<svg className="viewer-anchor-marker" aria-hidden="true" viewBox="0 0 100 100" preserveAspectRatio="none">
          <rect x={coordinates.x} y={coordinates.y} width={coordinates.width} height={coordinates.height} />
          <text x={coordinates.x} y={Math.max(3, coordinates.y)}>{number}</text></svg>, props.overlay) : null}
      </section>;
    })}
  </section>;
}
