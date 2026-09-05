import { useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";

import {
  CoreApiClientError,
  createCoreApiClient,
  type CoreApiRequest,
  type CoreApiResponse,
  type CoreApiTransport,
  type ProjectCreateRequest,
  type ProjectProjection,
  type WorkflowProfileCatalogProjection,
} from "@research-observatory/contracts/core-api";
import { invoke } from "@tauri-apps/api/core";
import { Button, DirectoryPickerField, Field, Notification, Panel, StatusBadge, Typography } from "@research-observatory/ui-components";

import { LocalServiceBoundary, type RuntimeState } from "./LocalServiceBoundary";
import { chooseProjectDirectory, defaultProjectParent, projectDestination, projectDirectoryName, type DirectoryPurpose } from "./directoryPicker";

export interface ProjectsWorkspaceProps {
  readonly announce: (message: string) => void;
  readonly transport?: CoreApiTransport;
  readonly selectedProject?: ProjectProjection | null;
  readonly onProjectChange?: (project: ProjectProjection) => void;
  readonly initialCatalog?: WorkflowProfileCatalogProjection | null;
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
  if (project.open) return ["Close project"];
  const actions: string[] = [];
  if (project.lifecycleState === "active") {
    actions.push(project.compatibilityState === "compatible" ? "Open project" : "Open read-only");
  }
  if (project.lifecycleState === "active" && project.compatibilityState === "compatible") actions.push("Archive project");
  if (project.lifecycleState === "archived" && project.compatibilityState === "compatible") {
    actions.push("Restore project");
  }
  if (project.lifecycleState !== "trash" && project.compatibilityState === "compatible") {
    actions.push("Move to recoverable trash");
  }
  return actions;
}

export function projectCompatibilityGuidance(project: ProjectProjection): {
  readonly title: string;
  readonly message: string;
} | null {
  if (project.compatibilityState === "compatible") return null;
  if (project.compatibilityState === "migration-required") {
    return {
      title: "Migration required · read-only",
      message: "Keep the original unchanged. First create and verify a complete backup, then run the reviewed migration against a working copy.",
    };
  }
  return {
    title: "Newer project format · read-only",
    message: "Keep the original unchanged. First create and verify a complete backup, then use a compatible application version with the working copy.",
  };
}

function safeFailure(error: unknown): { readonly title: string; readonly message: string } {
  if (error instanceof CoreApiClientError) {
    if (error.problem.code === "RO-CORE-PROJECT-ALREADY-EXISTS") {
      return {
        title: "The destination already exists",
        message: "Change the project name or choose a different parent folder. The existing folder will not be overwritten; your entries are kept.",
      };
    }
    return {
      title: `${error.problem.title} (${error.problem.code})`,
      message: `${error.problem.detail} ${error.problem.remediation}`,
    };
  }
  if (error instanceof Error && error.message === "RO-CORE-REQUEST-INVALID") {
    return {
      title: "Review project details",
      message: "Check the project name, location, research objective and selected use case. No project request was sent.",
    };
  }
  return {
    title: "RO-CORE-PROJECT-ACTION-FAILED",
    message: "The local project action did not complete. Review Core status and retry once.",
  };
}

export function ProjectsWorkspace({
  announce,
  transport = packagedProjectTransport,
  selectedProject = null,
  onProjectChange,
  initialCatalog = null,
}: ProjectsWorkspaceProps): ReactNode {
  const client = useMemo(() => createCoreApiClient(transport), [transport]);
  const [project, setProject] = useState<ProjectProjection | null>(selectedProject);
  const [parentDirectory, setParentDirectory] = useState("");
  const [folderSuggestionId] = useState(() => globalThis.crypto.randomUUID().replaceAll("-", "").slice(0, 12));
  const [displayName, setDisplayName] = useState("");
  const [researchObjective, setResearchObjective] = useState("");
  const [primaryUseCase, setPrimaryUseCase] = useState<ProjectCreateRequest["primaryUseCase"] | "">(
    initialCatalog?.profiles[0]?.profileId ?? "",
  );
  const [catalog, setCatalog] = useState<WorkflowProfileCatalogProjection | null>(initialCatalog);
  const [openRoot, setOpenRoot] = useState("");
  const [deleteConfirmation, setDeleteConfirmation] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [failure, setFailure] = useState<{ readonly title: string; readonly message: string } | null>(null);
  const [serviceState, setServiceState] = useState<RuntimeState>("starting");
  const [catalogState, setCatalogState] = useState<"waiting" | "loading" | "ready" | "failed">(initialCatalog ? "ready" : "waiting");
  const [catalogAttempt, setCatalogAttempt] = useState(0);
  const mounted = useRef(false);
  const mutationPending = useRef(false);
  const mutationGeneration = useRef(0);
  const folderPending = useRef(false);
  const folderGeneration = useRef(0);
  const folderRequest = useRef<AbortController | null>(null);
  const parentChosenByUser = useRef(false);
  const parentSelectionPending = useRef(false);
  const parentButton = useRef<HTMLButtonElement>(null);
  const openButton = useRef<HTMLButtonElement>(null);
  const restoreFolderFocus = useRef<HTMLButtonElement | null>(null);
  const [folderBusy, setFolderBusy] = useState<DirectoryPurpose | null>(null);
  const [folderNotice, setFolderNotice] = useState<{ title: string; message: string; failed: boolean } | null>(null);
  const [defaultState, setDefaultState] = useState<"waiting" | "loading" | "available" | "unavailable">("waiting");
  const [defaultAttempt, setDefaultAttempt] = useState(0);
  const observesNativeService = transport === packagedProjectTransport && !initialCatalog;
  const serviceReady = !observesNativeService || serviceState === "ready";
  const actionsDisabled = busy !== null || folderBusy !== null || !serviceReady;
  const directoryName = projectDirectoryName(displayName, folderSuggestionId);
  const destination = projectDestination(parentDirectory, directoryName);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      mutationGeneration.current++;
      folderGeneration.current++;
      folderRequest.current?.abort();
      restoreFolderFocus.current = null;
    };
  }, []);

  useEffect(() => {
    if (!serviceReady || parentChosenByUser.current || parentDirectory) return;
    const controller = new AbortController();
    setDefaultState("loading");
    void defaultProjectParent(controller.signal).then((result) => {
      if (controller.signal.aborted || !mounted.current || parentChosenByUser.current || parentSelectionPending.current) return;
      if (result.status === "available") {
        setParentDirectory(result.path);
        setDefaultState("available");
      } else setDefaultState("unavailable");
    });
    return () => controller.abort();
  }, [defaultAttempt, parentDirectory, serviceReady]);

  useEffect(() => {
    if (folderBusy !== null) return;
    const trigger = restoreFolderFocus.current;
    restoreFolderFocus.current = null;
    if (mounted.current && trigger?.isConnected && !trigger.closest("[inert], [hidden]")) trigger.focus();
  }, [folderBusy]);

  const chooseFolder = async (purpose: DirectoryPurpose): Promise<void> => {
    if (!mounted.current || mutationPending.current || folderPending.current) return;
    folderPending.current = true;
    const generation = ++folderGeneration.current;
    if (purpose === "create-parent") parentSelectionPending.current = true;
    const controller = new AbortController();
    folderRequest.current = controller;
    setFolderBusy(purpose);
    setFolderNotice(null);
    const previousLocation = purpose === "create-parent" ? parentDirectory : openRoot;
    const result = await chooseProjectDirectory({ purpose, ...(previousLocation ? { previousLocation } : {}) }, controller.signal);
    folderPending.current = false;
    if (purpose === "create-parent") parentSelectionPending.current = false;
    if (controller.signal.aborted || !mounted.current || generation !== folderGeneration.current) return;
    folderRequest.current = null;
    if (result.status === "selected") {
      if (purpose === "create-parent") {
        parentChosenByUser.current = true;
        setParentDirectory(result.path);
      }
      else setOpenRoot(result.path);
      announce("Folder selected. No project action was performed.");
    } else {
      // An attempted choice is not a selection. A default response discarded
      // during the dialog must be rediscovered after cancel/failure.
      if (purpose === "create-parent" && !parentDirectory) setDefaultAttempt((attempt) => attempt + 1);
      const notice = result.status === "cancelled" ? {
        title: "Selection cancelled", message: "Your previous folder and form entries are unchanged.", failed: false,
      } : result.status === "unavailable" ? {
        title: "The folder chooser is unavailable", message: "Retry from the folder button. No project action was performed.", failed: true,
      } : {
        title: "This folder cannot be used", message: "Choose an accessible local folder. Your form entries are unchanged. No project action was performed.", failed: true,
      };
      setFolderNotice(notice);
      announce(`${notice.title}. ${notice.message}`);
    }
    restoreFolderFocus.current = purpose === "create-parent" ? parentButton.current : openButton.current;
    setFolderBusy(null);
  };

  useEffect(() => setProject(selectedProject), [selectedProject]);

  useEffect(() => {
    if (initialCatalog) {
      setCatalog(initialCatalog);
      setCatalogState("ready");
      return;
    }
    if (!serviceReady) {
      setCatalog(null);
      setCatalogState("waiting");
      return;
    }
    let cancelled = false;
    setCatalogState("loading");
    void client.workflowProfileCatalog().then((next) => {
      if (!cancelled) { setCatalog(next); setCatalogState("ready"); }
    }).catch(() => {
      if (!cancelled) { setCatalog(null); setCatalogState("failed"); }
    });
    return () => { cancelled = true; };
  }, [catalogAttempt, client, initialCatalog, serviceReady]);

  const selectedProfile = catalog?.profiles.find((profile) => profile.profileId === primaryUseCase) ?? null;

  const run = async (label: string, action: () => Promise<ProjectProjection>): Promise<void> => {
    if (!serviceReady || mutationPending.current || folderPending.current || !mounted.current) return;
    mutationPending.current = true;
    const generation = mutationGeneration.current;
    const ownsResult = (): boolean => mounted.current && mutationGeneration.current === generation;
    setBusy(label);
    setFailure(null);
    try {
      const next = await action();
      if (!ownsResult()) return;
      setProject(next);
      onProjectChange?.(next);
      setOpenRoot(next.root);
      setDeleteConfirmation("");
      announce(`${label} completed.`);
    } catch (error) {
      if (!ownsResult()) return;
      const safe = safeFailure(error);
      setFailure(safe);
      announce(`${label} did not complete. ${safe.title}`);
    } finally {
      mutationPending.current = false;
      if (ownsResult()) setBusy(null);
    }
  };

  const createProject = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    if (!serviceReady || !destination || catalogState !== "ready" || !selectedProfile || !primaryUseCase || !researchObjective.trim()) return;
    void run("Create project", () => client.createProject({
      parentDirectory,
      directoryName,
      displayName,
      primaryUseCase,
      researchObjective: researchObjective.trim(),
    }));
  };

  const openProject = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    if (!openRoot) return;
    void run("Open project", () => client.openProject({ root: openRoot }));
  };

  return (
    <section className="projects-workspace ro-page-region" aria-labelledby="projects-title" data-projects-workspace>
      <div className="page-header">
        <Typography id="projects-title" as="h1" variant="page-title">Local projects</Typography>
        <Typography className="page-subtitle">
          Create or open a governed local project package. Project documents remain on this computer.
        </Typography>
      </div>

      {failure ? <Notification tone="danger" title={failure.title}>{failure.message}</Notification> : null}

      {observesNativeService ? <LocalServiceBoundary announce={announce} observeOnly onStateChange={setServiceState} /> : null}
      {folderBusy ? <Notification title="Choosing a folder…">
        Complete or cancel the native dialog. Other folder buttons and project submission remain unavailable while it is open.
      </Notification> : folderNotice ? <Notification tone={folderNotice.failed ? "warning" : "info"} title={folderNotice.title}>
        {folderNotice.message}
      </Notification> : null}

      <div className="project-workflow-grid ro-grid">
        <Panel title="Create a local project">
          <form className="project-form ro-form" onSubmit={createProject}>
            <Field
              id="project-display-name"
              label="Project name"
              description="Use a descriptive name. The application suggests the new folder name for you."
              input={{ value: displayName, onChange: (event) => setDisplayName(event.currentTarget.value), required: true, maxLength: 120, disabled: busy !== null }}
            />
            <DirectoryPickerField id="project-parent-directory" label="Parent folder" value={parentDirectory}
              description={parentDirectory ? "The new project will be created here. Change folder to choose another local location."
                : defaultState === "unavailable" ? "A default folder is not available. Choose an existing accessible local folder."
                  : "Finding your default project folder. You can also choose an existing local folder."}
              buttonRef={parentButton} disabled={busy !== null || folderBusy !== null} pending={folderBusy === "create-parent"}
              onChoose={() => void chooseFolder("create-parent")} />
            <div className="ro-field">
              <span className="ro-field__label" id="project-destination-label">New project destination</span>
              <output className="ro-directory-location" id="project-destination" aria-labelledby="project-destination-label">
                {destination || (parentDirectory && directoryName
                  ? "This destination cannot be used. Shorten the project name or choose another parent folder."
                  : "Enter a project name and select a parent folder to see the destination.")}
              </output>
              <span className="ro-field__description">Review the destination before Create. Existing folders are never overwritten or automatically numbered.</span>
            </div>
            <label htmlFor="project-research-objective">Research objective</label>
            <textarea
              id="project-research-objective"
              value={researchObjective}
              onChange={(event) => setResearchObjective(event.currentTarget.value)}
              rows={3}
              maxLength={4000}
              required
              disabled={busy !== null}
            />
            <label htmlFor="project-primary-use-case">Primary use case</label>
            {catalogState === "failed" ? (
              <Notification tone="danger" title="Could not load use cases">
                <p>Your entries are unchanged. Load the available research types before creating a project.</p>
                <p><code>RO-CORE-CATALOG-FAILED</code></p>
                <Button disabled={!serviceReady || busy !== null} onClick={() => setCatalogAttempt((attempt) => attempt + 1)}>
                  Retry loading use cases
                </Button>
              </Notification>
            ) : catalogState !== "ready" ? (
              <p role="status">{catalogState === "waiting" ? "Waiting for the local service. Your entries are kept here." : "Loading research use cases…"}</p>
            ) : null}
            <select
              id="project-primary-use-case"
              value={primaryUseCase}
              onChange={(event) => setPrimaryUseCase(event.currentTarget.value as ProjectCreateRequest["primaryUseCase"])}
              required
              disabled={busy !== null || !catalog || catalogState !== "ready"}
            >
              <option value="" disabled>{catalogState === "ready" ? "Select a governed use case" : catalogState === "failed" ? "Use cases unavailable" : catalogState === "waiting" ? "Waiting for local service…" : "Loading governed use cases…"}</option>
              {catalog?.profiles.map((profile) => (
                <option key={profile.profileId} value={profile.profileId}>{profile.title}</option>
              ))}
            </select>
            {selectedProfile ? (
              <div className="workflow-profile-preview ro-notice" aria-live="polite">
                <Typography as="h3" variant="section-title">{selectedProfile.title}</Typography>
                <p>{selectedProfile.purpose}</p>
                <p><strong>Expected output:</strong> {selectedProfile.expectedOutputs.join(", ")}</p>
                <p><strong>Process form:</strong> {selectedProfile.processForm === "revisitable" ? "Revisitable process" : "Linear process"}</p>
                <ol>{selectedProfile.stages.map((stage) => <li key={stage.stageKey}>{stage.label}{stage.optional ? " (optional)" : ""}</li>)}</ol>
                <p className="field-note">All tools remain available. The selected workflow does not weaken evidence or provenance requirements.</p>
              </div>
            ) : null}
            <Button tone="primary" type="submit" disabled={actionsDisabled || !destination || catalogState !== "ready" || !selectedProfile || !researchObjective.trim()}>Create project</Button>
          </form>
        </Panel>

        <Panel title="Open an existing project">
          <form className="project-form ro-form" onSubmit={openProject}>
            <DirectoryPickerField id="project-root" label="Project folder" value={openRoot}
              description="Choose an existing Research Observatory project folder, then select Open project. Choosing alone does not open it."
              buttonRef={openButton} disabled={busy !== null || folderBusy !== null} pending={folderBusy === "open-project"}
              onChoose={() => void chooseFolder("open-project")} />
            <Button tone="primary" type="submit" disabled={actionsDisabled || !openRoot}>Open project</Button>
          </form>
        </Panel>
      </div>

      <Panel title="Current project" tone={project ? "success" : "neutral"}>
        {!project ? <p>No project is selected. Create one or open an existing local project.</p> : (
          <div className="current-project ro-card ro-stack" data-current-project={project.projectId}>
            {projectCompatibilityGuidance(project) ? (
              <Notification tone="warning" title={projectCompatibilityGuidance(project)?.title ?? "Read-only project"}>
                {projectCompatibilityGuidance(project)?.message}
              </Notification>
            ) : null}
            <div>
              <Typography as="h2" variant="section-title">{project.displayName}</Typography>
              <p><code>{project.root}</code></p>
              <div className="project-status-row ro-cluster">
                <StatusBadge tone={project.lifecycleState === "active" ? "success" : "warning"}>
                  {project.lifecycleState}
                </StatusBadge>
                <span>{project.accessMode === "read-write" ? "Exclusive local session open" : project.accessMode === "read-only" ? "Read-only inspection open" : "Closed"}</span>
                <span>{project.compatibilityState}</span>
                <span>Revision {project.revision}</span>
              </div>
            </div>
            <div className="project-actions ro-action-row" aria-label="Current project actions">
              {project.lifecycleState === "active" ? (
                <Button disabled={actionsDisabled} onClick={() => void run(
                  project.open ? "Close project" : "Open project",
                  () => project.open ? client.closeProject({ root: project.root }) : client.openProject({ root: project.root }),
                )}>{project.open ? "Close project" : project.compatibilityState === "compatible" ? "Open project" : "Open read-only"}</Button>
              ) : null}
              {project.lifecycleState === "active" && !project.open && project.compatibilityState === "compatible" ? (
                <Button disabled={actionsDisabled} onClick={() => void run("Archive project", () => client.archiveProject({ root: project.root }))}>
                  Archive project
                </Button>
              ) : null}
              {project.lifecycleState === "archived" && project.compatibilityState === "compatible" ? (
                <Button disabled={actionsDisabled} onClick={() => void run("Restore project", () => client.restoreProject({ root: project.root }))}>
                  Restore project
                </Button>
              ) : null}
            </div>
            {!project.open && project.lifecycleState !== "trash" && project.compatibilityState === "compatible" ? (
              <div className="project-delete-boundary ro-notice">
                <Typography as="h3" variant="section-title">Move to recoverable trash</Typography>
                <p>This moves only this project package. The shared model cache is not deleted.</p>
                <Field
                  id="project-delete-confirmation"
                  label="Exact deletion confirmation"
                  description={`Enter ${project.deleteConfirmation} to confirm.`}
                  input={{ value: deleteConfirmation, onChange: (event) => setDeleteConfirmation(event.currentTarget.value), autoComplete: "off" }}
                />
                <Button
                  disabled={actionsDisabled || deleteConfirmation !== project.deleteConfirmation}
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
