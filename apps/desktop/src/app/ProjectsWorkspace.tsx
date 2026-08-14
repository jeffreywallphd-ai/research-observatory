import { useMemo, useState, type FormEvent, type ReactNode } from "react";

import {
  CoreApiClientError,
  createCoreApiClient,
  type CoreApiRequest,
  type CoreApiResponse,
  type CoreApiTransport,
  type ProjectProjection,
} from "@research-observatory/contracts/core-api";
import { invoke } from "@tauri-apps/api/core";
import { Button, Field, Notification, Panel, StatusBadge, Typography } from "@research-observatory/ui-components";

export interface ProjectsWorkspaceProps {
  readonly announce: (message: string) => void;
  readonly transport?: CoreApiTransport;
  readonly onProjectChange?: (project: ProjectProjection) => void;
}

function hasTauriRuntime(): boolean {
  return typeof globalThis.window !== "undefined" && "__TAURI_INTERNALS__" in globalThis.window;
}

export async function packagedProjectTransport(request: CoreApiRequest): Promise<CoreApiResponse> {
  if (!hasTauriRuntime()) throw new Error("RO-CORE-HOST-UNAVAILABLE");
  return await invoke<CoreApiResponse>("core_api_request", { request });
}

export function projectActionLabels(project: ProjectProjection | null): readonly string[] {
  if (!project) return [];
  const actions: string[] = [];
  if (project.lifecycleState === "active") actions.push(project.open ? "Close project" : "Open project");
  if (project.lifecycleState === "active" && !project.open) actions.push("Archive project");
  if (project.lifecycleState === "archived") actions.push("Restore project");
  if (!project.open && project.lifecycleState !== "trash") actions.push("Move to recoverable trash");
  return actions;
}

function safeFailure(error: unknown): { readonly title: string; readonly message: string } {
  if (error instanceof CoreApiClientError) {
    return { title: error.problem.code, message: error.problem.remediation };
  }
  return {
    title: "RO-CORE-PROJECT-ACTION-FAILED",
    message: "The local project action did not complete. Review Core status and retry once.",
  };
}

