import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  CoreApiClientError,
  createCoreApiClient,
  type CoreApiTransport,
  type ProjectProjection,
} from "@research-observatory/contracts/core-api";
import type {
  CorpusReportDrillPage,
  CorpusReportFilter,
  CorpusReportSnapshot,
  CoverageSummary,
  ReportDimension,
  ReportPath,
  ReportState,
} from "@research-observatory/contracts/corpus-reports";
import { Button, Notification, Panel, StatusBadge, Typography } from "@research-observatory/ui-components";
import { packagedProjectTransport } from "./ProjectsWorkspace";
import type { ApplicationWorkspace } from "./workflowNavigationModel";

const FIELD_STATES = ["known", "not-reported", "unknown", "unavailable"] as const;

export interface CorpusCanvasReportTransport {
  create(request: { readonly root: string; readonly commandId: string }): Promise<CorpusReportSnapshot>;
  inspect(request: { readonly root: string; readonly snapshotId: string }): Promise<CorpusReportSnapshot>;
  drill(request: { readonly root: string; readonly snapshotId: string; readonly filter: CorpusReportFilter; readonly cursor: string | null; readonly limit: number }): Promise<CorpusReportDrillPage>;
}

export type CorpusReportRecoveryStorage = Pick<Storage, "getItem" | "setItem">;
export interface CorpusReportRecoveryState {
  readonly pendingCommandId: string | null;
  readonly lastVerifiedSnapshotId: string | null;
}
type CorpusOperation = "create" | "inspect" | "drill";
type RecoveryControl = "generate" | "open" | "storage";

interface CorpusCanvasProps {
  readonly project: ProjectProjection | null;
  readonly announce: (message: string) => void;
  readonly active?: boolean;
  readonly onNavigate?: (workspace: ApplicationWorkspace) => void;
  readonly transport?: CoreApiTransport;
  readonly reportTransport?: CorpusCanvasReportTransport;
  readonly recoveryStorage?: CorpusReportRecoveryStorage;
  readonly initialSnapshot?: CorpusReportSnapshot;
  readonly initialDrill?: CorpusReportDrillPage;
}

const ALL_FILTER: CorpusReportFilter = Object.freeze({
  kind: "all", membership: null, sourceKey: null, route: null, leftSourceKey: null, rightSourceKey: null,
  leftRoute: null, rightRoute: null, dimension: null, state: null, value: null,
});
function reportFilter(kind: CorpusReportFilter["kind"], fields: Partial<Omit<CorpusReportFilter, "kind">> = {}): CorpusReportFilter {
  return { ...ALL_FILTER, kind, ...fields };
}
const readableDimension = (dimension: ReportDimension): string => ({
  identifier: "Identifier", year: "Year", venue: "Venue", language: "Language",
  discipline: "Discipline", oa: "Open access", "full-text": "Full text",
})[dimension];
const readableState = (state: ReportState): string => ({
  known: "Known", "not-reported": "Not reported", unknown: "Unknown", unavailable: "Unavailable",
})[state];
const coverageCount = (entry: CoverageSummary, state: ReportState): number => (
  state === "not-reported" ? entry.notReported : entry[state]
);
const displaySource = (sourceKey: string | null): string => sourceKey ?? "Unattributed source";
const displayValue = (value: string | null): string => value ?? "No reported value";

export function ReportPathStatus({ path }: { readonly path: ReportPath }): ReactNode {
  return <>
    Metadata assertion: {path.metadataAssertionStatus === "retained" ? "retained" : "no external assertion"}.<br />
    Report-metadata inspection: {path.reportInspectStatus === "allowed" ? <>allowed under policy <code>{path.rightsPolicyRevisionId}</code>{path.rightsExpiresAt ? <> until <time dateTime={path.rightsExpiresAt}>{path.rightsExpiresAt}</time></> : null}</> : "unassessed for this path"}.<br />
    Source full-text copy: {path.sourceCopyAvailability}.
  </>;
}

export function sourceBoundaryComparison(
  snapshot: Pick<CorpusReportSnapshot, "memberCount" | "discoveryPathCount" | "sourceContributions" | "sourceOverlaps">,
  firstSource: string,
  secondSource: string | null,
): {
  readonly firstCount: number; readonly secondCount: number; readonly sharedCount: number | null;
  readonly firstPathCount: number; readonly secondPathCount: number; readonly sharedPathPairCount: number | null;
} | null {
  const first = snapshot.sourceContributions.find((entry) => entry.sourceKey === firstSource);
  if (!first) return null;
  if (secondSource === null) {
    return { firstCount: snapshot.memberCount, secondCount: first.itemCount, sharedCount: null,
      firstPathCount: snapshot.discoveryPathCount, secondPathCount: first.discoveryPathCount,
      sharedPathPairCount: null };
  }
  const second = snapshot.sourceContributions.find((entry) => entry.sourceKey === secondSource);
  if (!second || secondSource === firstSource) return null;
  const overlap = snapshot.sourceOverlaps.find((entry) =>
    entry.leftSourceKey === firstSource && entry.rightSourceKey === secondSource
    || entry.leftSourceKey === secondSource && entry.rightSourceKey === firstSource,
  );
  return { firstCount: first.itemCount, secondCount: second.itemCount, sharedCount: overlap?.itemCount ?? 0,
    firstPathCount: first.discoveryPathCount, secondPathCount: second.discoveryPathCount,
    sharedPathPairCount: overlap?.discoveryPathPairCount ?? 0 };
}

function filterKey(filter: CorpusReportFilter): string {
  return JSON.stringify([
    filter.kind, filter.membership, filter.sourceKey, filter.leftSourceKey, filter.rightSourceKey,
    filter.route, filter.leftRoute, filter.rightRoute, filter.dimension, filter.state, filter.value,
  ]);
}

export function drillMatchesSelection(
  snapshot: Pick<CorpusReportSnapshot, "snapshotId" | "projectId">,
  filter: CorpusReportFilter,
  page: Pick<CorpusReportDrillPage, "snapshotId" | "projectId" | "filter">,
): boolean {
  return page.snapshotId === snapshot.snapshotId
    && page.projectId === snapshot.projectId
    && filterKey(page.filter) === filterKey(filter);
}

