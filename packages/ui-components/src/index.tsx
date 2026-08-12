import { useState, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode, type Ref } from "react";

import {
  DESIGN_REFERENCE_ID,
  DESIGN_TOKEN_CONTRACT_VERSION,
  evidenceStates,
  isSemanticTone,
  uncertaintyStates,
  type EvidenceState,
  type SemanticTone,
  type UncertaintyState as UncertaintyIdentity,
} from "@research-observatory/ui-tokens";

export { DESIGN_REFERENCE_ID, DESIGN_TOKEN_CONTRACT_VERSION };
export const UI_COMPONENT_CONTRACT_VERSION = "1.2.0" as const;

export const boundaryStates = [
  "loading",
  "empty",
  "offline",
  "denied",
  "stale",
  "partial",
  "failed",
  "recovery-required",
] as const;
export type BoundaryState = (typeof boundaryStates)[number];

type TypographyVariant = "display" | "page-title" | "section-title" | "card-title" | "body" | "compact" | "label";
type TypographyTag = "h1" | "h2" | "h3" | "p" | "span";

function classNames(...values: Array<string | false | null | undefined>): string {
  return values.filter(Boolean).join(" ");
}

function requireSemanticTone(tone: SemanticTone): void {
  if (!isSemanticTone(tone)) throw new RangeError(`unsupported semantic tone: ${String(tone)}`);
}

export interface TypographyProps {
  readonly id?: string;
  readonly as?: TypographyTag;
  readonly variant?: TypographyVariant;
  readonly className?: string;
  readonly children: ReactNode;
}

export function Typography({ id, as: Element = "p", variant = "body", className, children }: TypographyProps) {
  return <Element id={id} className={classNames("ro-typography", `ro-typography--${variant}`, className)}>{children}</Element>;
}

const ICON_PATHS = {
  info: "M12 7.25a1.25 1.25 0 1 0 0-2.5 1.25 1.25 0 0 0 0 2.5Zm-1 2.25h2v9h-2v-9Z",
  success: "m6.7 12.3 3.1 3.1 7.5-7.5 1.4 1.4-8.9 8.9-4.5-4.5 1.4-1.4Z",
  warning: "M12 3 2.5 20h19L12 3Zm-1 6h2v5h-2V9Zm0 7h2v2h-2v-2Z",
  danger: "M7.05 5.64 12 10.59l4.95-4.95 1.41 1.41L13.41 12l4.95 4.95-1.41 1.41L12 13.41l-4.95 4.95-1.41-1.41L10.59 12 5.64 7.05l1.41-1.41Z",
  evidence: "M5 3h14v18H5V3Zm2 2v14h10V5H7Zm2 3h6v2H9V8Zm0 4h6v2H9v-2Zm0 4h4v2H9v-2Z",
} as const;

export interface IconProps {
  readonly name: keyof typeof ICON_PATHS;
  readonly label?: string;
  readonly className?: string;
}

export function Icon({ name, label, className }: IconProps) {
  const accessibility = label ? { role: "img", "aria-label": label } : { "aria-hidden": true as const };
  return (
    <svg className={classNames("ro-icon", className)} viewBox="0 0 24 24" focusable="false" {...accessibility}>
      <path d={ICON_PATHS[name]} />
    </svg>
  );
}

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  readonly tone?: "primary" | "secondary" | "danger";
  readonly ref?: Ref<HTMLButtonElement>;
}

export function Button({ ref, tone = "secondary", type = "button", className, children, ...props }: ButtonProps) {
  return (
    <button ref={ref} type={type} className={classNames("ro-button", `ro-button--${tone}`, className)} {...props}>
      {children}
    </button>
  );
}

export interface FieldProps {
  readonly id: string;
  readonly label: string;
  readonly description?: string;
  readonly error?: string;
  readonly inputRef?: Ref<HTMLInputElement>;
  readonly input?: Omit<InputHTMLAttributes<HTMLInputElement>, "id" | "aria-describedby" | "aria-invalid">;
}

