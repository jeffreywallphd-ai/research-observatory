import { useEffect, useRef, useState, type ReactNode } from "react";
import { CoreApiClientError, createCoreApiClient, type VersionCommand, type VersionContext, type VersionDate,
  type VersionDefinition, type VersionOutcome, type VersionPlan, type VersionPreview, type VersionReference,
  type VersionWorkPage, type WorkVersion, type UpdateRelationDraft } from "@research-observatory/contracts/core-api";
import { Button, DataTable, Notification, Panel, StatusBadge } from "@research-observatory/ui-components";
import { DocumentAttachmentPane, type AttachmentHandoff } from "./DocumentAttachmentPane";
import { attachmentSelection, sameAttachmentSelection } from "./documentAttachment";

type Client = ReturnType<typeof createCoreApiClient>;
const kinds: readonly VersionDefinition["kind"][] = ["preprint", "accepted-manuscript", "version-of-record", "erratum", "correction", "expression-of-concern", "retraction", "not-reported"];
const relations: readonly UpdateRelationDraft["kind"][] = ["is-version-of", "supersedes", "erratum-for", "corrects", "expresses-concern", "retracts"];
const label = (value: string): string => value.charAt(0).toUpperCase() + value.slice(1).replaceAll("-", " ");
const warnings: Partial<Record<UpdateRelationDraft["kind"], string>> = { "erratum-for": "Erratum linked", corrects: "Correction linked", "expresses-concern": "Expression of concern linked", retracts: "Retraction linked" };
const reference = (version: WorkVersion): VersionReference => ({ versionId: version.versionId, revisionId: version.revisionId });
const dateLabel = (date: VersionDate): string => date.value ? `${date.value} (${date.precision})` : label(date.precision);
const sourceTitle = (source: VersionContext["sources"][number]): string => source.assertion.fields.find((field) => field.name === "title")?.observed ?? "Title not reported";
const versionLabel = (context: VersionContext, id: string): string => {
  const index = context.versions.findIndex((version) => version.versionId === id);
  return index < 0 ? "Historical version" : `${label(context.versions[index]!.definition.kind)} · version ${index + 1}`;
};

