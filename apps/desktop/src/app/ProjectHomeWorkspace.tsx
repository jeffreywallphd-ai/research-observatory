import type { ReactNode } from "react";

import { Button, Panel, StatusBadge, Typography } from "@research-observatory/ui-components";
import type {
  ProjectProjection,
  WorkflowProgressProjection,
} from "@research-observatory/contracts/core-api";

import type { WorkflowNavigationLoadState } from "./WorkflowNavigation";
import {
  workflowRevisitSources,
  type WorkflowProgressStage,
} from "./workflowNavigationModel";

interface ProjectHomeWorkspaceProps {
  readonly project: ProjectProjection | null;
  readonly progress: WorkflowProgressProjection | null;
  readonly loadState: WorkflowNavigationLoadState;
  readonly failure: string | null;
  readonly busy: boolean;
  readonly onStart: () => void;
  readonly onResume: () => void;
  readonly onOpenCurrent: () => void;
  readonly onRevisit: (source: WorkflowProgressStage) => void;
}

function checkpointLabel(state: WorkflowProgressProjection["checkpointState"]): string {
  switch (state) {
    case "unknown": return "Not yet governed";
    case "optional-human": return "Optional human review";
    case "required-human": return "Human review required";
    case "not-applicable": return "Not applicable";
  }
}

export function ProjectHomeWorkspace({
  project,
  progress,
  loadState,
  failure,
  busy,
  onStart,
  onResume,
  onOpenCurrent,
  onRevisit,
}: ProjectHomeWorkspaceProps): ReactNode {
  if (!project) {
    return (
      <section aria-labelledby="project-home-title" data-project-home-state="empty">
        <div className="page-header">
          <Typography id="project-home-title" as="h1" variant="page-title">Project Home</Typography>
          <Typography className="page-subtitle">
            Open a compatible local project to see its governed workflow position and research-quality gates.
          </Typography>
        </div>
      </section>
    );
  }

  if (!progress) {
    return (
      <section aria-labelledby="project-home-title" data-project-home-state={loadState}>
        <div className="page-header">
          <Typography id="project-home-title" as="h1" variant="page-title">{project.displayName}</Typography>
          <Typography className="page-subtitle">Project Home</Typography>
        </div>
        <Panel title="Guided workflow" tone={loadState === "error" ? "danger" : "neutral"}>
          <p role={loadState === "error" ? "alert" : "status"}>
            {loadState === "loading"
              ? "Loading the persisted workflow position…"
              : failure ?? "Workflow progress is unavailable for this project."}
          </p>
        </Panel>
      </section>
    );
  }

  const currentLabel = progress.current?.stageKey ?? progress.recommendedStageKey;
  const complete = progress.current === null && !progress.bootstrapRequired;
  const resumable = progress.current?.status === "attention-required" || progress.current?.status === "blocked";
  const revisitSources = workflowRevisitSources(progress);
  const recommendedRevisit = revisitSources.find((source) => source.stageKey === progress.recommendedStageKey) ?? null;
  return (
    <section aria-labelledby="project-home-title" data-project-home-state="ready" data-workflow-profile={progress.profileId}>
      <div className="page-header">
        <Typography id="project-home-title" as="h1" variant="page-title">{project.displayName}</Typography>
        <Typography className="page-subtitle">
          {progress.profileTitle} · {progress.processForm === "revisitable" ? "Revisitable" : "Linear"} workflow
        </Typography>
      </div>

      <div className="project-home-grid">
        <Panel title="Current position" tone={complete ? "success" : resumable ? "danger" : "neutral"}>
          <StatusBadge tone={complete ? "success" : resumable ? "danger" : "neutral"}>
            {complete ? "Workflow complete" : progress.bootstrapRequired ? "Not started" : progress.current?.status ?? "Review"}
          </StatusBadge>
          <p><strong>{currentLabel}</strong></p>
          <p>{progress.recommendedAction}</p>
          {progress.bootstrapRequired ? (
            <Button tone="primary" disabled={busy} onClick={onStart}>Start guided workflow</Button>
          ) : resumable ? (
            <Button tone="primary" disabled={busy} onClick={onResume}>Resume current step</Button>
          ) : complete && progress.processForm === "revisitable" ? (
            <Button
              tone="primary"
              disabled={busy || recommendedRevisit === null}
              onClick={() => { if (recommendedRevisit) onRevisit(recommendedRevisit); }}
            >Begin another pass</Button>
          ) : (
            <Button tone="primary" disabled={busy || progress.current === null} onClick={onOpenCurrent}>
              Open current step
            </Button>
          )}
        </Panel>

        <Panel title="Research-quality gate" tone={progress.checkpointState === "required-human" ? "danger" : "neutral"}>
          <StatusBadge tone={progress.checkpointState === "required-human" ? "danger" : "neutral"}>
            {checkpointLabel(progress.checkpointState)}
          </StatusBadge>
          <p>{progress.checkpointRationale}</p>
          <p>Stage completion is recorded only by an explicit researcher action bound to exact project evidence.</p>
        </Panel>
      </div>

      {revisitSources.length > 0 ? (
        <Panel title="Revisit completed steps" tone="neutral">
          <p>Starting a new pass preserves every prior pass. If another step is current, it remains recorded in progress.</p>
          <ul className="project-home-revisit-list" data-workflow-revisit-options>
            {revisitSources.map((source) => (
              <li key={source.stageStateRevisionId}>
                <span><strong>{source.stageKey}</strong> · Pass {source.passNumber} · {source.status}</span>
                <Button disabled={busy} onClick={() => onRevisit(source)}>Revisit {source.stageKey}</Button>
              </li>
            ))}
          </ul>
        </Panel>
      ) : null}

      <Panel title="Outputs needing review" tone={progress.staleOutputs.length > 0 ? "danger" : "success"}>
        {progress.staleOutputs.length === 0 ? (
          <p>No stale or unknown-impact outputs are recorded.</p>
        ) : (
          <ul className="project-home-stale-list">
            {progress.staleOutputs.map((output) => (
              <li key={`${output.outputRevisionId}:${output.causeReferenceHash}`}>
                <strong>{output.disposition === "unknown-impact" ? "Impact unknown" : "Stale output"}</strong>
                <span>{output.reason}</span>
                <small>{output.safestNextAction}</small>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </section>
  );
}