export function Field({ id, label, description, error, inputRef, input }: FieldProps) {
  if (!id.trim() || !label.trim()) throw new TypeError("field id and label must be nonempty");
  const descriptionIds = [description ? `${id}-description` : null, error ? `${id}-error` : null]
    .filter(Boolean)
    .join(" ");
  return (
    <div className="ro-field" data-invalid={error ? "true" : undefined}>
      <label htmlFor={id}>{label}</label>
      {description ? <span id={`${id}-description`} className="ro-field__description">{description}</span> : null}
      <input ref={inputRef} id={id} aria-describedby={descriptionIds || undefined} aria-invalid={error ? true : undefined} {...input} />
      {error ? <span id={`${id}-error`} className="ro-field__error">{error}</span> : null}
    </div>
  );
}

export interface DataColumn {
  readonly id: string;
  readonly label: string;
}

export interface DataTableProps {
  readonly caption: string;
  readonly columns: readonly DataColumn[];
  readonly rows: ReadonlyArray<Readonly<Record<string, ReactNode>>>;
  readonly rowKey: (row: Readonly<Record<string, ReactNode>>, index: number) => string;
  readonly compact?: boolean;
  readonly pageSize?: number;
  readonly initialPage?: number;
}

export const DEFAULT_DATA_TABLE_PAGE_SIZE = 50;
export const MAX_DATA_TABLE_PAGE_SIZE = 200;