export function ReconciliationVersionsPane({ root, projectId, client, announce, onClose, onDenied, onTaskCenter, onOpenReader, returnAttachment, onAttachmentReturnConsumed, onAttachmentRecovery }: {
  readonly root: string; readonly projectId: string; readonly client: Client; readonly announce: (message: string) => void;
  readonly onClose: () => void; readonly onDenied: () => void;
  readonly onTaskCenter?: ((handoff: AttachmentHandoff) => void) | undefined;
  readonly onOpenReader?: ((handoff: AttachmentHandoff) => void) | undefined;
  readonly returnAttachment?: AttachmentHandoff | null | undefined;
  readonly onAttachmentReturnConsumed?: ((handoff: AttachmentHandoff) => void) | undefined;
  readonly onAttachmentRecovery?: ((selection: AttachmentHandoff["selection"], handoff: AttachmentHandoff | null) => void) | undefined;
}): ReactNode {
  const [page, setPage] = useState<VersionWorkPage | null>(null), [cursors, setCursors] = useState<readonly (string | null)[]>([null]);
  const [selected, setSelected] = useState<readonly string[]>([]), [context, setContext] = useState<VersionContext | null>(null);
  const [busy, setBusy] = useState(false), [failure, setFailure] = useState<string | null>(null);
  const [action, setAction] = useState<VersionPlan["action"]>("register"), [kind, setKind] = useState<VersionDefinition["kind"]>("not-reported");
  const [sources, setSources] = useState<readonly string[]>([]), [versionId, setVersionId] = useState("");
  const [relationKind, setRelationKind] = useState<UpdateRelationDraft["kind"]>("is-version-of"), [targetId, setTargetId] = useState("");
  const [evidenceKey, setEvidenceKey] = useState(""), [knowledge, setKnowledge] = useState<UpdateRelationDraft["knowledgeStatus"]>("adjudicated");
  const [precision, setPrecision] = useState<VersionDate["precision"]>("not-reported"), [dateValue, setDateValue] = useState(""), [rationale, setRationale] = useState("");
  const [preview, setPreview] = useState<{ plan: VersionPlan; value: VersionPreview } | null>(null);
  const [command, setCommand] = useState<VersionCommand | null>(null), [outcome, setOutcome] = useState<VersionOutcome | null>(null);
  const [historical, setHistorical] = useState<WorkVersion | null>(null);
  const [attachmentVersionId, setAttachmentVersionId] = useState<string | null>(null);
  const [attachmentInitialSourceId, setAttachmentInitialSourceId] = useState<string | undefined>(undefined);
  const [attachmentHandoff, setAttachmentHandoff] = useState<AttachmentHandoff | null>(null);
  const [needsRefresh, setNeedsRefresh] = useState(false);
  const live = useRef(true), generation = useRef(0), pending = useRef(false);
  const heading = useRef<HTMLHeadingElement>(null), previewHeading = useRef<HTMLHeadingElement>(null), resultHeading = useRef<HTMLHeadingElement>(null), historyHeading = useRef<HTMLHeadingElement>(null);
  const reviewButton = useRef<HTMLButtonElement>(null), previewButton = useRef<HTMLButtonElement>(null);
  const inventoryHeading = useRef<HTMLHeadingElement>(null);
  const refreshButton = useRef<HTMLButtonElement>(null);
  const attachmentTriggers = useRef(new Map<string, HTMLButtonElement>());
  const unresolved = command !== null && outcome === null, disabled = busy || preview !== null || command !== null || outcome !== null;
  const current = (ticket: number): boolean => live.current && generation.current === ticket;
  useEffect(() => {
    live.current = true;
    if (returnAttachment?.selection.projectId === projectId) {
      setSelected([returnAttachment.selection.workId]);
      void loadContext([returnAttachment.selection.workId], false, returnAttachment);
    } else void loadPage([null]);
    return () => { live.current = false; generation.current += 1; };
  }, []);
  useEffect(() => {
    if (attachmentHandoff && context && attachmentVersionId === attachmentHandoff.selection.versionId
      && sameAttachmentSelection(attachmentHandoff.selection,
        attachmentSelection(context, attachmentHandoff.selection.versionId,
          attachmentHandoff.selection.sourceAssertionRevisionId))) onAttachmentReturnConsumed?.(attachmentHandoff);
  }, [attachmentHandoff, attachmentVersionId, context, onAttachmentReturnConsumed]);
  useEffect(() => { if (context) heading.current?.focus(); }, [context]);
  useEffect(() => { if (page && !context) inventoryHeading.current?.focus(); }, [page]);
  useEffect(() => { if (preview) previewHeading.current?.focus(); }, [preview]);
  useEffect(() => { if (outcome) resultHeading.current?.focus(); }, [outcome]);
  useEffect(() => { if (historical) historyHeading.current?.focus(); }, [historical]);
  useEffect(() => { if (needsRefresh && !busy) refreshButton.current?.focus(); }, [needsRefresh, busy]);

  async function perform(operation: (ticket: number) => Promise<void>): Promise<void> {
    if (pending.current) return;
    pending.current = true;
    const ticket = ++generation.current;
    setBusy(true); setFailure(null);
    try { await operation(ticket); }
    catch (error) {
      if (current(ticket)) {
        const denied = error instanceof CoreApiClientError && error.problem.status === 403;
        const notApplied = error instanceof CoreApiClientError && error.problem.status === 409
          && error.problem.code === "RO-CORE-RECONCILIATION-VERSION-NOT-APPLIED";
        if (denied) {
          setPage(null); setSelected([]); setContext(null); setPreview(null); setCommand(null); setOutcome(null); setHistorical(null);
          setAttachmentVersionId(null);
          setRationale(""); setSources([]); setVersionId(""); setTargetId(""); setEvidenceKey(""); setDateValue(""); onDenied();
          setNeedsRefresh(false);
        }
        if (notApplied) { setCommand(null); setPreview(null); setNeedsRefresh(true); }
        setFailure(denied ? "Current project or source access was denied. Check accepted Intent and source rights before reopening evidence."
          : notApplied ? "This decision was not applied because its evidence changed. Refresh version evidence, then prepare a new preview."
          : "The version reply could not be confirmed. Your draft is retained. Check current evidence before preparing a new decision, or retry the same saved decision if its reply was lost.");
        announce(denied ? "Version evidence access denied." : "Version review needs attention.");
      }
    } finally { if (current(ticket)) { pending.current = false; setBusy(false); } }
  }
  async function loadPage(next: readonly (string | null)[]): Promise<void> {
    await perform(async (ticket) => {
      const result = await client.listScholarlyVersionWorks({ root, after: next.at(-1) ?? null, limit: 32 });
      if (result.projectId !== projectId) throw new Error("RO-CORE-RESPONSE-INVALID");
      if (current(ticket)) { setPage(result); setCursors(next); }
    });
  }
  async function loadContext(ids = selected, preserveDraft = false, handoff: AttachmentHandoff | null = null): Promise<void> {
    await perform(async (ticket) => {
      const result = await client.inspectScholarlyVersionContext({ root, workIds: [...ids].sort() });
      if (result.projectId !== projectId) throw new Error("RO-CORE-RESPONSE-INVALID");
      if (current(ticket)) {
        setContext(result); setPreview(null); setCommand(null); setOutcome(null); setHistorical(null);
        setAttachmentVersionId(null); setAttachmentInitialSourceId(undefined); setAttachmentHandoff(null);
        setNeedsRefresh(false);
        if (handoff && !preserveDraft) {
          const binding = attachmentSelection(result, handoff.selection.versionId,
            handoff.selection.sourceAssertionRevisionId);
          if (sameAttachmentSelection(handoff.selection, binding)) {
            setAttachmentInitialSourceId(handoff.selection.sourceAssertionRevisionId);
            setAttachmentHandoff(handoff);
            setAttachmentVersionId(binding!.versionId);
          }
          else setFailure("The selected Work/version changed while you were away. Review current revisions before another attachment attempt.");
        }
        if (preserveDraft) {
          const members = new Set(result.works.flatMap((work) => work.assertionRevisionIds));
          const available = new Set(result.versions.map((version) => version.versionId));
          const anchors = new Set(result.sources.flatMap((source) => (["field", "identifier"] as const).flatMap((category) =>
            (category === "field" ? source.assertion.fields : source.assertion.identifiers).map((item) => JSON.stringify([source.assertionRevisionId, category, item.sourceSelector])))));
          const missingSources = sources.some((id) => !members.has(id));
          const missingVersion = Boolean(versionId && !available.has(versionId)), missingTarget = Boolean(targetId && !available.has(targetId));
          const missingAnchor = Boolean(evidenceKey && !anchors.has(evidenceKey));
          if (missingSources) setSources([]);
          if (missingVersion) setVersionId("");
          if (missingTarget) setTargetId("");
          if (missingAnchor) setEvidenceKey("");
          if (missingSources || missingVersion || missingTarget || missingAnchor) setFailure("Some selected evidence is no longer available in these Works. Review and select the affected sources or versions again; your rationale and classification are retained.");
        } else {
          setAction("register"); setKind("not-reported"); setSources([]); setVersionId(""); setTargetId(""); setEvidenceKey("");
          setPrecision("not-reported"); setDateValue(""); setRationale("");
        }
        announce("Current versions, preference and source warnings loaded.");
      }
    });
  }
  function backToWorks(): void {
    setContext(null); setHistorical(null); setPreview(null); setCommand(null); setOutcome(null); setFailure(null);
    setAttachmentVersionId(null); setAttachmentInitialSourceId(undefined); setAttachmentHandoff(null);
    setNeedsRefresh(false);
    if (!page) void loadPage([null]);
    globalThis.requestAnimationFrame(() => { if (live.current) reviewButton.current?.focus(); });
  }
  function closeAttachment(): void {
    const closedVersionId = attachmentVersionId;
    setAttachmentVersionId(null); setAttachmentInitialSourceId(undefined); setAttachmentHandoff(null);
    globalThis.requestAnimationFrame(() => {
      const target = closedVersionId ? attachmentTriggers.current.get(closedVersionId) : null;
      if (live.current && target?.isConnected && !target.disabled) target.focus();
      else if (live.current) heading.current?.focus();
    });
  }
  function backToDraft(): void {
    setPreview(null);
    globalThis.requestAnimationFrame(() => { if (live.current) previewButton.current?.focus(); });
  }
  function chooseVersion(id: string): void {
    setVersionId(id);
    const version = context?.versions.find((item) => item.versionId === id);
    if (action === "revise" && version) {
      setKind(version.definition.kind); setSources(version.definition.assertionRevisionIds);
      setPrecision(version.definition.date.precision); setDateValue(version.definition.date.value ?? "");
    }
  }
  const evidence = context?.sources.flatMap((source) => (["field", "identifier"] as const).flatMap((category) =>
    (category === "field" ? source.assertion.fields : source.assertion.identifiers).map((item) => ({
      key: JSON.stringify([source.assertionRevisionId, category, item.sourceSelector]), source, category,
      selector: item.sourceSelector, observed: item.observed,
    })))) ?? [];
  const definitionAction = action === "register" || action === "revise";
  const chosen = context?.versions.find((item) => item.versionId === versionId);
  const target = context?.versions.find((item) => item.versionId === targetId);
  const anchor = evidence.find((item) => item.key === evidenceKey);
  const validDate = precision === "unknown" || precision === "not-reported" || dateValue.trim().length >= 4;
  const canPreview = Boolean(context && !needsRefresh && rationale.trim() && (action === "prefer" || validDate)
    && (!definitionAction || sources.length > 0) && (action === "register" || action === "relate" || chosen)
    && (action !== "prefer" || context.works.length === 1)
    && (action !== "relate" || chosen && target && chosen.versionId !== target.versionId && anchor));
  async function prepare(): Promise<void> {
    if (!context || !canPreview || disabled) return;
    await perform(async (ticket) => {
      const date: VersionDate = { precision, value: precision === "unknown" || precision === "not-reported" ? null : dateValue.trim() };
      let relation: UpdateRelationDraft | null = null;
      if (action === "relate" && chosen && target && anchor) {
        const bytes = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(anchor.observed));
        relation = { kind: relationKind, source: reference(chosen), target: reference(target), date, knowledgeStatus: knowledge,
          evidence: [{ assertionRevisionId: anchor.source.assertionRevisionId, category: anchor.category, selector: anchor.selector,
            valueSha256: Array.from(new Uint8Array(bytes), (byte) => byte.toString(16).padStart(2, "0")).join("") }] };
      }
      const ownPreferences = context.preferences.filter((item) => item.workId === context.works[0]?.workId);
      const plan: VersionPlan = { schemaVersion: "1.0", action, workIds: context.works.map((item) => item.workId).sort(), contextSha256: context.contextSha256,
        rationale: rationale.trim(), definition: definitionAction ? { kind, assertionRevisionIds: [...sources].sort(), date } : null,
        version: action === "revise" || action === "prefer" ? reference(chosen!) : null, relation,
        previousPreferenceRevisionId: action === "prefer" ? ownPreferences.at(-1)?.revisionId ?? null : null };
      const value = await client.previewScholarlyVersionDecision({ root, plan });
      if (current(ticket)) { setPreview({ plan, value }); announce("Version decision preview ready."); }
    });
  }
  async function commit(): Promise<void> {
    if (!preview || busy || outcome) return;
    const exact = command ?? { commandId: preview.value.commandId, plan: preview.plan, expectedPreviewSha256: preview.value.previewSha256 };
    setCommand(exact);
    await perform(async (ticket) => {
      const result = await client.commitScholarlyVersionDecision({ root, command: exact });
      if (current(ticket)) { setOutcome(result); announce("Version decision saved. Earlier source records and history are retained."); }
    });
  }
  async function inspect(revisionId: string): Promise<void> {
    await perform(async (ticket) => {
      const value = await client.inspectScholarlyVersion({ root, revisionId });
      if (current(ticket)) setHistorical(value);
    });
  }
  const versionOptions = context?.versions.map((version) => <option key={version.versionId} value={version.versionId}>{versionLabel(context, version.versionId)}</option>);
  return <Panel title="Work versions and status"><section className="ro-stack ro-form" aria-label="Work version review" aria-busy={busy}
    onKeyDown={(event) => { if (event.key === "Escape" && !busy && !unresolved) { event.preventDefault(); event.stopPropagation(); if (preview && !outcome) backToDraft(); else if (context) backToWorks(); else onClose(); } }}>
    {failure ? <Notification tone="danger" title="Version review needs attention">{failure}</Notification> : null}
    {busy ? <p role="status">Checking current version evidence…</p> : null}
    {!context ? <>
      <h3 ref={inventoryHeading} tabIndex={-1} className="ro-typography ro-typography--card-title">Select canonical Works</h3>
      <p>Review versions independently of duplicate suggestions. Select up to eight Works for a relationship; select one Work to choose its preferred citable version.</p>
      <Button disabled={busy} onClick={onClose}>Close Work versions</Button>
      <Button disabled={busy || !selected.length} onClick={() => { setSelected([]); setFailure(null); }}>Clear Work selection</Button>
      {page?.items.map((work) => <label key={work.workId} className="ro-cluster ro-wrap-anywhere"><input type="checkbox" checked={selected.includes(work.workId)} disabled={busy || !selected.includes(work.workId) && selected.length >= 8}
        onChange={(event) => { const checked = event.currentTarget.checked; setSelected((saved) => checked ? [...saved, work.workId] : saved.filter((id) => id !== work.workId)); }} />Select Work {work.workId} · {work.assertionRevisionIds.length} source assertion(s)</label>)}
      {page && !page.items.length ? <p>No active Works on this page. Reconcile accepted sources to create canonical Works, or continue to the next page.</p> : null}
      <nav className="ro-action-row" aria-label="Work pages"><Button disabled={busy || cursors.length < 2} onClick={() => void loadPage(cursors.slice(0, -1))}>Previous Works</Button>
        <Button disabled={busy || !page?.nextAfter} onClick={() => page?.nextAfter && void loadPage([...cursors, page.nextAfter])}>Next Works</Button>
        <Button disabled={busy} onClick={() => void loadPage(cursors)}>Refresh Works</Button></nav>
      <Button ref={reviewButton} tone="primary" disabled={busy || !selected.length} onClick={() => void loadContext()}>Review selected Work versions</Button>
    </> : <>
      <h3 ref={heading} tabIndex={-1} className="ro-typography ro-typography--card-title">Review Work versions</h3>
      <p>Version classifications, relationships and citable preferences are researcher decisions. Original assertions and competing status evidence stay available. A preference does not remove a warning or grant source rights.</p>
      <div className="ro-action-row"><Button disabled={busy || unresolved || attachmentVersionId !== null} onClick={backToWorks}>Back to Works</Button>
        <Button ref={refreshButton} disabled={busy || command !== null || attachmentVersionId !== null} onClick={() => void loadContext(context.works.map((work) => work.workId), true)}>Refresh version evidence</Button></div>
      {context.preferenceStates.map((state) => <section key={state.workId} className="ro-stack" aria-label={`Citable preference for Work ${state.workId}`}>
        <p className="ro-wrap-anywhere">Work {state.workId}</p>
        {state.selected ? <><StatusBadge>Preferred citable version · {state.state.replaceAll("-", " ")}</StatusBadge><p>{versionLabel(context, state.selected.versionId)}</p>
          {state.state === "requires-review" ? <p>Membership, version or status evidence changed. Review the retained choice and make a new explicit selection before relying on it.</p> : null}</> : <p>No preferred citable version recorded.</p>}
      </section>)}
      <section className="ro-stack" aria-label="Retractions and corrections"><h4>Retractions &amp; corrections</h4>
        {context.relations.filter((item) => warnings[item.assertion.kind]).map((item) => <Notification key={item.revisionId} tone={item.assertion.kind === "retracts" ? "danger" : "warning"} title={warnings[item.assertion.kind]!}>
          {versionLabel(context, item.assertion.source.versionId)} → {versionLabel(context, item.assertion.target.versionId)}. {label(item.assertion.knowledgeStatus)}; date: {dateLabel(item.assertion.date)}. Dependent outputs require review; history is retained.
        </Notification>)}
        {!context.relations.some((item) => warnings[item.assertion.kind]) ? <p>No sourced warning relationship is recorded in this context. This does not establish that a work has no corrections or retractions.</p> : null}
      </section>
      <DataTable caption="Current Work versions" columns={[{ id: "version", label: "Version" }, { id: "date", label: "Reported date" }, { id: "placement", label: "Membership" }, { id: "history", label: "History" }, { id: "attachment", label: "Full text" }]}
        rows={context.versions.map((version) => ({ id: version.versionId, version: versionLabel(context, version.versionId), date: dateLabel(version.definition.date),
          placement: context.placements.find((item) => item.versionId === version.versionId)?.state.replaceAll("-", " ") ?? "Requires review",
          history: <Button disabled={busy || unresolved} onClick={() => void inspect(version.revisionId)}>Inspect version history</Button>,
          attachment: <Button disabled={busy || unresolved || needsRefresh || attachmentVersionId !== null
            || !version.definition.assertionRevisionIds.some((id) => attachmentSelection(context, version.versionId, id))}
            ref={(element) => { if (element) attachmentTriggers.current.set(version.versionId, element); else attachmentTriggers.current.delete(version.versionId); }}
            onClick={() => { setAttachmentInitialSourceId(undefined); setAttachmentHandoff(null); setAttachmentVersionId(version.versionId); }}>Attach full text to this version</Button> }))} rowKey={(row) => String(row.id)} />
      {attachmentVersionId ? <DocumentAttachmentPane key={attachmentVersionId} root={root} context={context} versionId={attachmentVersionId}
        client={client} announce={announce} onClose={closeAttachment} onTaskCenter={onTaskCenter} onOpenReader={onOpenReader}
        onRecoveryContext={onAttachmentRecovery} initialSourceId={attachmentInitialSourceId} initialHandoff={attachmentHandoff} /> : null}
      {historical ? <section className="ro-stack" aria-label="Retained version history"><h4 ref={historyHeading} tabIndex={-1}>Retained version revision</h4>
        <p>{label(historical.definition.kind)} · {dateLabel(historical.definition.date)}</p><p className="ro-wrap-anywhere">Revision: {historical.revisionId}. Decision: {historical.decisionRevisionId}.</p>
        <ul>{historical.definition.assertionRevisionIds.map((id) => <li key={id} className="ro-wrap-anywhere">Source assertion: {id}</li>)}</ul>
        {historical.previousRevisionId ? <Button disabled={busy || unresolved} onClick={() => void inspect(historical.previousRevisionId!)}>Inspect earlier revision</Button> : <p>First retained revision.</p>}</section> : null}
      <details><summary>Source evidence, rights and retained decisions</summary><div className="ro-stack">
        {context.sources.map((source) => <section key={source.assertionRevisionId} className="ro-stack"><h4 className="ro-wrap-anywhere">{sourceTitle(source)}</h4>
          <p>Provider: {source.assertion.provider}. Inspection: {source.assertion.rights.inspect.value}; derivation: {source.assertion.rights.derive.value}.</p>
          <p className="ro-wrap-anywhere">Assertion: {source.assertionRevisionId}; source revision: {source.assertion.sourceRevisionId}</p>
          <dl>{[...source.assertion.fields, ...source.assertion.identifiers].map((item, index) => <div key={index}><dt className="ro-wrap-anywhere">{item.sourceSelector}</dt><dd className="import-field-value">{item.observed}</dd></div>)}</dl></section>)}
        {context.relations.map((item) => <section key={item.revisionId}><h4>{label(item.assertion.kind)} · {label(item.assertion.knowledgeStatus)}</h4>
          <p className="ro-wrap-anywhere">Exact endpoints: {item.assertion.source.revisionId} → {item.assertion.target.revisionId}. Decision: {item.decisionRevisionId}. Date: {dateLabel(item.assertion.date)}.</p>
          <ul>{item.assertion.evidence.map((proof) => <li key={`${proof.assertionRevisionId}/${proof.category}/${proof.selector}`} className="ro-wrap-anywhere">{proof.assertionRevisionId} · {proof.category} · {proof.selector} · SHA-256 {proof.valueSha256}</li>)}</ul></section>)}
        {context.preferences.map((item) => <p key={item.revisionId} className="ro-wrap-anywhere">Retained preference {item.revisionId}: Work {item.workId}, version revision {item.selected.revisionId}.</p>)}
      </div></details>
      <fieldset disabled={disabled} className="ro-stack"><legend>Human version decision</legend>
        <div className="ro-field"><label htmlFor="version-action">Version action</label><select id="version-action" value={action} onChange={(event) => { setAction(event.currentTarget.value as VersionPlan["action"]); setVersionId(""); setSources([]); }}>
          <option value="register">Register a version</option><option value="revise">Revise a version classification</option><option value="relate">Record a sourced relationship</option><option value="prefer">Choose preferred citable version</option></select></div>
        {action === "revise" || action === "prefer" ? <div className="ro-field"><label htmlFor="version-selected">Selected version</label><select id="version-selected" value={versionId} onChange={(event) => chooseVersion(event.currentTarget.value)}><option value="">Choose a version</option>{versionOptions}</select></div> : null}
        {definitionAction ? <><div className="ro-field"><label htmlFor="version-kind">Version kind</label><select id="version-kind" value={kind} onChange={(event) => setKind(event.currentTarget.value as VersionDefinition["kind"])}>{kinds.map((item) => <option key={item} value={item}>{label(item)}</option>)}</select></div>
          <p>Select the retained assertions describing this manifestation. They must belong to one current Work.</p>
          {context.sources.filter((source) => context.works.some((work) => work.assertionRevisionIds.includes(source.assertionRevisionId))).map((source) => <label key={source.assertionRevisionId} className="ro-cluster ro-wrap-anywhere"><input type="checkbox" checked={sources.includes(source.assertionRevisionId)} onChange={(event) => { const checked = event.currentTarget.checked; setSources((saved) => checked ? [...saved, source.assertionRevisionId] : saved.filter((id) => id !== source.assertionRevisionId)); }} />Version source: {sourceTitle(source).slice(0, 160)} · {source.assertionRevisionId}</label>)}
        </> : null}
        {action === "relate" ? <><div className="ro-field"><label htmlFor="version-relation">Relationship</label><select id="version-relation" value={relationKind} onChange={(event) => setRelationKind(event.currentTarget.value as UpdateRelationDraft["kind"])}>{relations.map((item) => <option key={item} value={item}>{label(item)}</option>)}</select></div>
          <div className="ro-field"><label htmlFor="version-from">From version</label><select id="version-from" value={versionId} onChange={(event) => setVersionId(event.currentTarget.value)}><option value="">Choose the originating version or notice</option>{versionOptions}</select></div>
          <div className="ro-field"><label htmlFor="version-to">To version</label><select id="version-to" value={targetId} onChange={(event) => setTargetId(event.currentTarget.value)}><option value="">Choose the affected version</option>{versionOptions}</select></div>
          <div className="ro-field"><label htmlFor="version-evidence">Retained source evidence</label><select id="version-evidence" value={evidenceKey} onChange={(event) => setEvidenceKey(event.currentTarget.value)}><option value="">Choose the source assertion supporting this relationship</option>{evidence.map((item) => <option key={item.key} value={item.key}>{item.selector} · {item.observed.slice(0, 180)} · {item.source.assertionRevisionId}</option>)}</select></div>
          {anchor ? <p className="import-field-value">{anchor.observed}</p> : null}
          <div className="ro-field"><label htmlFor="version-knowledge">Relationship evidence state</label><select id="version-knowledge" value={knowledge} onChange={(event) => setKnowledge(event.currentTarget.value as UpdateRelationDraft["knowledgeStatus"])}><option value="adjudicated">Adjudicated by researcher</option><option value="disputed">Disputed</option></select></div>
        </> : null}
        {action !== "prefer" ? <><div className="ro-field"><label htmlFor="version-date-precision">Reported date precision</label><select id="version-date-precision" value={precision} onChange={(event) => setPrecision(event.currentTarget.value as VersionDate["precision"])}>{(["not-reported", "unknown", "year", "month", "day"] as const).map((item) => <option key={item} value={item}>{label(item)}</option>)}</select></div>
          {precision !== "not-reported" && precision !== "unknown" ? <div className="ro-field"><label htmlFor="version-date">Reported date ({precision === "year" ? "YYYY" : precision === "month" ? "YYYY-MM" : "YYYY-MM-DD"})</label><input id="version-date" value={dateValue} maxLength={10} onChange={(event) => setDateValue(event.currentTarget.value)} /></div> : null}</> : null}
        <div className="ro-field"><label htmlFor="version-rationale">Version decision rationale</label><textarea id="version-rationale" maxLength={4000} value={rationale} onChange={(event) => setRationale(event.currentTarget.value)} /></div>
        {!canPreview ? <p>Provide a rationale and the source or version selections for this action. A citable preference requires exactly one Work. Leave missing dates explicitly unreported or unknown.</p> : null}
        <Button ref={previewButton} disabled={disabled || !canPreview} onClick={() => void prepare()}>Preview version decision</Button>
      </fieldset>
      {preview && !outcome ? <section className="ro-stack" aria-label="Version decision preview"><h3 ref={previewHeading} tabIndex={-1} className="ro-typography ro-typography--card-title">Version decision preview</h3>
        <p>{label(preview.plan.action)} · {preview.plan.definition ? label(preview.plan.definition.kind) : preview.plan.relation ? label(preview.plan.relation.kind) : "Preferred citable version"}. {preview.value.affectedCount} downstream object(s) require impact review.</p>
        {preview.plan.version ? <p className="ro-wrap-anywhere">Selected: {versionLabel(context, preview.plan.version.versionId)} · exact revision {preview.plan.version.revisionId}</p> : null}
        {preview.plan.definition ? <><p>Reported date: {dateLabel(preview.plan.definition.date)}</p><ul>{preview.plan.definition.assertionRevisionIds.map((id) => <li key={id} className="ro-wrap-anywhere">{sourceTitle(context.sources.find((source) => source.assertionRevisionId === id)!)} · {id}</li>)}</ul></> : null}
        {preview.plan.relation ? <><p>{versionLabel(context, preview.plan.relation.source.versionId)} → {versionLabel(context, preview.plan.relation.target.versionId)}. {label(preview.plan.relation.knowledgeStatus)}; reported date: {dateLabel(preview.plan.relation.date)}.</p>
          <ul>{preview.plan.relation.evidence.map((proof) => <li key={`${proof.assertionRevisionId}/${proof.category}/${proof.selector}`} className="ro-wrap-anywhere">{proof.selector} · {evidence.find((item) => item.source.assertionRevisionId === proof.assertionRevisionId && item.category === proof.category && item.selector === proof.selector)?.observed} · source assertion {proof.assertionRevisionId}</li>)}</ul></> : null}
        <p>{preview.plan.rationale}</p><p>Earlier revisions and warnings remain available. Dependency checks resume after interruption; saving this decision does not recalculate downstream outputs.</p>
        {command ? <Notification tone="warning" title="Version reply not yet confirmed">Retry the same saved decision before leaving. A missing reply does not mean publication failed.</Notification> : null}
        <div className="ro-action-row">{!command ? <Button disabled={busy} onClick={backToDraft}>Back to version draft</Button> : null}<Button tone="primary" disabled={busy} onClick={() => void commit()}>{command ? "Retry same version decision" : "Apply version decision"}</Button></div>
      </section> : null}
      {outcome ? <section className="ro-stack" aria-label="Saved version decision"><h3 ref={resultHeading} tabIndex={-1} className="ro-typography ro-typography--card-title">Version decision saved</h3>
        <p>{outcome.dependencyRunIds.length} durable dependency check(s) recorded. Inspect Audit &amp; Lineage before relying on affected outputs.</p>
        <p className="ro-wrap-anywhere">Decision revision: {outcome.decisionRevisionId}</p><Button disabled={busy} onClick={() => void loadContext(outcome.workStates.map((work) => work.workId))}>Review updated versions</Button>
      </section> : null}
    </>}
  </section></Panel>;
}