export function corpusReportCommandId(pending: string | null): string {
  if (pending) return pending;
  const bytes = globalThis.crypto.getRandomValues(new Uint8Array(16));
  let timestamp = Date.now();
  for (let index = 5; index >= 0; index -= 1) {
    bytes[index] = timestamp & 0xff;
    timestamp = Math.floor(timestamp / 256);
  }
  bytes[6] = ((bytes[6] ?? 0) & 0x0f) | 0x70;
  bytes[8] = ((bytes[8] ?? 0) & 0x3f) | 0x80;
  const hex = Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

const RECOVERY_PREFIX = "research-observatory.corpus-report.v1";
const UUID7 = /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const EMPTY_RECOVERY: CorpusReportRecoveryState = Object.freeze({ pendingCommandId: null, lastVerifiedSnapshotId: null });

function recoveryKey(project: Pick<ProjectProjection, "projectId" | "root">): string {
  return `${RECOVERY_PREFIX}.${project.projectId}.${encodeURIComponent(project.root)}`;
}

function recoveryUnavailable(): Error {
  return new Error("RO-CORPUS-LOCAL-RECOVERY-UNAVAILABLE");
}

export function readCorpusReportRecovery(
  storage: CorpusReportRecoveryStorage | null,
  project: Pick<ProjectProjection, "projectId" | "root">,
): CorpusReportRecoveryState {
  if (!storage) throw recoveryUnavailable();
  try {
    const value = storage.getItem(recoveryKey(project));
    if (value === null) return EMPTY_RECOVERY;
    const parsed: unknown = JSON.parse(value);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw recoveryUnavailable();
    const record = parsed as Record<string, unknown>;
    if (record.version !== 1 || Object.keys(record).sort().join("|") !== "lastVerifiedSnapshotId|pendingCommandId|version"
      || record.pendingCommandId !== null && (typeof record.pendingCommandId !== "string" || !UUID7.test(record.pendingCommandId))
      || record.lastVerifiedSnapshotId !== null && (typeof record.lastVerifiedSnapshotId !== "string" || !UUID7.test(record.lastVerifiedSnapshotId))) throw recoveryUnavailable();
    return { pendingCommandId: record.pendingCommandId as string | null, lastVerifiedSnapshotId: record.lastVerifiedSnapshotId as string | null };
  } catch {
    throw recoveryUnavailable();
  }
}

function writeCorpusReportRecovery(
  storage: CorpusReportRecoveryStorage | null,
  project: Pick<ProjectProjection, "projectId" | "root">,
  value: CorpusReportRecoveryState,
): void {
  if (!storage) throw recoveryUnavailable();
  try {
    const serialized = JSON.stringify({ version: 1, pendingCommandId: value.pendingCommandId, lastVerifiedSnapshotId: value.lastVerifiedSnapshotId });
    storage.setItem(recoveryKey(project), serialized);
    if (storage.getItem(recoveryKey(project)) !== serialized) throw recoveryUnavailable();
  } catch {
    throw recoveryUnavailable();
  }
}

export function rememberVerifiedCorpusReportSnapshot(
  storage: CorpusReportRecoveryStorage | null,
  project: Pick<ProjectProjection, "projectId" | "root">,
  snapshotId: string,
  completedCommandId?: string,
): boolean {
  if (!UUID7.test(snapshotId)) return false;
  try {
    const prior = readCorpusReportRecovery(storage, project);
    writeCorpusReportRecovery(storage, project, {
      pendingCommandId: completedCommandId && prior.pendingCommandId === completedCommandId ? null : prior.pendingCommandId,
      lastVerifiedSnapshotId: snapshotId,
    });
    return true;
  } catch {
    return false;
  }
}

export async function createCorpusReportWithRecovery(
  storage: CorpusReportRecoveryStorage | null,
  project: Pick<ProjectProjection, "projectId" | "root">,
  create: CorpusCanvasReportTransport["create"],
  isCurrent: () => boolean = () => true,
): Promise<{ readonly snapshot: CorpusReportSnapshot; readonly commandId: string; readonly recoverySaved: boolean }> {
  const prior = readCorpusReportRecovery(storage, project);
  const commandId = corpusReportCommandId(prior.pendingCommandId);
  writeCorpusReportRecovery(storage, project, { ...prior, pendingCommandId: commandId });
  const snapshot = await create({ root: project.root, commandId });
  if (snapshot.projectId !== project.projectId) throw new Error("RO-CORE-RESPONSE-INVALID");
  return {
    snapshot,
    commandId,
    recoverySaved: isCurrent() && rememberVerifiedCorpusReportSnapshot(storage, project, snapshot.snapshotId, commandId),
  };
}

export function recoveryActionForInterruptedOperation(operation: CorpusOperation | null): RecoveryControl | null {
  return operation === "create" ? "generate" : operation ? "open" : null;
}

export function suspendedCorpusReportState(operation: CorpusOperation | null): {
  readonly reportState: "interrupted";
  readonly drillState: "idle";
  readonly focus: RecoveryControl;
} | null {
  const focus = recoveryActionForInterruptedOperation(operation);
  return focus ? { reportState: "interrupted", drillState: "idle", focus } : null;
}

export function focusCorpusRecoveryControl(
  target: RecoveryControl,
  controls: Readonly<Record<RecoveryControl, Pick<HTMLButtonElement, "disabled" | "focus"> | null>>,
): boolean {
  const control = controls[target];
  if (!control || control.disabled) return false;
  control.focus();
  return true;
}

function browserRecoveryStorage(): CorpusReportRecoveryStorage | null {
  try { return globalThis.window?.localStorage ?? null; } catch { return null; }
}

function failureKind(error: unknown): "denied" | "failed" {
  return error instanceof CoreApiClientError && [401, 403, 404].includes(error.problem.status) ? "denied" : "failed";
}

function defaultReportTransport(transport: CoreApiTransport): CorpusCanvasReportTransport {
  const client = createCoreApiClient(transport);
  return {
    create: (request) => client.createCorpusReport(request),
    inspect: (request) => client.inspectCorpusReport(request),
    drill: (request) => client.drillCorpusReport(request),
  };
}

export function CorpusCanvasWorkspace(props: CorpusCanvasProps): ReactNode {
  const project = props.project;
  if (!project?.open) return <Notification tone="info" title="No project open">Open a local project to inspect its corpus.</Notification>;
  if (project.compatibilityState !== "compatible") return <Notification tone="warning" title="Corpus report unavailable">Open a compatible project before inspecting corpus reports.</Notification>;
  return <CorpusProject key={`${project.projectId}\u0000${project.root}`} {...props} project={project} />;
}

function CorpusProject({
  project, announce, active = true, onNavigate, transport = packagedProjectTransport,
  reportTransport, recoveryStorage, initialSnapshot, initialDrill,
}: CorpusCanvasProps & { readonly project: ProjectProjection }): ReactNode {
  const api = useMemo(() => reportTransport ?? defaultReportTransport(transport), [reportTransport, transport]);
  const store = useMemo(() => recoveryStorage ?? browserRecoveryStorage(), [recoveryStorage]);
  const initialRecovery = useMemo(() => {
    try { return readCorpusReportRecovery(store, project); } catch { return null; }
  }, [store, project.projectId, project.root]);
  const initialValid = initialSnapshot?.projectId === project.projectId ? initialSnapshot : null;
  const [snapshot, setSnapshot] = useState<CorpusReportSnapshot | null>(initialValid);
  const [reportState, setReportState] = useState<"idle" | "loading" | "denied" | "failed" | "interrupted" | "storage-unavailable">(initialRecovery ? "idle" : "storage-unavailable");
  const [storageReady, setStorageReady] = useState(initialRecovery !== null);
  const [snapshotInput, setSnapshotInput] = useState(initialRecovery?.lastVerifiedSnapshotId ?? "");
  const [selectedFilter, setSelectedFilter] = useState<CorpusReportFilter>(ALL_FILTER);
  const [selectionLabel, setSelectionLabel] = useState("All canonical items");
  const [page, setPage] = useState<CorpusReportDrillPage | null>(
    initialValid && initialDrill && drillMatchesSelection(initialValid, ALL_FILTER, initialDrill) ? initialDrill : null,
  );
  const [drillState, setDrillState] = useState<"idle" | "loading" | "denied" | "failed">("idle");
  const [cursorStack, setCursorStack] = useState<readonly (string | null)[]>([null]);
  const [selectedItemId, setSelectedItemId] = useState<string | null>(null);
  const [sourceOverlapPage, setSourceOverlapPage] = useState(0);
  const [boundaryFirst, setBoundaryFirst] = useState<string>(initialValid?.sourceContributions[0]?.sourceKey ?? "");
  const [boundarySecond, setBoundarySecond] = useState<string>(initialValid?.sourceContributions[1]?.sourceKey ?? "");
  const live = useRef(active);
  const reportGeneration = useRef(0);
  const drillGeneration = useRef(0);
  const pendingCommandId = useRef<string | null>(initialRecovery?.pendingCommandId ?? null);
  const operation = useRef<{ readonly kind: CorpusOperation; readonly snapshotId: string | null } | null>(null);
  const drillHeading = useRef<HTMLHeadingElement>(null);
  const detailHeading = useRef<HTMLHeadingElement>(null);
  const membershipHeading = useRef<HTMLHeadingElement>(null);
  const sourceOverlapRegion = useRef<HTMLDivElement>(null);
  const boundaryRegion = useRef<HTMLDivElement>(null);
  const focusDrill = useRef(false);
  const focusDetail = useRef(false);
  const focusSourceOverlap = useRef(false);
  const generateRecoveryButton = useRef<HTMLButtonElement>(null);
  const openRecoveryButton = useRef<HTMLButtonElement>(null);
  const storageRecoveryButton = useRef<HTMLButtonElement>(null);
  const recoveryFocus = useRef<RecoveryControl | null>(null);
  const [recoveryFocusRevision, setRecoveryFocusRevision] = useState(0);
  const selectedMember = page?.members.find((member) => member.itemId === selectedItemId) ?? null;
  const sourceKeys = snapshot?.sourceContributions.map((entry) => entry.sourceKey) ?? [];
  const firstSource = sourceKeys.includes(boundaryFirst) ? boundaryFirst : sourceKeys[0] ?? "";
  const secondSource = sourceKeys.length > 1
    ? sourceKeys.includes(boundarySecond) && boundarySecond !== firstSource
      ? boundarySecond : sourceKeys.find((key) => key !== firstSource) ?? ""
    : null;
  const boundary = snapshot && firstSource
    ? sourceBoundaryComparison(snapshot, firstSource, secondSource)
    : null;

  function focusRecoveryControl(control: RecoveryControl): void {
    recoveryFocus.current = control;
    setRecoveryFocusRevision((value) => value + 1);
  }

  useEffect(() => {
    live.current = active;
    if (!active) {
      reportGeneration.current += 1; drillGeneration.current += 1;
      const interrupted = operation.current;
      operation.current = null;
      if (interrupted) {
        clearVisibleReport(interrupted.snapshotId);
        const recovery = suspendedCorpusReportState(interrupted.kind);
        if (recovery) {
          setReportState(recovery.reportState); setDrillState(recovery.drillState);
          focusRecoveryControl(recovery.focus);
        }
        try { pendingCommandId.current = readCorpusReportRecovery(store, project).pendingCommandId; }
        catch { setStorageReady(false); setReportState("storage-unavailable"); focusRecoveryControl("storage"); }
      }
    }
    return () => { live.current = false; reportGeneration.current += 1; drillGeneration.current += 1; };
  }, [active, store, project.projectId, project.root]);
  useEffect(() => {
    if (!active || !recoveryFocus.current) return;
    const target = recoveryFocus.current;
    if (focusCorpusRecoveryControl(target, {
      generate: generateRecoveryButton.current,
      open: openRecoveryButton.current,
      storage: storageRecoveryButton.current,
    })) {
      recoveryFocus.current = null;
    }
  }, [active, reportState, recoveryFocusRevision]);
  useEffect(() => {
    if (focusDrill.current && page && drillState === "idle") {
      focusDrill.current = false;
      drillHeading.current?.focus();
    }
  }, [page, drillState]);
  useEffect(() => {
    if (focusDetail.current && selectedMember) {
      focusDetail.current = false;
      detailHeading.current?.focus();
    }
  }, [selectedMember]);
  useEffect(() => {
    if (focusSourceOverlap.current) {
      focusSourceOverlap.current = false;
      sourceOverlapRegion.current?.focus();
    }
  }, [sourceOverlapPage]);

  function clearVisibleReport(snapshotId: string | null): void {
    ++drillGeneration.current;
    if (snapshotId) setSnapshotInput(snapshotId);
    setSnapshot(null); setPage(null); setSelectedItemId(null);
    setSelectedFilter(ALL_FILTER); setSelectionLabel("All canonical items");
    setCursorStack([null]);
  }

  async function loadDrill(nextSnapshot: CorpusReportSnapshot, filter: CorpusReportFilter, cursor: string | null, pageNumber: number): Promise<void> {
    const generation = ++drillGeneration.current;
    operation.current = { kind: "drill", snapshotId: nextSnapshot.snapshotId };
    setDrillState("loading"); setPage(null); setSelectedItemId(null);
    try {
      const result = await api.drill({ root: project.root, snapshotId: nextSnapshot.snapshotId, filter, cursor, limit: 50 });
      if (!live.current || generation !== drillGeneration.current) return;
      if (!drillMatchesSelection(nextSnapshot, filter, result) || result.total > nextSnapshot.memberCount || result.members.length > 50
        || result.members.some((member) => member.snapshotId !== nextSnapshot.snapshotId || member.projectId !== project.projectId)) throw new Error("RO-CORE-RESPONSE-INVALID");
      operation.current = null;
      setPage(result); setDrillState("idle");
      announce(`${selectionLabelFor(filter, nextSnapshot)}: ${result.total} canonical item${result.total === 1 ? "" : "s"} in this saved report. Page ${pageNumber} loaded.`);
    } catch (error) {
      if (!live.current || generation !== drillGeneration.current) return;
      operation.current = null;
      const kind = failureKind(error);
      clearVisibleReport(nextSnapshot.snapshotId);
      setDrillState(kind); setReportState(kind);
      focusRecoveryControl("open");
      announce("Corpus record drill is unavailable. Reopen the saved snapshot to verify current access before inspecting records.");
    }
  }

  function acceptSnapshot(result: CorpusReportSnapshot): void {
    if (result.projectId !== project.projectId) throw new Error("RO-CORE-RESPONSE-INVALID");
    ++drillGeneration.current;
    setSnapshot(result); setReportState("idle"); setSelectedFilter(ALL_FILTER);
    setSelectionLabel("All canonical items"); setCursorStack([null]); setSelectedItemId(null);
    setSourceOverlapPage(0);
    setBoundaryFirst(result.sourceContributions[0]?.sourceKey ?? "");
    setBoundarySecond(result.sourceContributions[1]?.sourceKey ?? "");
    setSnapshotInput(result.snapshotId);
    setPage(null); setDrillState("idle"); focusDrill.current = false;
    announce(`Corpus report saved with ${result.memberCount} canonical item${result.memberCount === 1 ? "" : "s"}.`);
    void loadDrill(result, ALL_FILTER, null, 1);
  }

  async function generate(): Promise<void> {
    if (!live.current || !storageReady || operation.current || reportState === "loading" || project.accessMode !== "read-write") return;
    const generation = ++reportGeneration.current;
    operation.current = { kind: "create", snapshotId: snapshot?.snapshotId ?? null };
    setReportState("loading");
    try {
      const result = await createCorpusReportWithRecovery(
        store, project, api.create, () => live.current && generation === reportGeneration.current,
      );
      if (!live.current || generation !== reportGeneration.current) return;
      operation.current = null;
      pendingCommandId.current = result.recoverySaved ? null : result.commandId;
      acceptSnapshot(result.snapshot);
      if (!result.recoverySaved) {
        setStorageReady(false); setReportState("storage-unavailable");
        focusRecoveryControl("storage");
      }
    } catch (error) {
      if (!live.current || generation !== reportGeneration.current) return;
      operation.current = null;
      clearVisibleReport(snapshot?.snapshotId ?? null);
      try { pendingCommandId.current = readCorpusReportRecovery(store, project).pendingCommandId; }
      catch { setStorageReady(false); }
      if (error instanceof Error && error.message === "RO-CORPUS-LOCAL-RECOVERY-UNAVAILABLE") {
        setStorageReady(false); setReportState("storage-unavailable"); focusRecoveryControl("storage");
        announce("Local report recovery storage is unavailable. No report creation request was sent.");
      } else {
        setReportState(failureKind(error)); focusRecoveryControl(storageReady ? "generate" : "storage");
        announce("Corpus report generation is unavailable. Retrying will use the same request identity.");
      }
    }
  }

  async function openSaved(): Promise<void> {
    if (!live.current || operation.current || reportState === "loading" || !snapshotInput.trim()) return;
    const generation = ++reportGeneration.current;
    operation.current = { kind: "inspect", snapshotId: snapshotInput.trim() };
    setReportState("loading");
    try {
      const result = await api.inspect({ root: project.root, snapshotId: snapshotInput.trim() });
      if (!live.current || generation !== reportGeneration.current) return;
      if (result.snapshotId !== snapshotInput.trim()) throw new Error("RO-CORE-RESPONSE-INVALID");
      operation.current = null;
      const saved = rememberVerifiedCorpusReportSnapshot(store, project, result.snapshotId);
      acceptSnapshot(result);
      if (!saved) { setStorageReady(false); setReportState("storage-unavailable"); focusRecoveryControl("storage"); }
    } catch (error) {
      if (!live.current || generation !== reportGeneration.current) return;
      operation.current = null;
      clearVisibleReport(snapshotInput.trim());
      setReportState(failureKind(error)); focusRecoveryControl("open");
      announce("Saved corpus report could not be opened.");
    }
  }

  function retryLocalRecovery(): void {
    try {
      const state = readCorpusReportRecovery(store, project);
      writeCorpusReportRecovery(store, project, state);
      pendingCommandId.current = state.pendingCommandId;
      if (!snapshotInput.trim() && state.lastVerifiedSnapshotId) setSnapshotInput(state.lastVerifiedSnapshotId);
      setStorageReady(true); setReportState((current) => current === "storage-unavailable" ? "idle" : current);
      focusRecoveryControl(state.pendingCommandId ? "generate" : "open");
      announce("Local report recovery is available again.");
    } catch {
      setStorageReady(false); setReportState("storage-unavailable");
      focusRecoveryControl("storage");
      announce("Local report recovery is still unavailable.");
    }
  }

  function selectFilter(filter: CorpusReportFilter, label: string): void {
    if (!snapshot || !live.current) return;
    focusDrill.current = true;
    setSelectedFilter(filter); setSelectionLabel(label); setCursorStack([null]);
    void loadDrill(snapshot, filter, null, 1);
  }

  function nextPage(): void {
    if (!snapshot || !page?.nextCursor || drillState === "loading") return;
    const cursors = [...cursorStack, page.nextCursor];
    setCursorStack(cursors); focusDrill.current = true;
    void loadDrill(snapshot, selectedFilter, page.nextCursor, cursors.length);
  }

  function previousPage(): void {
    if (!snapshot || cursorStack.length < 2 || drillState === "loading") return;
    const cursors = cursorStack.slice(0, -1);
    setCursorStack(cursors); focusDrill.current = true;
    void loadDrill(snapshot, selectedFilter, cursors[cursors.length - 1] ?? null, cursors.length);
  }

  return <div className="ro-page-region corpus-canvas" data-corpus-canvas>
    <header className="page-header">
      <Typography as="h1" variant="page-title">Corpus Canvas</Typography>
      <Typography className="page-subtitle">Inspect retained discovery paths, source overlap, coverage and missingness in an immutable local report.</Typography>
      <div className="ro-action-row">
        <Button disabled={!snapshot || !boundary} onClick={() => { boundaryRegion.current?.focus(); announce("Source-boundary comparison in this saved corpus report."); }}>Compare boundary</Button>
        <Button onClick={() => onNavigate?.("imports")} disabled={!onNavigate}>Add records</Button>
        <Button ref={generateRecoveryButton} data-corpus-recovery="generate" tone="primary" onClick={() => void generate()} disabled={!active || !storageReady || reportState === "loading" || project.accessMode !== "read-write"}>
          {pendingCommandId.current ? "Retry generation" : snapshot ? "Generate new report" : "Generate report"}
        </Button>
      </div>
    </header>
    <div className="corpus-snapshot-open ro-card ro-stack">
      <label htmlFor="corpus-snapshot-id">Open saved report by snapshot ID</label>
      <div className="ro-action-row">
        <input id="corpus-snapshot-id" type="text" value={snapshotInput} onChange={(event) => setSnapshotInput(event.currentTarget.value)} autoComplete="off" spellCheck={false} />
        <Button ref={openRecoveryButton} data-corpus-recovery="open" onClick={() => void openSaved()} disabled={!active || !snapshotInput.trim() || reportState === "loading"}>Open saved report</Button>
      </div>
      {project.accessMode !== "read-write" ? <p>Report generation requires a writable project. Core determines whether saved-snapshot inspection is available.</p> : null}
    </div>
    {reportState === "loading" ? <p role="status">Loading corpus report…</p> : null}
    {reportState === "interrupted" ? <Notification tone="warning" title="Report action interrupted">Settings interrupted the pending report action. Retry generation with its saved request identity, or reopen the saved snapshot to verify current access.</Notification> : null}
    {!storageReady ? <Notification tone="warning" title="Local report recovery unavailable">Report creation is paused because its request identity cannot be durably saved. Saved-snapshot inspection still requires a fresh Core authorization check. <Button ref={storageRecoveryButton} data-corpus-recovery="storage" onClick={retryLocalRecovery} disabled={!active}>Retry local recovery</Button></Notification> : null}
    {reportState === "denied" ? <Notification tone="warning" title="Corpus report inaccessible">Core did not make this report available to the open project. Check the snapshot ID, project access and rights before retrying.</Notification> : null}
    {reportState === "failed" ? <Notification tone="warning" title="Corpus report unavailable">The local service did not return a verified report. {pendingCommandId.current ? "Retry generation with the same request identity, or open a saved snapshot by ID." : "Open a saved snapshot by ID to verify current access, or generate a new report."}</Notification> : null}
    {snapshot ? <div className="corpus-report-content ro-stack">
      <Panel title="Report snapshot">
        <p>This is an immutable report captured at the time shown. Later corpus changes require a new report.</p>
        <dl className="ro-key-value">
          <dt>Canonical items</dt><dd>{snapshot.memberCount}</dd>
          <dt>Discovery paths</dt><dd>{snapshot.discoveryPathCount}</dd>
          <dt>Captured</dt><dd><time dateTime={snapshot.createdAt}>{snapshot.createdAt}</time></dd>
          <dt>Snapshot ID</dt><dd><code>{snapshot.snapshotId}</code></dd>
          <dt>Report rule</dt><dd>{snapshot.ruleVersion}</dd>
          {snapshot.membersSha256 ? <><dt>Member set digest</dt><dd><code>{snapshot.membersSha256}</code></dd></> : null}
          <dt>Intent revision</dt><dd><code>{snapshot.intentRevisionId}</code></dd>
          <dt>Protocol revision</dt><dd><code>{snapshot.protocolRevisionId}</code></dd>
        </dl>
      </Panel>
      <div className="corpus-toolbar" role="toolbar" aria-label="Corpus Canvas views">
        <Button disabled title="Semantic clusters unavailable">Semantic clusters</Button>
        <Button disabled title="Citation neighborhoods unavailable">Citation neighborhoods</Button>
        <Button aria-pressed={selectedFilter.kind === "all"} onClick={() => selectFilter(ALL_FILTER, "All canonical items")}>Discovery paths</Button>
        <Button onClick={() => membershipHeading.current?.focus()}>Inclusion state</Button>
        <span className="corpus-toolbar-note">Color and size encodings are unavailable without a verified network.</span>
      </div>
      <div className="corpus-main-grid">
        <section className="ro-card ro-stack corpus-network-stage" aria-labelledby="corpus-paths-heading">
          <Typography id="corpus-paths-heading" as="h2" variant="section-title">Discovery paths</Typography>
          <StatusBadge tone="neutral">Semantic clusters unavailable</StatusBadge>
          <p>No semantic or citation network has been calculated for this report. The table is the accessible inspection view.</p>
          <table className="ro-table"><caption>Retained discovery route contributions</caption><thead><tr><th scope="col">Route</th><th scope="col">Canonical items</th><th scope="col">Discovery paths</th><th scope="col">Inspect</th></tr></thead>
            <tbody>{snapshot.routeContributions.map((entry) => <tr key={entry.route}><th scope="row">{entry.route}</th><td>{entry.itemCount}</td><td>{entry.discoveryPathCount}</td><td><Button aria-label={`Inspect ${entry.route} route items`} onClick={() => selectFilter(reportFilter("route", { route: entry.route }), `${entry.route} route`)}>Inspect items</Button></td></tr>)}</tbody>
          </table>
          {snapshot.routeContributions.length === 0 ? <p>No retained discovery paths are represented in this snapshot.</p> : null}
          {snapshot.routeOverlaps.length ? <table className="ro-table"><caption>Items shared by discovery route pairs</caption><thead><tr><th scope="col">Route pair</th><th scope="col">Canonical items</th><th scope="col">Discovery path pairs</th><th scope="col">Inspect</th></tr></thead><tbody>{snapshot.routeOverlaps.map((entry) => <tr key={JSON.stringify([entry.leftRoute, entry.rightRoute])}><th scope="row">{entry.leftRoute} + {entry.rightRoute}</th><td>{entry.itemCount}</td><td>{entry.discoveryPathPairCount}</td><td><Button aria-label={`Inspect overlap between ${entry.leftRoute} and ${entry.rightRoute} routes`} onClick={() => selectFilter(reportFilter("route-overlap", { leftRoute: entry.leftRoute, rightRoute: entry.rightRoute }), `Routes ${entry.leftRoute} and ${entry.rightRoute}`)}>Inspect items</Button></td></tr>)}</tbody></table> : null}
          <section className="ro-stack corpus-drill" aria-labelledby="corpus-drill-heading">
            <h3 id="corpus-drill-heading" ref={drillHeading} tabIndex={-1} className="corpus-focus-heading">Record drill: {selectionLabel}</h3>
            {drillState === "loading" ? <p role="status">Loading exact report records…</p> : null}
            {drillState === "denied" ? <Notification tone="warning" title="Record drill denied">Core did not authorize these records.</Notification> : null}
            {drillState === "failed" ? <Notification tone="warning" title="Record drill unavailable">The selected records could not be verified from this snapshot.</Notification> : null}
            {(drillState === "failed" || drillState === "denied") ? <Button onClick={() => { if (snapshot) void loadDrill(snapshot, selectedFilter, cursorStack[cursorStack.length - 1] ?? null, cursorStack.length); }}>Retry record drill</Button> : null}
            {page ? <><p role="status">{page.total} canonical item{page.total === 1 ? "" : "s"} match this exact filter. Page {cursorStack.length}.</p>
              {page.members.length ? <div className="ro-table-scroll" tabIndex={0} aria-label="Corpus record drill table scroll region"><table className="ro-table"><caption>Records in {selectionLabel}</caption><thead><tr><th scope="col">Canonical record</th><th scope="col">Membership</th><th scope="col">Discovery paths</th><th scope="col">Inspect</th></tr></thead><tbody>
                {page.members.map((member) => <tr key={member.itemRevisionId}><th scope="row">{member.displayLabel ?? <code>{member.itemId}</code>}</th><td>{member.membership}</td><td>{member.paths.length}</td><td><Button aria-pressed={member.itemId === selectedItemId} aria-label={`Inspect record ${member.displayLabel ?? member.itemId}`} onClick={() => { focusDetail.current = true; setSelectedItemId(member.itemId); announce("Record source and field witnesses selected."); }}>Inspect record</Button></td></tr>)}
              </tbody></table></div> : <p>No records match this exact filter in this saved snapshot.</p>}
              <div className="ro-action-row"><Button disabled={cursorStack.length < 2} onClick={previousPage}>Previous records</Button><Button disabled={!page.nextCursor} onClick={nextPage}>Next records</Button></div>
            </> : null}
          </section>
        </section>
        <aside className="ro-stack corpus-inspection" aria-label="Corpus inspection">
          <Panel title="Selected cluster"><StatusBadge tone="neutral">Unavailable</StatusBadge><p>No semantic or citation cluster has been computed for this snapshot. Select a canonical record below for exact source inspection.</p></Panel>
          <Panel title="Selected records">
            {selectedMember ? <div className="ro-stack">
              <h3 ref={detailHeading} tabIndex={-1} className="corpus-focus-heading">{selectedMember.displayLabel ?? selectedMember.itemId}</h3>
              <dl className="ro-key-value">
                <dt>Item revision</dt><dd><code>{selectedMember.itemRevisionId}</code></dd>
                <dt>Work revision</dt><dd><code>{selectedMember.workRevisionId}</code></dd>
                <dt>Membership</dt><dd>{selectedMember.membership}</dd>
                <dt>Duplicate link</dt><dd>{selectedMember.duplicateOfItemId ? <code>{selectedMember.duplicateOfItemId}</code> : "None recorded"}</dd>
              </dl>
              <h4>Retained source paths</h4>
              {selectedMember.paths.length ? <ul>{selectedMember.paths.map((path) => <li key={path.pathId}>
                <strong>{displaySource(path.sourceKey)}</strong> · {path.route}<br />
                <code>Path {path.pathId}</code><br /><code>Source revision {path.sourceRevisionId}</code><br /><code>Context revision {path.contextRevisionId}</code><br />
                <ReportPathStatus path={path} />
              </li>)}</ul> : <p>No retained source path in this snapshot.</p>}
              <h4>Field status and witnesses</h4>
              <dl className="ro-key-value">{selectedMember.fields.map((field) => <div key={field.dimension}><dt>{readableDimension(field.dimension)}</dt><dd>{readableState(field.state)}{field.state === "known" ? `: ${displayValue(field.value)}` : ""}{field.witnessRevisionId ? <> · witness <code>{field.witnessRevisionId}</code></> : null}</dd></div>)}</dl>
              <p>Report-metadata inspection is action-specific. Other rights actions and source full-text copies are unassessed unless an exact separate witness is available; metadata retention is not full-text permission.</p>
            </div> : <p>Choose a record from the exact drill table to inspect its retained source paths and field witnesses.</p>}
          </Panel>
          <Panel title="Corpus reflexivity">
            <p>Coverage counts use {snapshot.memberCount} distinct canonical item revision{snapshot.memberCount === 1 ? "" : "s"} as their denominator. Unknown, unavailable and not reported are distinct states.</p>
            <h3 ref={membershipHeading} tabIndex={-1} className="corpus-focus-heading">Inclusion state</h3>
            <ul>{snapshot.membershipCounts.map((entry) => <li key={entry.membership}><Button aria-label={`Inspect ${entry.membership} items: ${entry.itemCount}`} onClick={() => selectFilter(reportFilter("membership", { membership: entry.membership }), `${entry.membership} items`)}>{entry.membership}: {entry.itemCount}</Button></li>)}</ul>
            <div className="ro-action-row"><Button aria-label={`Inspect items with at least one unattributed source path: ${snapshot.unattributedItemCount}`} onClick={() => selectFilter(reportFilter("unattributed"), "Items with an unattributed source path")}>Items with an unattributed source path: {snapshot.unattributedItemCount}</Button><Button aria-label={`Inspect duplicate-linked items: ${snapshot.duplicateLinkedItemCount}`} onClick={() => selectFilter(reportFilter("duplicate-linked"), "Duplicate-linked items")}>Duplicate-linked items: {snapshot.duplicateLinkedItemCount}</Button></div>
            {snapshot.valueDistributions.map((distribution) => <details key={distribution.dimension}><summary>{readableDimension(distribution.dimension)} known values</summary>{distribution.buckets.length ? <ul>{distribution.buckets.map((bucket) => <li key={bucket.value}><Button aria-label={`Inspect ${readableDimension(distribution.dimension)} value ${bucket.value}: ${bucket.itemCount} ${bucket.itemCount === 1 ? "item" : "items"}`} onClick={() => selectFilter(reportFilter("coverage", { dimension: distribution.dimension, state: "known", value: bucket.value }), `${readableDimension(distribution.dimension)}: ${bucket.value}`)}>{bucket.value}: {bucket.itemCount}</Button></li>)}</ul> : <p>No listed known values.</p>}{distribution.truncated ? <p>Additional known values: {distribution.otherKnownCount}. This list is incomplete; inspect all known {readableDimension(distribution.dimension).toLowerCase()} records for the full snapshot.</p> : null}<Button onClick={() => selectFilter(reportFilter("coverage", { dimension: distribution.dimension, state: "known", value: null }), `${readableDimension(distribution.dimension)}: Known`)}>Inspect all known records</Button></details>)}
          </Panel>
        </aside>
      </div>
      <div className="corpus-diagnostic-grid ro-grid">
        <Panel title="Source overlap">
          <p>Item counts deduplicate canonical records; discovery-path counts retain each source edge. Path-pair counts multiply paths from two sources on the same item. The same item can appear under more than one source.</p>
          {snapshot.sourceContributions.length ? <table className="ro-table"><caption>Source contributions</caption><thead><tr><th scope="col">Source</th><th scope="col">Items</th><th scope="col">Discovery paths</th><th scope="col">Inspect</th></tr></thead><tbody>{snapshot.sourceContributions.map((entry) => <tr key={entry.sourceKey}><th scope="row">{entry.sourceKey}</th><td>{entry.itemCount}</td><td>{entry.discoveryPathCount}</td><td><Button aria-label={`Inspect source ${entry.sourceKey}`} onClick={() => selectFilter(reportFilter("source", { sourceKey: entry.sourceKey }), `Source ${entry.sourceKey}`)}>Inspect</Button></td></tr>)}</tbody></table> : <p>No attributed source contribution is represented.</p>}
          {snapshot.sourceOverlaps.length ? <>
            <p role="status">Showing source pair rows {sourceOverlapPage * 50 + 1}–{Math.min((sourceOverlapPage + 1) * 50, snapshot.sourceOverlaps.length)} of {snapshot.sourceOverlaps.length}.</p>
            <div ref={sourceOverlapRegion} className="ro-table-scroll" tabIndex={0} aria-label="Source overlap table scroll region"><table className="ro-table"><caption>Items shared by source pairs</caption><thead><tr><th scope="col">Source pair</th><th scope="col">Items</th><th scope="col">Discovery path pairs</th><th scope="col">Inspect</th></tr></thead><tbody>{snapshot.sourceOverlaps.slice(sourceOverlapPage * 50, (sourceOverlapPage + 1) * 50).map((entry) => <tr key={JSON.stringify([entry.leftSourceKey, entry.rightSourceKey])}><th scope="row">{entry.leftSourceKey} + {entry.rightSourceKey}</th><td>{entry.itemCount}</td><td>{entry.discoveryPathPairCount}</td><td><Button aria-label={`Inspect overlap between ${entry.leftSourceKey} and ${entry.rightSourceKey}`} onClick={() => selectFilter(reportFilter("source-overlap", { leftSourceKey: entry.leftSourceKey, rightSourceKey: entry.rightSourceKey }), `Overlap: ${entry.leftSourceKey} and ${entry.rightSourceKey}`)}>Inspect</Button></td></tr>)}</tbody></table></div>
            {snapshot.sourceOverlaps.length > 50 ? <div className="ro-action-row"><Button disabled={sourceOverlapPage === 0} onClick={() => { focusSourceOverlap.current = true; setSourceOverlapPage(Math.max(0, sourceOverlapPage - 1)); }}>Previous source pairs</Button><Button disabled={(sourceOverlapPage + 1) * 50 >= snapshot.sourceOverlaps.length} onClick={() => { focusSourceOverlap.current = true; setSourceOverlapPage(sourceOverlapPage + 1); }}>Next source pairs</Button></div> : null}
          </> : <p>No source-pair overlap is represented.</p>}
          {snapshot.unattributedItemCount ? <p>{snapshot.unattributedItemCount} canonical item{snapshot.unattributedItemCount === 1 ? "" : "s"} have at least one unattributed source path; an item can also have an attributed path. Inspect them in Corpus reflexivity.</p> : null}
          {snapshot.unattributedDiscoveryPathCount ? <p>{snapshot.unattributedDiscoveryPathCount} discovery path{snapshot.unattributedDiscoveryPathCount === 1 ? "" : "s"} lack an attested source root.</p> : null}
        </Panel>
        <Panel title="Boundary sensitivity">
          <div ref={boundaryRegion} tabIndex={-1} className="corpus-focus-heading" aria-label="Source-boundary comparison">
            {boundary && snapshot ? <>
              <StatusBadge tone="info">Source-boundary comparison</StatusBadge>
              <p>This compares retained source-path boundaries within snapshot <code>{snapshot.snapshotId}</code>. The denominator is {snapshot.memberCount} canonical items. It does not model a new search, eligibility rule, or cluster change.</p>
              {sourceKeys.length > 1 ? <div className="ro-action-row corpus-boundary-selectors">
                <label htmlFor="corpus-boundary-first">First source</label>
                <select id="corpus-boundary-first" value={firstSource} onChange={(event) => {
                  const next = event.currentTarget.value;
                  setBoundaryFirst(next);
                  if (next === secondSource) setBoundarySecond(sourceKeys.find((key) => key !== next) ?? "");
                }}>{sourceKeys.map((key) => <option key={key} value={key}>{key}</option>)}</select>
                <label htmlFor="corpus-boundary-second">Second source</label>
                <select id="corpus-boundary-second" value={secondSource ?? ""} onChange={(event) => setBoundarySecond(event.currentTarget.value)}>
                  {sourceKeys.filter((key) => key !== firstSource).map((key) => <option key={key} value={key}>{key}</option>)}
                </select>
              </div> : null}
              <dl className="ro-key-value">
                <dt>{secondSource === null ? "All canonical items" : firstSource}</dt><dd>{boundary.firstCount}</dd>
                <dt>{secondSource === null ? firstSource : secondSource}</dt><dd>{boundary.secondCount}</dd>
                {secondSource !== null ? <><dt>Items in both source boundaries</dt><dd>{boundary.sharedCount}</dd></> : null}
                <dt>Discovery paths in first boundary</dt><dd>{boundary.firstPathCount}</dd>
                <dt>Discovery paths in second boundary</dt><dd>{boundary.secondPathCount}</dd>
                {secondSource !== null ? <><dt>Within-item path pairs across boundaries</dt><dd>{boundary.sharedPathPairCount}</dd></> : null}
              </dl>
              <div className="ro-action-row">
                <Button onClick={() => selectFilter(secondSource === null ? ALL_FILTER : reportFilter("source", { sourceKey: firstSource }), secondSource === null ? "All canonical items" : `Source ${firstSource}`)}>Inspect first boundary</Button>
                <Button onClick={() => selectFilter(reportFilter("source", { sourceKey: secondSource ?? firstSource }), `Source ${secondSource ?? firstSource}`)}>Inspect second boundary</Button>
                {secondSource !== null ? <Button onClick={() => selectFilter(reportFilter("source-overlap", { leftSourceKey: firstSource < secondSource ? firstSource : secondSource, rightSourceKey: firstSource < secondSource ? secondSource : firstSource }), `Overlap: ${firstSource} and ${secondSource}`)}>Inspect shared items</Button> : null}
              </div>
            </> : <><StatusBadge tone="neutral">Boundary comparison unavailable</StatusBadge><p>No attributed source boundary is represented in this snapshot. This report makes no sensitivity claim.</p></>}
          </div>
        </Panel>
        <Panel title="Missingness risks">
          <p>These are field availability counts, not inferred demographic or research-quality judgments.</p>
          <div className="ro-table-scroll" tabIndex={0} aria-label="Coverage table scroll region"><table className="ro-table"><caption>Coverage across distinct canonical items</caption><thead><tr><th scope="col">Field</th>{FIELD_STATES.map((state) => <th key={state} scope="col">{readableState(state)}</th>)}</tr></thead><tbody>
            {snapshot.coverage.map((entry) => <tr key={entry.dimension}><th scope="row">{readableDimension(entry.dimension)}</th>{FIELD_STATES.map((state) => <td key={state}><Button className="corpus-count-button" aria-label={`Inspect ${readableDimension(entry.dimension)} ${readableState(state).toLowerCase()} items: ${coverageCount(entry, state)}`} onClick={() => selectFilter(reportFilter("coverage", { dimension: entry.dimension, state, value: null }), `${readableDimension(entry.dimension)}: ${readableState(state)}`)}>{coverageCount(entry, state)}</Button></td>)}</tr>)}
          </tbody></table></div>
        </Panel>
      </div>
    </div> : <div className="corpus-empty ro-stack" role="status">
      <p>No report selected. Generate a local report or open an existing snapshot ID to inspect canonical corpus diagnostics.</p>
      <div className="corpus-toolbar" role="toolbar" aria-label="Corpus Canvas views">
        <Button disabled title="Semantic clusters unavailable">Semantic clusters</Button>
        <Button disabled title="Citation neighborhoods unavailable">Citation neighborhoods</Button>
        <Button disabled>Discovery paths</Button>
        <Button disabled>Inclusion state</Button>
      </div>
      <div className="corpus-main-grid">
        <section className="ro-card ro-stack corpus-network-stage" aria-labelledby="corpus-empty-paths"><Typography id="corpus-empty-paths" as="h2" variant="section-title">Discovery paths</Typography><StatusBadge tone="neutral">Semantic clusters unavailable</StatusBadge><p>Select a verified report to inspect retained paths and exact records.</p></section>
        <aside className="ro-stack corpus-inspection" aria-label="Corpus inspection"><Panel title="Selected cluster"><StatusBadge tone="neutral">Unavailable</StatusBadge><p>No semantic or citation cluster has been computed.</p></Panel><Panel title="Selected records"><p>Select a report and then a record to inspect source and field witnesses.</p></Panel><Panel title="Corpus reflexivity"><p>Coverage is unavailable until a report is selected.</p></Panel></aside>
      </div>
      <div className="corpus-diagnostic-grid ro-grid"><Panel title="Source overlap"><p>No report selected.</p></Panel><Panel title="Boundary sensitivity"><StatusBadge tone="neutral">Boundary comparison unavailable</StatusBadge><p>No alternate corpus boundary has been calculated.</p></Panel><Panel title="Missingness risks"><p>No report selected.</p></Panel></div>
    </div>}
  </div>;
}

function selectionLabelFor(filter: CorpusReportFilter, snapshot: CorpusReportSnapshot): string {
  if (filter.kind === "all") return `All ${snapshot.memberCount} canonical items`;
  if (filter.kind === "membership") return `${filter.membership} items`;
  if (filter.kind === "duplicate-linked") return "Duplicate-linked items";
  if (filter.kind === "unattributed") return "Items with an unattributed source path";
  if (filter.kind === "source") return `Source ${filter.sourceKey}`;
  if (filter.kind === "route") return `${filter.route} route`;
  if (filter.kind === "source-overlap") return `Source overlap ${filter.leftSourceKey} and ${filter.rightSourceKey}`;
  if (filter.kind === "route-overlap") return `Route overlap ${filter.leftRoute} and ${filter.rightRoute}`;
  return `${filter.dimension ? readableDimension(filter.dimension) : "Field"} ${filter.state ? readableState(filter.state) : "status"}`;
}