export function DataTable({
  caption,
  columns,
  rows,
  rowKey,
  compact = false,
  pageSize = DEFAULT_DATA_TABLE_PAGE_SIZE,
  initialPage = 0,
}: DataTableProps) {
  if (!caption.trim() || columns.length === 0 || new Set(columns.map((column) => column.id)).size !== columns.length) {
    throw new TypeError("table requires a caption and unique columns");
  }
  if (!Number.isInteger(pageSize) || pageSize < 1 || pageSize > MAX_DATA_TABLE_PAGE_SIZE) {
    throw new RangeError(`table page size must be an integer from 1 through ${MAX_DATA_TABLE_PAGE_SIZE}`);
  }
  const pageCount = Math.max(1, Math.ceil(rows.length / pageSize));
  if (!Number.isInteger(initialPage) || initialPage < 0 || initialPage >= pageCount) {
    throw new RangeError("table initial page must identify an available zero-based page");
  }
  const [requestedPage, setRequestedPage] = useState(initialPage);
  const page = Math.min(requestedPage, pageCount - 1);
  const firstRowIndex = page * pageSize;
  const visibleRows = rows.slice(firstRowIndex, firstRowIndex + pageSize);
  const rangeStart = rows.length === 0 ? 0 : firstRowIndex + 1;
  const rangeEnd = firstRowIndex + visibleRows.length;

  return (
    <div
      className="ro-data-table"
      data-total-rows={rows.length}
      data-rendered-rows={visibleRows.length}
      data-page-size={pageSize}
    >
      <div className="ro-table-scroll" tabIndex={0} aria-label={`${caption} scroll region`}>
        <table className="ro-table" data-density={compact ? "compact" : "default"}>
          <caption>{caption}</caption>
          <thead><tr>{columns.map((column) => <th scope="col" key={column.id}>{column.label}</th>)}</tr></thead>
          <tbody>
            {visibleRows.map((row, index) => (
              <tr key={rowKey(row, firstRowIndex + index)}>
                {columns.map((column) => <td key={column.id}>{row[column.id]}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {pageCount > 1 ? (
        <nav className="ro-table-pagination" aria-label={`${caption} pagination`}>
          <span aria-live="polite" aria-atomic="true">
            Rows {rangeStart}-{rangeEnd} of {rows.length}. Page {page + 1} of {pageCount}.
          </span>
          <span className="ro-table-pagination__actions">
            <Button
              disabled={page === 0}
              onClick={() => setRequestedPage(Math.max(0, page - 1))}
              aria-label={`Previous page of ${caption}`}
            >
              Previous
            </Button>
            <Button
              disabled={page >= pageCount - 1}
              onClick={() => setRequestedPage(Math.min(pageCount - 1, page + 1))}
              aria-label={`Next page of ${caption}`}
            >
              Next
            </Button>
          </span>
        </nav>
      ) : null}
    </div>
  );
}

export interface DialogSurfaceProps {
  readonly id: string;
  readonly title: string;
  readonly open?: boolean;
  readonly children: ReactNode;
  readonly actions?: ReactNode;
}

export function DialogSurface({ id, title, open = false, children, actions }: DialogSurfaceProps) {
  if (!id.trim() || !title.trim()) throw new TypeError("dialog id and title must be nonempty");
  return (
    <dialog className="ro-dialog" open={open} aria-labelledby={`${id}-title`}>
      <Typography id={`${id}-title`} as="h2" variant="section-title" className="ro-dialog__title">{title}</Typography>
      <div className="ro-dialog__body">{children}</div>
      {actions ? <div className="ro-dialog__actions">{actions}</div> : null}
    </dialog>
  );
}

export interface ToneProps {
  readonly tone?: SemanticTone;
  readonly children: ReactNode;
}

export interface NotificationProps extends ToneProps {
  readonly title: string;
}

export function Notification({ tone = "info", title, children }: NotificationProps) {
  requireSemanticTone(tone);
  return (
    <section className="ro-notification" data-tone={tone} role={tone === "danger" ? "alert" : "status"} aria-atomic="true">
      <Typography as="h3" variant="card-title">{title}</Typography>
      <div>{children}</div>
    </section>
  );
}

export function StatusBadge({ tone = "neutral", children }: ToneProps) {
  requireSemanticTone(tone);
  return <span className="ro-status-badge" data-tone={tone}>{children}</span>;
}

const EVIDENCE_STATE_LABELS: Readonly<Record<EvidenceState, string>> = {
  observed: "Observed",
  extracted: "Extracted",
  inferred: "Inferred",
  verified: "Verified",
  disputed: "Disputed",
  adjudicated: "Adjudicated",
  stale: "Stale",
};

const UNCERTAINTY_STATE_LABELS: Readonly<Record<UncertaintyIdentity, string>> = {
  unknown: "Unknown",
  "not-reported": "Not reported",
  "not-applicable": "Not applicable",
  ambiguous: "Ambiguous",
};

function requireEvidenceState(state: EvidenceState): void {
  if (!evidenceStates.some((candidate) => candidate === state)) {
    throw new RangeError(`unsupported evidence state: ${String(state)}`);
  }
}

function requireUncertaintyState(state: UncertaintyIdentity): void {
  if (!uncertaintyStates.some((candidate) => candidate === state)) {
    throw new RangeError(`unsupported uncertainty state: ${String(state)}`);
  }
}

const BOUNDARY_STATE_LABELS: Readonly<Record<BoundaryState, string>> = {
  loading: "Loading",
  empty: "Empty",
  offline: "Offline",
  denied: "Access denied",
  stale: "Stale",
  partial: "Partial results",
  failed: "Failed",
  "recovery-required": "Recovery required",
};

const BOUNDARY_STATE_TONES: Readonly<Record<BoundaryState, SemanticTone>> = {
  loading: "info",
  empty: "neutral",
  offline: "warning",
  denied: "danger",
  stale: "warning",
  partial: "info",
  failed: "danger",
  "recovery-required": "warning",
};

const DIAGNOSTIC_REFERENCE = /^RO-[A-Z0-9]+(?:-[A-Z0-9]+){1,15}$/;

function requireBoundaryState(state: BoundaryState): void {
  if (!boundaryStates.some((candidate) => candidate === state)) {
    throw new RangeError(`unsupported boundary state: ${String(state)}`);
  }
}

function requireDiagnosticReference(reference: string): void {
  if (reference.length > 96 || !DIAGNOSTIC_REFERENCE.test(reference)) {
    throw new TypeError("diagnostic reference must be a bounded Research Observatory identifier");
  }
}

export interface BoundaryProgress {
  readonly label: string;
  readonly value: number;
}

export interface BoundaryStatePanelProps {
  readonly id?: string;
  readonly state: BoundaryState;
  readonly title: string;
  readonly message: string;
  readonly progress?: BoundaryProgress;
  readonly diagnosticReference?: string;
  readonly onRetry?: () => void;
  readonly onCancel?: () => void;
  readonly onContinueOffline?: () => void;
  readonly onCopyDiagnostic?: (reference: string) => void;
  readonly children?: ReactNode;
}

export function BoundaryStatePanel({
  id,
  state,
  title,
  message,
  progress,
  diagnosticReference,
  onRetry,
  onCancel,
  onContinueOffline,
  onCopyDiagnostic,
  children,
}: BoundaryStatePanelProps) {
  requireBoundaryState(state);
  if (!title.trim() || !message.trim()) throw new TypeError("boundary title and message must be nonempty");
  if (progress && (!progress.label.trim() || !Number.isFinite(progress.value) || progress.value < 0 || progress.value > 100)) {
    throw new RangeError("boundary progress requires a nonempty label and a finite value from 0 through 100");
  }
  if (diagnosticReference) requireDiagnosticReference(diagnosticReference);
  const urgent = state === "denied" || state === "failed" || state === "recovery-required";
  const tone = BOUNDARY_STATE_TONES[state];
  return (
    <section
      id={id}
      className="ro-boundary-state"
      data-boundary-state={state}
      data-tone={tone}
      role={urgent ? "alert" : "status"}
      aria-atomic="true"
      aria-busy={state === "loading" ? true : undefined}
    >
      <div className="ro-boundary-state__header">
        <Typography as="h3" variant="card-title">{title}</Typography>
        <StatusBadge tone={tone}>State: {BOUNDARY_STATE_LABELS[state]}</StatusBadge>
      </div>
      <p>{message}</p>
      {progress ? (
        <label className="ro-boundary-state__progress">
          <span>{progress.label}: {progress.value}%</span>
          <progress value={progress.value} max={100}>{progress.value}%</progress>
        </label>
      ) : null}
      {diagnosticReference ? (
        <div className="ro-boundary-state__diagnostic">
          <span>Diagnostic reference</span>
          <code data-diagnostic-reference>{diagnosticReference}</code>
        </div>
      ) : null}
      {children ? <div className="ro-boundary-state__retained">{children}</div> : null}
      {onRetry || onCancel || onContinueOffline || (diagnosticReference && onCopyDiagnostic) ? (
        <div className="ro-boundary-state__actions">
          {onRetry ? <Button tone="primary" onClick={onRetry} data-retry-boundary>Retry</Button> : null}
          {onCancel ? <Button onClick={onCancel} data-cancel-boundary>Cancel</Button> : null}
          {onContinueOffline ? <Button onClick={onContinueOffline} data-continue-offline>Continue locally</Button> : null}
          {diagnosticReference && onCopyDiagnostic ? (
            <Button onClick={() => onCopyDiagnostic(diagnosticReference)} data-copy-diagnostic>Copy diagnostic reference</Button>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

export interface EvidenceStateBadgeProps {
  readonly state: EvidenceState;
}

export function EvidenceStateBadge({ state }: EvidenceStateBadgeProps) {
  requireEvidenceState(state);
  return <span className="ro-evidence-state" data-evidence-state={state}>Evidence: {EVIDENCE_STATE_LABELS[state]}</span>;
}

export interface UncertaintyStateProps {
  readonly state: UncertaintyIdentity;
}

export function UncertaintyState({ state }: UncertaintyStateProps) {
  requireUncertaintyState(state);
  return <span className="ro-uncertainty-state" data-uncertainty-state={state}>Uncertainty: {UNCERTAINTY_STATE_LABELS[state]}</span>;
}

export interface PanelProps extends ToneProps {
  readonly title: string;
  readonly evidenceState?: EvidenceState;
}

export function Panel({ tone = "neutral", title, evidenceState, children }: PanelProps) {
  requireSemanticTone(tone);
  if (evidenceState) requireEvidenceState(evidenceState);
  return (
    <section className="ro-panel" data-tone={tone} data-evidence-state={evidenceState}>
      <Typography as="h2" variant="section-title">{title}</Typography>
      <div>{children}</div>
    </section>
  );
}