export function ProjectsWorkspace({
  announce,
  transport = packagedProjectTransport,
  onProjectChange,
}: ProjectsWorkspaceProps): ReactNode {
  const client = useMemo(() => createCoreApiClient(transport), [transport]);
  const [project, setProject] = useState<ProjectProjection | null>(null);
  const [parentDirectory, setParentDirectory] = useState("");
  const [directoryName, setDirectoryName] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [openRoot, setOpenRoot] = useState("");
  const [deleteConfirmation, setDeleteConfirmation] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [failure, setFailure] = useState<{ readonly title: string; readonly message: string } | null>(null);

  const run = async (label: string, action: () => Promise<ProjectProjection>): Promise<void> => {
    setBusy(label);
    setFailure(null);
    try {
      const next = await action();
      setProject(next);
      onProjectChange?.(next);
      setOpenRoot(next.root);
      setDeleteConfirmation("");
      announce(`${label} completed.`);
    } catch (error) {
      const safe = safeFailure(error);
      setFailure(safe);
      announce(`${label} did not complete. ${safe.title}`);
    } finally {
      setBusy(null);
    }
  };

  const createProject = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    void run("Create project", () => client.createProject({
      parentDirectory,
      directoryName,
      displayName,
      templateId: "theory-synthesis",
    }));
  };

  const openProject = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    void run("Open project", () => client.openProject({ root: openRoot }));
  };

  return (
    <section className="projects-workspace" aria-labelledby="projects-title" data-projects-workspace>
      <div className="page-header">
        <Typography id="projects-title" as="h1" variant="page-title">Local projects</Typography>
        <Typography className="page-subtitle">
          Create or open a governed local project package. Project documents remain on this computer.
        </Typography>
      </div>

      {failure ? <Notification tone="danger" title={failure.title}>{failure.message}</Notification> : null}

      <div className="project-workflow-grid">
        <Panel title="Create a local project">
          <form className="project-form" onSubmit={createProject}>
            <Field
              id="project-parent-directory"
              label="Parent directory"
              description="Enter an existing absolute local directory, for example C:\Research."
              input={{ value: parentDirectory, onChange: (event) => setParentDirectory(event.currentTarget.value), required: true }}
            />
            <Field
              id="project-directory-name"
              label="Project directory name"
              description="Use lowercase letters, numbers, and hyphens."
              input={{ value: directoryName, onChange: (event) => setDirectoryName(event.currentTarget.value), required: true, pattern: "[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?" }}
            />
            <Field
              id="project-display-name"
              label="Project name"
              input={{ value: displayName, onChange: (event) => setDisplayName(event.currentTarget.value), required: true, maxLength: 120 }}
            />
            <p className="field-note"><strong>Template:</strong> Theory synthesis. More templates arrive in their governed slices.</p>
            <Button tone="primary" type="submit" disabled={busy !== null}>Create project</Button>
          </form>
        </Panel>

        <Panel title="Open an existing project">
          <form className="project-form" onSubmit={openProject}>
            <Field
              id="project-root"
              label="Project directory"
              description="Enter the absolute directory containing project.ro.json."
              input={{ value: openRoot, onChange: (event) => setOpenRoot(event.currentTarget.value), required: true }}
            />
            <Button tone="primary" type="submit" disabled={busy !== null}>Open project</Button>
          </form>
        </Panel>
      </div>

      <Panel title="Current project" tone={project ? "success" : "neutral"}>
        {!project ? <p>No project is selected. Create one or open an existing local project.</p> : (
          <div className="current-project" data-current-project={project.projectId}>
            <div>
              <Typography as="h2" variant="section-title">{project.displayName}</Typography>
              <p><code>{project.root}</code></p>
              <div className="project-status-row">
                <StatusBadge tone={project.lifecycleState === "active" ? "success" : "warning"}>
                  {project.lifecycleState}
                </StatusBadge>
                <span>{project.open ? "Exclusive local session open" : "Closed"}</span>
                <span>Revision {project.revision}</span>
              </div>
            </div>
            <div className="project-actions" aria-label="Current project actions">
              {project.lifecycleState === "active" ? (
                <Button disabled={busy !== null} onClick={() => void run(
                  project.open ? "Close project" : "Open project",
                  () => project.open ? client.closeProject({ root: project.root }) : client.openProject({ root: project.root }),
                )}>{project.open ? "Close project" : "Open project"}</Button>
              ) : null}
              {project.lifecycleState === "active" && !project.open ? (
                <Button disabled={busy !== null} onClick={() => void run("Archive project", () => client.archiveProject({ root: project.root }))}>
                  Archive project
                </Button>
              ) : null}
              {project.lifecycleState === "archived" ? (
                <Button disabled={busy !== null} onClick={() => void run("Restore project", () => client.restoreProject({ root: project.root }))}>
                  Restore project
                </Button>
              ) : null}
            </div>
            {!project.open && project.lifecycleState !== "trash" ? (
              <div className="project-delete-boundary">
                <Typography as="h3" variant="section-title">Move to recoverable trash</Typography>
                <p>This moves only this project package. The shared model cache is not deleted.</p>
                <Field
                  id="project-delete-confirmation"
                  label="Exact deletion confirmation"
                  description={`Enter ${project.deleteConfirmation} to confirm.`}
                  input={{ value: deleteConfirmation, onChange: (event) => setDeleteConfirmation(event.currentTarget.value), autoComplete: "off" }}
                />
                <Button
                  disabled={busy !== null || deleteConfirmation !== project.deleteConfirmation}
                  onClick={() => void run("Move project to recoverable trash", () => client.deleteProject({
                    root: project.root,
                    confirmation: deleteConfirmation,
                  }))}
                >Move to recoverable trash</Button>
              </div>
            ) : null}
          </div>
        )}
      </Panel>
    </section>
  );
}
