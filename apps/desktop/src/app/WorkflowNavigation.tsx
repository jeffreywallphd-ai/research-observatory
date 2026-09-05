import type { ReactNode } from "react";

import {
  IMPLEMENTED_WORKSPACES,
  deriveWorkflowStages,
  implementedWorkspace,
  supportingReturnMatches,
  workspaceClassification,
  type ApplicationWorkspace,
  type SupportingReturnContext,
  type WorkflowAuthoritySnapshot,
  type WorkflowStageAuthorityState,
} from "./workflowNavigationModel";

export type WorkflowNavigationLoadState = "loading" | "ready" | "unavailable" | "error";

interface WorkflowNavigationProps {
  readonly authority: WorkflowAuthoritySnapshot | null;
  readonly currentWorkspace: ApplicationWorkspace;
  readonly loadState: WorkflowNavigationLoadState;
  readonly failure?: string | null;
  readonly authoritativeStates?: Readonly<Partial<Record<string, WorkflowStageAuthorityState>>>;
  readonly supportingReturn?: SupportingReturnContext | null;
  readonly disabled?: boolean;
  readonly showContext?: boolean;
  readonly onSelectStage: (stageKey: string) => void;
  readonly onSelectWorkspace: (workspace: ApplicationWorkspace) => void;
  readonly onReturn: () => void;
}

function checkpointLabel(state: WorkflowAuthoritySnapshot["profile"]["stages"][number]["checkpointState"]): string {
  switch (state) {
    case "unknown": return "Unknown";
    case "optional-human": return "Optional human review";
    case "required-human": return "Required human review";
    case "not-applicable": return "Not applicable";
  }
}

function AllTools({
  authority,
  currentWorkspace,
  disabled,
  onSelectWorkspace,
}: Pick<WorkflowNavigationProps, "authority" | "currentWorkspace" | "disabled" | "onSelectWorkspace">): ReactNode {
  return (
    <details className="all-tools" data-all-tools>
      <summary>All tools</summary>
      <ul aria-label="All implemented tools">
        {IMPLEMENTED_WORKSPACES.map((tool) => {
          const classification = authority ? workspaceClassification(authority, tool.id) : null;
          return (
            <li key={tool.id}>
              <button
                className="ro-stack ro-stack--tight"
                type="button"
                disabled={disabled}
                aria-label={tool.label}
                aria-current={currentWorkspace === tool.id ? "page" : undefined}
                onClick={() => onSelectWorkspace(tool.id)}
              >
                <span>{tool.label}</span>
                <small>{classification ? classification.role === "primary" ? "Primary workflow tool" : "Supporting tool" : "Implemented tool"}</small>
              </button>
            </li>
          );
        })}
      </ul>
    </details>
  );
}

export function WorkflowNavigation({
  authority,
  currentWorkspace,
  loadState,
  failure = null,
  authoritativeStates = {},
  supportingReturn = null,
  disabled = false,
  showContext = true,
  onSelectStage,
  onSelectWorkspace,
  onReturn,
}: WorkflowNavigationProps): ReactNode {
  if (!authority) {
    return (
      <nav className="workflow-navigation ro-stack" aria-label="Research workflow and tools" data-workflow-navigation>
        <div className="workflow-navigation-heading ro-stack">
          <strong>Guided workflow unavailable</strong>
          <span role={loadState === "error" ? "alert" : "status"}>
            {loadState === "loading"
              ? "Loading the authenticated workflow and current Research Intent…"
              : failure ?? "Open a compatible local project with a current Research Intent to load guided workflow navigation."}
          </span>
        </div>
        <AllTools
          authority={null}
          currentWorkspace={currentWorkspace}
          disabled={disabled}
          onSelectWorkspace={onSelectWorkspace}
        />
      </nav>
    );
  }

  const stages = deriveWorkflowStages(authority, authoritativeStates);

  return (
    <nav
      className="workflow-navigation ro-stack"
      aria-label="Research workflow and tools"
      data-workflow-navigation
      data-workflow-nav
    >
      <div className="workflow-navigation-heading ro-stack">
        <strong>{authority.profile.title}</strong>
        <span>{authority.profile.processForm === "revisitable" ? "Revisitable workflow" : "Linear workflow"}</span>
      </div>

      <ol className="workflow-stage-list" aria-label="Ordered steps for the selected use case">
        {stages.map((stage) => (
          <li
            key={stage.stageKey}
            data-workflow-stage-key={stage.stageKey}
            data-stage-state={stage.state}
            data-stage-optional={stage.optional || undefined}
          >
            <button
              type="button"
              disabled={disabled || stage.implementedWorkspace === null}
              aria-current={stage.stageKey === authority.currentStageKey ? "step" : undefined}
              onClick={() => onSelectStage(stage.stageKey)}
            >
              <span className="workflow-stage-number" aria-hidden="true">{stage.order}</span>
              <span className="workflow-stage-copy">
                <strong>{stage.label}</strong>
                <small>{stage.stateLabel}{stage.optional ? " · Optional" : ""}</small>
                {stage.implementedWorkspace === null ? <small>Unavailable in this version</small> : null}
              </span>
            </button>
          </li>
        ))}
      </ol>

      <AllTools
        authority={authority}
        currentWorkspace={currentWorkspace}
        disabled={disabled}
        onSelectWorkspace={onSelectWorkspace}
      />

      {showContext ? (
        <WorkflowContextBar
          authority={authority}
          currentWorkspace={currentWorkspace}
          authoritativeStates={authoritativeStates}
          supportingReturn={supportingReturn}
          disabled={disabled}
          onSelectStage={onSelectStage}
          onReturn={onReturn}
        />
      ) : null}
    </nav>
  );
}

