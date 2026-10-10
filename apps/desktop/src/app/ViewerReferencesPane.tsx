import { useEffect, useRef, useState, type ReactNode } from "react";
import { Button, Panel, StatusBadge } from "@research-observatory/ui-components";
import { decodeReferencePage, decodeReferenceNotice, type DocumentReferencePort, type ReferencePage, type ReferencePreview, type ReferenceWork } from "./documentReferences";
import { viewerSourcesMatch, type ViewerMainAdmission, type ViewerMetadata } from "./documentViewer";
import { newAttachmentId } from "./documentAttachment";

interface Props {
  readonly metadata: ViewerMetadata; readonly revisionId: string; readonly port: DocumentReferencePort;
  readonly main: ViewerMainAdmission; readonly reserveCore: () => () => void;
  readonly onSource: (entry: ReferencePreview) => void; readonly onFailure: (code: string) => void;
}
/** One bounded protected reference preview; current authority is checked on every request. */
export function ViewerReferencesPane(props: Props): ReactNode {
  const [page, setPage] = useState<ReferencePage | null>(null), [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("Inspect references in this exact accepted revision."), [checked, setChecked] = useState(false);
  const [target, setTarget] = useState<ReferenceWork | null>(null);
  const retained = useRef<(() => void) | null>(null), live = useRef(false), generation = useRef(0), pending = useRef(false);
  const heading = useRef<HTMLHeadingElement>(null), targetHeading = useRef<HTMLHeadingElement>(null);
  const command = useRef<string | null>(null);
  const knownHead = useRef<string | null>(null);
  function clear(): void { retained.current?.(); retained.current = null; setPage(null); setTarget(null); }
  useEffect(() => {
    live.current = true; generation.current += 1; clear(); setBusy(false); setChecked(false);
    setStatus("Inspect references in this exact accepted revision."); command.current = null; knownHead.current = null;
    return () => { live.current = false; generation.current += 1; retained.current?.(); retained.current = null; };
  }, [props.revisionId, props.metadata, props.port, props.main]);

  async function load(enrich: boolean, after: number | null = null, restart = false): Promise<void> {
    if (pending.current) return;
    pending.current = true; const ticket = ++generation.current;
    const expected = restart ? null : knownHead.current;
    clear(); setBusy(true); setStatus(enrich ? "Extracting references and checking current canonical Works…" : "Checking exact references and current permission…");
    let releaseMain = (): void => undefined, releaseCore = (): void => undefined, terminal = true;
    const current = (): boolean => live.current && ticket === generation.current;
    try {
      releaseMain = props.main.context(); releaseCore = props.reserveCore(); terminal = false;
      if (enrich) command.current ??= newAttachmentId();
      const result = enrich ? await props.port.enrich(props.metadata.source.projectId, props.revisionId, command.current!, expected)
        : await props.port.read(props.metadata.source.projectId, props.revisionId, expected, after);
      terminal = true;
      const value = decodeReferencePage(result, props.metadata.source.projectId, props.revisionId);
      const notice = !enrich ? decodeReferenceNotice(result, props.metadata.source.projectId, props.revisionId) : null;
      if (!current()) { releaseMain(); return; }
      setChecked(true);
      if (notice && viewerSourcesMatch(notice.source, props.metadata.source)) {
        releaseMain(); knownHead.current = notice.collectionRevisionId;
        setStatus(notice.reasonCode === "viewer-resource-limit" ? "References exceed the local Reader limit. The original and accepted revision remain retained."
          : "The retained reference collection is unavailable under current matching evidence. Refresh matches to check current Works; no prior text was displayed.");
        return;
      }
      if (!value || !viewerSourcesMatch(value.source, props.metadata.source) || value.afterOrder !== after
        || !enrich && expected !== null && value.collectionRevisionId !== expected) {
        releaseMain(); setStatus(result === null && !enrich && expected === null
          ? "No reference collection is recorded. Extract references to preserve their raw text and assess Work matches."
          : "References could not be confirmed under current permission. Check current references; no substitute collection was displayed.");
        return;
      }
      command.current = null; knownHead.current = value.collectionRevisionId; retained.current = releaseMain; setPage(value);
      setStatus(value.total ? `Reference ${(value.entries[0]?.order ?? 0) + 1} of ${value.total}. Extraction remains unverified.` : "No reference-list entries were reported in this accepted structure.");
      heading.current?.focus();
    } catch (error) {
      const code = error instanceof Error ? error.message : "viewer-owned-read-drain-pending";
      terminal = terminal || code === "viewer-resource-limit" || code === "viewer-source-unavailable";
      if (terminal) releaseMain();
      if (current()) {
        setStatus(code === "viewer-resource-limit" ? "References exceed the local Reader limit. The original and accepted revision remain retained."
          : "Reference access could not be confirmed. Return to source review.");
        if (!terminal) props.onFailure("viewer-owned-read-drain-pending");
      }
    } finally {
      if (terminal) releaseCore();
      if (current()) { pending.current = false; setBusy(false); }
    }
  }
  function inspect(work: ReferenceWork): void { setTarget(work); window.requestAnimationFrame(() => targetHeading.current?.focus()); }
  const entry = page?.entries[0];
  return <Panel title="References"><section className="ro-stack ro-wrap-anywhere" aria-label="Reference inspection" aria-busy={busy}>
    <h2 ref={heading} tabIndex={-1}>Reference list</h2><p role="status">{status}</p>
    <div className="ro-action-row"><Button disabled={busy} onClick={() => void load(false, null, true)}>Inspect references</Button>
      {checked ? <Button disabled={busy} onClick={() => void load(true)}>{knownHead.current ? "Refresh reference matches" : "Extract references"}</Button> : null}
      {page?.nextAfterOrder !== null && page?.nextAfterOrder !== undefined ? <Button disabled={busy} onClick={() => void load(false, page.nextAfterOrder)}>Next reference</Button> : null}</div>
    {entry ? <section aria-label={`Reference ${entry.order + 1}`} className="ro-stack">
      <p className="anchor-passage-text">{entry.rawPreview || "Reference text not reported."}</p>
      {entry.rawTruncated ? <p>Raw preview truncated; all {entry.rawLength.toLocaleString()} codepoints remain in the encrypted reference collection.</p> : null}
      <StatusBadge tone="info">Unverified extraction</StatusBadge><p>Match: {entry.linkState.replaceAll("-", " ")}</p>
      <dl>{entry.fields.map(field => <div key={field.name}><dt>{field.name}</dt><dd>{field.value} · {field.knowledgeStatus}
        {field.truncated ? ` · bounded preview of ${field.valueCount} observation(s)` : ""}</dd></div>)}</dl>
      <ul>{entry.identifiers.map((identifier, index) => <li key={index}>{identifier.scheme}: {identifier.observed}
        {identifier.truncated ? " · preview truncated" : ""} · {identifier.normalizedStatus} syntax · {identifier.verificationState}
        {identifier.activeForMatching ? "" : " · inactive for matching"}</li>)}</ul>
      {entry.identifierCount > entry.identifiers.length ? <p>Showing {entry.identifiers.length} of {entry.identifierCount} identifiers; all observations remain retained.</p> : null}
      {entry.anchor ? <Button disabled={busy} onClick={() => props.onSource(entry)}>Jump to reference source</Button> : <p>Exact text anchor not reported.</p>}
      {entry.anchorTruncated ? <p>The source-anchor quotation is bounded; the full raw reference remains retained.</p> : null}
      {entry.target ? <Button onClick={() => inspect(entry.target!)}>Inspect linked canonical Work</Button> : null}
      {entry.candidates.length ? <><p>Similarity proposes human review. It does not verify or merge Works.</p><ol>{entry.candidates.map(candidate => <li key={candidate.target.workId}>
        <Button onClick={() => inspect(candidate.target)}>Inspect candidate Work</Button> · score {candidate.score / 100}% · human review required
        <dl>{candidate.features.map(feature => <div key={feature.name}><dt>{feature.name}</dt><dd>{feature.state.replaceAll("-", " ")}
          {feature.score === null ? "" : ` · ${feature.score / 100}%`}{feature.conflict ? " · conflict" : ""}</dd></div>)}</dl>
        <p>{candidate.flags.join(", ") || "No additional match flags reported."}</p></li>)}</ol></> : null}
      {entry.candidateCount > entry.candidates.length ? <p>Showing {entry.candidates.length} of {entry.candidateCount} candidates; all scores remain retained for review.</p> : null}
      {entry.matchFlags.length ? <p>Match uncertainty: {entry.matchFlags.join(", ")}</p> : null}
    </section> : null}
    {target ? <section aria-label="Canonical reference target"><h3 ref={targetHeading} tabIndex={-1}>Canonical Work target</h3>
      <dl><dt>Work</dt><dd>{target.workId}</dd><dt>Matched Work revision</dt><dd>{target.revisionId}</dd></dl>
      <p>This inferred association leaves the Work and its scholarly verification unchanged.</p></section> : null}
  </section></Panel>;
}
