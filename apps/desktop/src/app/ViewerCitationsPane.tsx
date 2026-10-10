import { useEffect, useRef, useState, type ReactNode } from "react";
import { Button, Panel, StatusBadge } from "@research-observatory/ui-components";
import { decodeCitationNotice, decodeCitationPage, type CitationPage, type CitationPreview, type CitationReference, type DocumentCitationPort } from "./documentCitations";
import { decodeReferencePage, type DocumentReferencePort, type ReferencePreview } from "./documentReferences";
import { newAttachmentId } from "./documentAttachment";
import { viewerSourcesMatch, type ViewerMainAdmission, type ViewerMetadata } from "./documentViewer";

interface Props {
  readonly metadata: ViewerMetadata; readonly revisionId: string; readonly port: DocumentCitationPort;
  readonly referencePort: DocumentReferencePort; readonly main: ViewerMainAdmission; readonly reserveCore: () => () => void;
  readonly onSource: (entry: CitationPreview) => void; readonly onReferenceSource: (entry: ReferencePreview) => void;
  readonly onFailure: (code: string) => void;
}
/** The citation plus optional reference preview share one <=128 KiB context. */
export function ViewerCitationsPane(props: Props): ReactNode {
  const [page, setPage] = useState<CitationPage | null>(null), [reference, setReference] = useState<ReferencePreview | null>(null);
  const [busy, setBusy] = useState(false), [checked, setChecked] = useState(false);
  const [status, setStatus] = useState("Inspect citations in this exact accepted revision.");
  const live = useRef(false), generation = useRef(0), pending = useRef(false), retained = useRef<(() => void) | null>(null);
  const knownHead = useRef<string | null>(null), command = useRef<{ id: string; reference: string; expected: string | null } | null>(null);
  const heading = useRef<HTMLHeadingElement>(null), referenceHeading = useRef<HTMLHeadingElement>(null);
  function clear(): void { retained.current?.(); retained.current = null; setPage(null); setReference(null); }
  useEffect(() => {
    live.current = true; generation.current += 1; clear(); setBusy(false); setChecked(false); knownHead.current = null; command.current = null;
    setStatus("Inspect citations in this exact accepted revision.");
    return () => { live.current = false; generation.current += 1; retained.current?.(); retained.current = null; };
  }, [props.revisionId, props.metadata, props.port, props.referencePort, props.main]);

  async function load(enrich: boolean, after: number | null = null, restart = false, target: CitationReference | null = null): Promise<void> {
    if (pending.current) return;
    const selectedPage = page;
    if (target && !selectedPage) return;
    pending.current = true; const ticket = ++generation.current, expected = restart ? null : knownHead.current;
    clear(); setBusy(true); setStatus(target ? "Checking this reference under current permission…" : enrich ? "Extracting source-grounded citation contexts…" : "Checking citations and current permission…");
    let releaseMain = (): void => undefined, releaseCore = (): void => undefined, terminal = true;
    const current = (): boolean => live.current && generation.current === ticket;
    try {
      releaseMain = props.main.context(); releaseCore = props.reserveCore();
      const project = props.metadata.source.projectId;
      if (target) {
        terminal = false;
        const result = await props.referencePort.read(project, props.revisionId, selectedPage!.referenceCollectionRevisionId, target.order ? target.order - 1 : null);
        terminal = true;
        const value = decodeReferencePage(result, project, props.revisionId), item = value?.entries[0];
        if (!current()) { releaseMain(); return; }
        if (!value || !item || !viewerSourcesMatch(value.source, props.metadata.source) || value.collectionRevisionId !== selectedPage!.referenceCollectionRevisionId
          || value.collectionId !== selectedPage!.referenceCollectionId || item.referenceId !== target.referenceId || item.nodeId !== target.nodeId || item.order !== target.order) {
          releaseMain(); setStatus("This exact reference is unavailable or has changed. Check citations and references again."); return;
        }
        retained.current = releaseMain; setPage(selectedPage); setReference(item); setStatus("Reference source checked. Its extraction and Work association remain unverified.");
        window.requestAnimationFrame(() => referenceHeading.current?.focus()); return;
      }
      let result: unknown;
      if (enrich) {
        terminal = false;
        const observed = await props.referencePort.read(project, props.revisionId, null, null);
        terminal = true;
        const refs = decodeReferencePage(observed, project, props.revisionId);
        if (!current()) { releaseMain(); return; }
        if (!refs || !viewerSourcesMatch(refs.source, props.metadata.source)) {
          releaseMain(); setStatus("Extract or refresh the reference list first, then retry citation extraction."); return;
        }
        if (!command.current || command.current.reference !== refs.collectionRevisionId || command.current.expected !== expected) {
          command.current = { id: newAttachmentId(), reference: refs.collectionRevisionId, expected };
        }
        terminal = false;
        result = await props.port.enrich(project, props.revisionId, command.current.id, command.current.reference, expected);
      } else {
        terminal = false;
        result = await props.port.read(project, props.revisionId, expected, after);
      }
      terminal = true;
      const value = decodeCitationPage(result, project, props.revisionId), notice = !enrich ? decodeCitationNotice(result, project, props.revisionId) : null;
      if (!current()) { releaseMain(); return; }
      setChecked(true);
      if (notice && viewerSourcesMatch(notice.source, props.metadata.source)) {
        knownHead.current = notice.collectionRevisionId; releaseMain();
        setStatus(notice.reasonCode === "viewer-resource-limit" ? "Citations exceed the local Reader limit. The accepted document remains available."
          : "Saved citations are unavailable under current references or permission. Check the reference list, then refresh citation contexts."); return;
      }
      if (!value || !viewerSourcesMatch(value.source, props.metadata.source) || value.afterOrder !== after || !enrich && expected !== null && value.collectionRevisionId !== expected) {
        releaseMain(); setStatus(result === null && !enrich && expected === null ? "No citation collection is recorded. Extract citation contexts after the reference list."
          : "Citations could not be confirmed. Check current source permission and references."); return;
      }
      if (enrich) command.current = null;
      retained.current = releaseMain; knownHead.current = value.collectionRevisionId; setPage(value);
      setStatus(value.total ? `Citation ${(value.entries[0]?.order ?? 0) + 1} of ${value.total}. Targets and contexts remain unverified.` : "No recognized citation markers were found. This does not establish absence of citations.");
      heading.current?.focus();
    } catch (error) {
      const code = error instanceof Error ? error.message : "viewer-owned-read-drain-pending";
      terminal = terminal || code === "viewer-resource-limit" || code === "viewer-source-unavailable";
      if (terminal) releaseMain();
      if (current()) {
        setStatus(code === "viewer-resource-limit" ? "Citations exceed the local Reader limit. The accepted document remains retained." : "Citation access could not be confirmed. Return to source review.");
        if (!terminal) props.onFailure("viewer-owned-read-drain-pending");
      }
    } finally {
      if (terminal) releaseCore();
      if (current()) { pending.current = false; setBusy(false); }
    }
  }
  const entry = page?.entries[0];
  return <Panel title="Citations"><section className="ro-stack ro-wrap-anywhere" aria-label="Citation inspection" aria-busy={busy}>
    <h2 ref={heading} tabIndex={-1}>Citation contexts</h2><p role="status">{status}</p>
    <div className="ro-action-row"><Button disabled={busy} onClick={() => void load(false, null, true)}>Inspect citations</Button>
      {checked ? <Button disabled={busy} onClick={() => void load(true)}>{knownHead.current ? "Refresh citation contexts" : "Extract citation contexts"}</Button> : null}
      {page?.nextAfterOrder !== null && page?.nextAfterOrder !== undefined ? <Button disabled={busy} onClick={() => void load(false, page.nextAfterOrder)}>Next citation</Button> : null}</div>
    {entry ? <section aria-label={`Citation ${entry.order + 1}`} className="ro-stack">
      <p className="anchor-passage-text">{entry.markerPreview || "Marker text not reported."}</p>
      {entry.markerTruncated ? <p>Marker preview truncated; {entry.markerLength.toLocaleString()} codepoints remain retained.</p> : null}
      <StatusBadge tone="info">{entry.knowledgeStatus} · unverified</StatusBadge><p>{entry.style.replaceAll("-", " ")} · target {entry.resolution}</p>
      <p>Parser confidence: {entry.confidence.value === null ? entry.confidence.state.replaceAll("-", " ") : entry.confidence.value}. Citation does not establish support for a claim.</p>
      {entry.sentence ? <><h3>Sentence context · inferred boundaries</h3><p className="anchor-passage-text">{entry.sentence.textPreview}</p>{entry.sentence.truncated ? <p>Sentence preview truncated; full context remains retained.</p> : null}</> : <p>Sentence context not reported.</p>}
      {entry.paragraph ? <><h3>Paragraph context</h3><p className="anchor-passage-text">{entry.paragraph.textPreview}</p>{entry.paragraph.truncated ? <p>Paragraph preview truncated; full context remains retained.</p> : null}</> : <p>Paragraph context not reported.</p>}
      {entry.contextReason === "normalization-boundary" ? <p>The marker crosses a normalization boundary. Its exact source anchor is retained; a containing-text highlight could not be confirmed.</p> : null}
      {entry.anchor ? <Button disabled={busy} onClick={() => props.onSource(entry)}>Jump to citation source</Button> : <p>Exact text anchor not reported.</p>}
      {entry.anchorTruncated ? <p>Source-anchor quotation is bounded; full marker remains retained.</p> : null}
      <ol>{entry.targets.map((target, index) => <li key={index}><p>{target.label} · {target.resolution}</p>
        {target.references.map(ref => <Button key={ref.referenceId} disabled={busy} onClick={() => void load(false, null, false, ref)}>Inspect reference {ref.order + 1}</Button>)}
        {target.referenceCount > target.references.length ? <p>Showing {target.references.length} of {target.referenceCount} possible references.</p> : null}</li>)}</ol>
      {entry.targetCount > entry.targets.length ? <p>Showing {entry.targets.length} of {entry.targetCount} target members. All members remain retained.</p> : null}
    </section> : null}
    {reference ? <section aria-label="Citation reference target" className="ro-stack"><h3 ref={referenceHeading} tabIndex={-1}>Reference {reference.order + 1}</h3>
      <p className="anchor-passage-text">{reference.rawPreview}</p><p>Work association: {reference.linkState.replaceAll("-", " ")} · unverified</p>
      {reference.rawTruncated ? <p>Reference preview truncated; {reference.rawLength.toLocaleString()} codepoints remain retained.</p> : null}
      {reference.target ? <dl><dt>Canonical Work</dt><dd>{reference.target.workId}</dd><dt>Matched revision</dt><dd>{reference.target.revisionId}</dd></dl> : null}
      {reference.candidates.length ? <><p>Possible Works require human review.</p><ul>{reference.candidates.map(candidate => <li key={candidate.target.workId}>{candidate.target.workId} · score {candidate.score / 100}%</li>)}</ul></> : null}
      {reference.anchor ? <Button disabled={busy} onClick={() => props.onReferenceSource(reference)}>Jump to target reference source</Button> : null}
    </section> : null}
  </section></Panel>;
}