export function WorkflowContextBar({
  authority,
  currentWorkspace,
  authoritativeStates = {},
  supportingReturn = null,
  disabled = false,
  onSelectStage,
  onReturn,
}: Pick<
  WorkflowNavigationProps,
  "authority" | "currentWorkspace" | "authoritativeStates" | "supportingReturn" | "disabled" | "onSelectStage" | "onReturn"
>): ReactNode {
  if (!authority) return null;
  const stages = deriveWorkflowStages(authority, authoritativeStates);
  const currentIndex = stages.findIndex(({ stageKey }) => stageKey === authority.currentStageKey);
  const current = stages[currentIndex];
  if (!current) return null;
  const previous = currentIndex > 0 ? stages[currentIndex - 1] : null;
  const next = stages[currentIndex + 1] ?? null;
  const workspace = implementedWorkspace(currentWorkspace);
  const showingSupportingTool = workspaceClassification(authority, currentWorkspace).role === "supporting";
  const returnIsCurrent = supportingReturn !== null && supportingReturnMatches(supportingReturn, authority);
  return (
    <section className="workflow-context ro-card" aria-label="Current guided workflow position" data-workflow-context>
      <div className="workflow-context-heading ro-stack">
        <strong>Step {current.order} of {stages.length} · {current.label}</strong>
        <span>{authority.referenceId} · {authority.referenceVersion}</span>
      </div>
      <p>{current.rationale}</p>
      <dl>
        <div><dt>Expected output</dt><dd>{authority.profile.expectedOutputs.join("; ")}</dd></div>
        <div><dt>Quality gate · {checkpointLabel(current.checkpointState)}</dt><dd>{current.checkpointRationale}</dd></div>
      </dl>
      <div className="workflow-context-actions ro-stack">
        {previous ? (
          <button
            type="button"
            disabled={disabled || previous.implementedWorkspace === null}
            onClick={() => onSelectStage(previous.stageKey)}
          >
            Previous step · {previous.label}
          </button>
        ) : <span>Previous step · None</span>}
        {next ? (
          <span>
            <button
              type="button"
              disabled={disabled || next.implementedWorkspace === null}
              onClick={() => onSelectStage(next.stageKey)}
            >
              Next step · {next.label}
            </button>
            {next.implementedWorkspace === null ? <small>Unavailable in this version</small> : null}
          </span>
        ) : <span>Next step · None</span>}
      </div>
      {showingSupportingTool ? (
        <div className="supporting-tool-context ro-stack" data-supporting-tool>
          <strong>Supporting tool · {workspace.label}</strong>
          {returnIsCurrent ? (
            <button type="button" disabled={disabled} onClick={onReturn}>
              Return to current step · {current.label}
            </button>
          ) : (
            <span role="status">Supporting context expired. Reopen a primary workflow step before returning.</span>
          )}
        </div>
      ) : null}
    </section>
  );
}
