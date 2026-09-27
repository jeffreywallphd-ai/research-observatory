import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { CoreApiClientError, createCoreApiClient, type CandidateExplanation, type ReconciliationInspection,
  type ReviewCommand, type ReviewContext, type ReviewOutcome, type ReviewPlan, type ReviewPreview } from "@research-observatory/contracts/core-api";
import { Button, DataTable, Notification, Panel, StatusBadge } from "@research-observatory/ui-components";
import { reconciliationReviewPlan, type ReconciliationChoice } from "./reconciliationReviewModel";

type Client = ReturnType<typeof createCoreApiClient>;
const title = (source: ReviewContext["sources"][number]) => source.assertion.fields.find((field) => field.name === "title")?.observed ?? "Title not reported";
const sourceLabel = (source: ReviewContext["sources"][number]) => `${title(source).slice(0, 100)} · ${source.assertion.provider} · source ${source.assertion.address.ordinal} · ${source.assertionRevisionId}`;

export function ReconciliationReviewPane({ root, projectId, client, initial, inspections, candidate, announce, onClose, onCommitted, onDenied }: {
  readonly root: string; readonly projectId: string; readonly client: Client; readonly initial: ReviewContext;
  readonly inspections: readonly ReconciliationInspection[]; readonly candidate: CandidateExplanation;
  readonly announce: (message: string) => void; readonly onClose: () => void; readonly onCommitted: (outcome: ReviewOutcome) => void;
  readonly onDenied: () => void;
}): ReactNode {
  const [context, setContext] = useState<ReviewContext | null>(initial);
  const initialAction = initial.works.length === 1 && initial.unassignedAssertionRevisionIds.length === 0 ? "split" : "merge";
  const [choice, setChoice] = useState<ReconciliationChoice>({ action: initialAction, survivor: initial.works[0]?.workId ?? null,
    separated: [], aliasGroups: {}, rationale: "" });
  const [busy, setBusy] = useState(false), [failure, setFailure] = useState<string | null>(null);
  const [preview, setPreview] = useState<{ value: ReviewPreview; plan: ReviewPlan } | null>(null);
  const [command, setCommand] = useState<ReviewCommand | null>(null), [outcome, setOutcome] = useState<ReviewOutcome | null>(null);
  const [sides, setSides] = useState<readonly ReconciliationInspection[]>(inspections);
  const live = useRef(true), generation = useRef(0), heading = useRef<HTMLHeadingElement>(null), previewButton = useRef<HTMLButtonElement>(null);
  const previewHeading = useRef<HTMLHeadingElement>(null), resultHeading = useRef<HTMLHeadingElement>(null);
  const plan = useMemo(() => context ? reconciliationReviewPlan(context, choice) : null, [context, choice]);
  const disabled = busy || preview !== null || command !== null || outcome !== null;
  const unresolved = command !== null && outcome === null;
  const showingScoredPair = sides.length === 2 && sides[0]?.result.assertionRevisionId !== sides[1]?.result.assertionRevisionId
    && sides.every((side) => [candidate.left, candidate.right].includes(side.result.assertionRevisionId));
  useEffect(() => { live.current = true; heading.current?.focus(); return () => { live.current = false; generation.current += 1; }; }, []);
  useEffect(() => { if (preview) previewHeading.current?.focus(); }, [preview]);
  useEffect(() => { if (outcome) resultHeading.current?.focus(); }, [outcome]);

  async function perform(action: (ticket: number) => Promise<void>): Promise<void> {
    const ticket = ++generation.current;
    setBusy(true); setFailure(null);
    try { await action(ticket); }
    catch (error) {
      if (live.current && ticket === generation.current) {
        const denied = error instanceof CoreApiClientError && error.problem.status === 403;
        if (denied) { setContext(null); setSides([]); setPreview(null); setCommand(null); setOutcome(null); onDenied(); }
        setFailure(denied ? "Current source or project access was denied. Close this comparison and check Intent and source rights."
          : "The review outcome could not be confirmed. Refresh current evidence before preparing a new decision, or retry the same saved decision if its reply was lost.");
        announce(denied ? "Reconciliation access denied." : "Reconciliation review needs attention.");
      }
    } finally { if (live.current && ticket === generation.current) setBusy(false); }
  }
  const current = (ticket: number): boolean => live.current && ticket === generation.current;
  function back(): void { setPreview(null); globalThis.requestAnimationFrame(() => { if (live.current) previewButton.current?.focus(); }); }
  function update(change: Partial<ReconciliationChoice>): void { setChoice((saved) => ({ ...saved, ...change })); setPreview(null); }
  async function loadContext(workIds: readonly string[], unassigned: readonly string[]): Promise<void> {
    await perform(async (ticket) => {
      const next = await client.inspectScholarlyReviewContext({ root, workIds, unassignedAssertionRevisionIds: unassigned });
      if (next.sources.some((source) => source.assertion.projectId !== projectId)) throw new Error("RO-CORE-RESPONSE-INVALID");
      if (!current(ticket)) return;
      setContext(next); setPreview(null); setCommand(null); setOutcome(null);
      setChoice((saved) => ({ ...saved, action: next.works.length === 1 && !next.unassignedAssertionRevisionIds.length ? "split" : "merge",
        survivor: next.works[0]?.workId ?? null, separated: [], aliasGroups: {} }));
      heading.current?.focus(); announce("Current Work membership and review evidence refreshed.");
    });
  }
  async function inspectSide(index: number, assertionRevisionId: string): Promise<void> {
    await perform(async (ticket) => {
      const inspection = await client.inspectScholarlyReconciliation({ root, assertionRevisionId });
      if (inspection.assertion.projectId !== projectId) throw new Error("RO-CORE-RESPONSE-INVALID");
      if (current(ticket)) setSides((saved) => saved.map((side, offset) => offset === index ? inspection : side));
    });
  }
  async function previewDecision(): Promise<void> {
    if (!plan || disabled) return;
    await perform(async (ticket) => {
      const next = await client.previewScholarlyReview({ root, plan });
      if (current(ticket)) { setPreview({ value: next, plan }); announce("Decision preview ready. Inspect affected objects before applying it."); }
    });
  }
  async function commitDecision(): Promise<void> {
    if (busy || !preview || outcome) return;
    const exact = command ?? { commandId: preview.value.commandId, plan: preview.plan, expectedPreviewSha256: preview.value.previewSha256 };
    setCommand(exact);
    await perform(async (ticket) => {
      const next = await client.commitScholarlyReview({ root, command: exact });
      if (current(ticket)) { setOutcome(next); onCommitted(next); announce("Human reconciliation decision saved. Original source values and earlier decisions are retained."); }
    });
  }

  return <Panel title="Review canonical identity"><section className="ro-stack ro-form" aria-label="Canonical identity review" aria-busy={busy}
    onKeyDown={(event) => { if (event.key === "Escape" && !busy && !unresolved) { event.preventDefault(); event.stopPropagation(); if (preview && !outcome) back(); else onClose(); } }}>
    <h3 ref={heading} tabIndex={-1} className="ro-typography ro-typography--card-title">Compare source assertions</h3>
    <p>Similarity suggests a review; it does not establish that these records describe the same work. Original and conflicting fields remain available after every decision.</p>
    {failure ? <Notification tone="danger" title="Review needs attention">{failure}</Notification> : null}
    {busy ? <p role="status">Checking current evidence and decision state…</p> : null}
    <div className="ro-action-row"><Button disabled={busy || unresolved} onClick={onClose}>Back to candidates</Button>
      {context && !command && !outcome ? <Button disabled={busy} onClick={() => void loadContext(context.works.map((work) => work.workId), context.unassignedAssertionRevisionIds)}>Refresh current evidence</Button> : null}</div>
    {context ? <>
      <div className="ro-grid import-comparison">{sides.map((inspection, index) => <section className="ro-stack" key={index} aria-label={`Compared source ${index + 1}`}>
        <div className="ro-field"><label htmlFor={`reconciliation-source-${index}`}>Source {index + 1}</label>
          <select id={`reconciliation-source-${index}`} disabled={busy || unresolved} value={inspection.result.assertionRevisionId} onChange={(event) => void inspectSide(index, event.currentTarget.value)}>
            {context.sources.map((source) => <option key={source.assertionRevisionId} value={source.assertionRevisionId}>{sourceLabel(source)}</option>)}
          </select></div>
        <p className="ro-wrap-anywhere">{inspection.assertion.fields.find((field) => field.name === "title")?.observed ?? "Title not reported"}</p>
        <p>Provider: {inspection.assertion.provider}. Inspection: {inspection.assertion.rights.inspect.value}; derivation: {inspection.assertion.rights.derive.value}.</p>
        <DataTable caption={`Source ${index + 1} identifier assertions`} columns={[{ id: "scheme", label: "Scheme" }, { id: "observed", label: "Original" }, { id: "normalized", label: "Normalized" }, { id: "state", label: "State" }]}
          rows={inspection.assertion.identifiers.map((identifier, ordinal) => ({ key: String(ordinal), scheme: identifier.scheme, observed: <span className="ro-wrap-anywhere">{identifier.observed}</span>,
            normalized: <span className="ro-wrap-anywhere">{inspection.normalizedIdentifiers[ordinal]?.canonical ?? "Unavailable"}</span>, state: `${identifier.verificationState}; ${inspection.normalizedIdentifiers[ordinal]?.status ?? "unavailable"}` }))} rowKey={(row) => String(row.key)} />
        <details><summary>Original fields and source provenance</summary><dl className="ro-stack">{inspection.assertion.fields.map((field, ordinal) => <div key={ordinal}>
          <dt>{field.name} · {field.origin}</dt><dd className="import-field-value">{field.observed}</dd></div>)}</dl>
          <dl className="import-rights">{Object.entries({ "Source revision": inspection.assertion.sourceRevisionId, "Source digest": inspection.assertion.sourceSha256,
            "Assertion revision": inspection.result.assertionRevisionId, "Input kind": inspection.assertion.address.kind, "Source position": inspection.assertion.address.ordinal }).map(([label, value]) => <div key={label}><dt>{label}</dt><dd className="ro-wrap-anywhere">{value}</dd></div>)}</dl>
        </details>
      </section>)}</div>
      {showingScoredPair ? <><DataTable caption="Historical candidate feature contributions" columns={[{ id: "name", label: "Feature" }, { id: "score", label: "Score / 10,000" }, { id: "weight", label: "Weight" }, { id: "state", label: "Evidence state" }]}
        rows={candidate.features.map((feature) => ({ name: feature.name, score: feature.score ?? "Not reported", weight: feature.weight, state: `${feature.state}${feature.conflict ? "; conflict retained" : ""}` }))} rowKey={(row) => String(row.name)} />
      <p>Ranking score: {candidate.score} / 10,000. This is not a probability. {candidate.flags.length ? `Flags: ${candidate.flags.join(", ")}.` : "No ranking conflict flag reported."}</p>
      <details><summary>Scoring and configuration identity</summary><p className="ro-wrap-anywhere">{candidate.algorithm} · {candidate.featureVersion} · {candidate.configurationFingerprint}</p></details></>
        : <p className="ro-wrap-anywhere">No pair score is shown for these selected sources. The historical candidate compared assertion {candidate.left} with {candidate.right}.</p>}
      <fieldset disabled={disabled} className="ro-stack"><legend>Researcher decision</legend>
        <div className="ro-field"><label htmlFor="reconciliation-action">Action</label><select id="reconciliation-action" value={choice.action} onChange={(event) => update({ action: event.currentTarget.value as ReviewPlan["action"], separated: [], aliasGroups: {} })}>
          {context.works.length + context.unassignedAssertionRevisionIds.length >= 2 ? <option value="merge">Merge into one Work</option> : null}
          {context.works.length === 1 && !context.unassignedAssertionRevisionIds.length ? <option value="split">Split into separate Works</option> : null}
          {context.unassignedAssertionRevisionIds.length > 0 && context.works.length <= 1 ? <option value="assign">Assign unassigned source assertions</option> : null}
        </select></div>
        {choice.action !== "split" ? <div className="ro-field"><label htmlFor="reconciliation-survivor">Surviving Work identity</label><select id="reconciliation-survivor" value={choice.survivor ?? ""} onChange={(event) => update({ survivor: event.currentTarget.value || null })}>
          <option value="">Create a new Work identity</option>{context.works.map((work) => <option key={work.workId} value={work.workId}>{work.workId}</option>)}</select></div> : <>
          <p>Choose the source assertions that will move to a new Work. At least one source must remain in the existing Work.</p>
          {context.sources.map((source) => <label className="ro-cluster ro-wrap-anywhere" key={source.assertionRevisionId}><input type="checkbox" checked={choice.separated.includes(source.assertionRevisionId)} onChange={(event) => update({ separated: event.currentTarget.checked ? [...choice.separated, source.assertionRevisionId] : choice.separated.filter((id) => id !== source.assertionRevisionId) })} />Move to separate Work: {sourceLabel(source)}</label>)}
          {context.inboundAliases.map((alias) => <div className="ro-field" key={alias.workId}><label htmlFor={`alias-${alias.workId}`} className="ro-wrap-anywhere">Historical alias {alias.workId}</label><select id={`alias-${alias.workId}`} value={choice.aliasGroups[alias.workId] ?? ""} onChange={(event) => update({ aliasGroups: { ...choice.aliasGroups, [alias.workId]: event.currentTarget.value } })}>
            <option value="">Choose its current destination</option><option value="retained">Retained Work</option><option value="separate">Separate Work</option></select></div>)}
        </>}
        <p>{context.sources.length} source assertions will be preserved. Conflicting source values remain recorded; this decision does not verify their scholarly claims.</p>
        <div className="ro-field"><label htmlFor="reconciliation-rationale">Decision rationale</label><textarea id="reconciliation-rationale" value={choice.rationale} maxLength={2048} onChange={(event) => update({ rationale: event.currentTarget.value })} /></div>
        <Button ref={previewButton} disabled={disabled || !plan} onClick={() => void previewDecision()}>Preview decision and affected objects</Button>
        {!plan ? <p>Provide a rationale and a complete, nonempty source partition. Each inherited alias needs an explicit destination for a split.</p> : null}
      </fieldset>
      {preview && !outcome ? <section className="ro-stack" aria-label="Reconciliation decision preview">
        <h3 ref={previewHeading} tabIndex={-1} className="ro-typography ro-typography--card-title">Apply this reviewed decision</h3>
        <p>{preview.plan.action === "split" ? "Split" : preview.plan.action === "merge" ? "Merge" : "Assign"} {context.sources.length} source assertions into {preview.plan.partitions.length} Work group(s). {preview.plan.aliases.length} alias route(s) will be recorded. Earlier identities and human decisions stay available.</p>
        <p>{preview.plan.rationale}</p>
        {preview.plan.partitions.map((part) => <section key={part.group} className="ro-stack"><h4>{part.group === "separate" ? "Separate Work" : "Retained Work"}</h4>
          <p className="ro-wrap-anywhere">{part.existingWorkId ? `Preserve identity: ${part.existingWorkId}` : "Create a new Work identity"}</p>
          <ul>{part.assertionRevisionIds.map((id) => <li key={id} className="ro-wrap-anywhere">{sourceLabel(context.sources.find((source) => source.assertionRevisionId === id)!)}</li>)}</ul>
        </section>)}
        {preview.plan.aliases.length ? <details><summary>Explicit alias destinations</summary><ul>{preview.plan.aliases.map((alias) => <li key={alias.workId} className="ro-wrap-anywhere">{alias.workId} → {alias.targetGroup === "separate" ? "Separate Work" : "Retained Work"}</li>)}</ul></details> : null}
        <RevisionList label="Affected downstream objects" revisions={preview.value.affectedOutputRevisionIds} />
        <RevisionList label="Objects with unknown impact" revisions={preview.value.unknownImpactRevisionIds} />
        <p>Downstream dependency checks are resumable. A saved identity decision does not mean downstream work is fresh or recalculated.</p>
        {command ? <Notification tone="warning" title="Decision reply not yet confirmed">Retry uses the same saved command and evidence. Confirm this result before returning to candidates. Do not assume the decision failed because its reply was lost.</Notification> : null}
        <div className="ro-action-row">{!command ? <Button disabled={busy} onClick={back}>Back to decision</Button> : null}<Button tone="primary" disabled={busy} onClick={() => void commitDecision()}>{command ? "Retry same decision" : "Apply reviewed decision"}</Button></div>
      </section> : null}
      {outcome ? <section className="ro-stack" aria-label="Saved reconciliation decision"><h3 ref={resultHeading} tabIndex={-1} className="ro-typography ro-typography--card-title">Decision saved</h3>
        <StatusBadge>Adjudicated identity · source assertions retained</StatusBadge>
        <p>{outcome.workStates.filter((work) => work.disposition === "active").length} active Work(s); {outcome.workStates.filter((work) => work.disposition === "alias").length} alias revision(s). {outcome.dependencyRunIds.length} durable dependency check(s) recorded. Inspect Audit &amp; Lineage for affected downstream work.</p>
        <p className="ro-wrap-anywhere">Decision revision: {outcome.decisionRevisionId}</p>
        <Button disabled={busy} onClick={() => void loadContext(outcome.workStates.filter((work) => work.disposition === "active").map((work) => work.workId), [])}>Review resulting Works or reverse the grouping</Button>
      </section> : null}
    </> : null}
  </section></Panel>;
}

function RevisionList({ label, revisions }: { readonly label: string; readonly revisions: readonly string[] }): ReactNode {
  const [offset, setOffset] = useState(0);
  return <section className="ro-stack" aria-label={label}><h4>{label}: {revisions.length}</h4>
    {revisions.length ? <><ul>{revisions.slice(offset, offset + 50).map((revision) => <li className="ro-wrap-anywhere" key={revision}>{revision}</li>)}</ul>
      <nav className="ro-action-row" aria-label={`${label} pages`}><Button disabled={offset === 0} onClick={() => setOffset(offset - 50)}>Previous objects</Button><Button disabled={offset + 50 >= revisions.length} onClick={() => setOffset(offset + 50)}>Next objects</Button></nav></> : <p>None reported by this preview.</p>}
  </section>;
}
