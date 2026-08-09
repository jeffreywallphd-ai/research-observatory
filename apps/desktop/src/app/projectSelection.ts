import type { DesktopRoute } from "./routes";

export const PROJECT_RECENTS_STORAGE_KEY = "research-observatory.project-recents.v1";
export const PROJECT_SELECTION_EVENT = "research-observatory:project-intent";

const PROJECT_ID = /^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$/u;

export interface RecentProject {
  readonly id: string;
  readonly title: string;
  readonly useCase: string;
  readonly lastOpenedAt: string;
  readonly availability: "available" | "missing";
}

export interface ProjectPreferencesV1 {
  readonly schemaVersion: 1;
  readonly removedProjectIds: readonly string[];
}

export type ProjectSelectionIntent =
  | { readonly type: "open-existing"; readonly projectId: string }
  | { readonly type: "locate-existing"; readonly projectId: string }
  | { readonly type: "remove-recent"; readonly projectId: string }
  | { readonly type: "create-new" };

export interface KeyValueStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

export const DEFAULT_RECENT_PROJECTS: readonly RecentProject[] = [
  {
    id: "generative-ai-creative-cognition",
    title: "Generative AI and Creative Cognition",
    useCase: "Theory synthesis",
    lastOpenedAt: "2026-08-08T14:00:00Z",
    availability: "available",
  },
  {
    id: "community-governed-ai",
    title: "Community-Governed AI",
    useCase: "Critical problematization",
    lastOpenedAt: "2026-08-07T14:00:00Z",
    availability: "available",
  },
  {
    id: "recurrent-staged-loras",
    title: "Recurrent Staged LoRAs",
    useCase: "Technical landscape / benchmark audit",
    lastOpenedAt: "2026-08-06T14:00:00Z",
    availability: "missing",
  },
  {
    id: "digital-control-worker-autonomy",
    title: "Digital Control and Worker Autonomy",
    useCase: "Hermeneutic inquiry",
    lastOpenedAt: "2026-08-05T14:00:00Z",
    availability: "available",
  },
];

const EMPTY_PREFERENCES: ProjectPreferencesV1 = Object.freeze({
  schemaVersion: 1,
  removedProjectIds: Object.freeze([]),
});

function assertProject(project: RecentProject): void {
  if (!PROJECT_ID.test(project.id)) throw new Error(`invalid recent project id: ${project.id}`);
  if (!project.title.trim() || !project.useCase.trim()) throw new Error(`recent project ${project.id} lacks a label`);
  const parsedTimestamp = Date.parse(project.lastOpenedAt);
  const canonicalTimestamp = Number.isFinite(parsedTimestamp)
    ? new Date(parsedTimestamp).toISOString().replace(".000Z", "Z")
    : null;
  if (canonicalTimestamp !== project.lastOpenedAt) {
    throw new Error(`recent project ${project.id} has an invalid last-opened timestamp`);
  }
  if (project.availability !== "available" && project.availability !== "missing") {
    throw new Error(`recent project ${project.id} has an invalid availability`);
  }
}

function validRemovedIds(value: unknown): value is string[] {
  if (!Array.isArray(value) || value.length > 64 || !value.every((item) => typeof item === "string")) return false;
  if (value.some((item) => !PROJECT_ID.test(item))) return false;
  return new Set(value).size === value.length && value.every((item, index) => index === 0 || value[index - 1]! < item);
}

export function orderRecentProjects(
  projects: readonly RecentProject[],
  preferences: ProjectPreferencesV1,
): RecentProject[] {
  const observed = new Set<string>();
  for (const project of projects) {
    assertProject(project);
    if (observed.has(project.id)) throw new Error(`duplicate recent project id: ${project.id}`);
    observed.add(project.id);
  }
  const removed = new Set(preferences.removedProjectIds);
  return projects
    .filter(({ id }) => !removed.has(id))
    .toSorted((left, right) => right.lastOpenedAt.localeCompare(left.lastOpenedAt) || left.id.localeCompare(right.id));
}

export function loadProjectPreferences(storage: KeyValueStorage): {
  readonly preferences: ProjectPreferencesV1;
  readonly recovery: "project-recents-unavailable" | "unsupported-or-invalid-project-recents" | null;
} {
  let raw: string | null;
  try {
    raw = storage.getItem(PROJECT_RECENTS_STORAGE_KEY);
  } catch {
    return { preferences: EMPTY_PREFERENCES, recovery: "project-recents-unavailable" };
  }
  if (raw === null) return { preferences: EMPTY_PREFERENCES, recovery: null };
  try {
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) throw new Error("not an object");
    const record = parsed as Record<string, unknown>;
    if (
      Object.keys(record).toSorted().join(",") !== "removedProjectIds,schemaVersion" ||
      record.schemaVersion !== 1 ||
      !validRemovedIds(record.removedProjectIds)
    ) {
      throw new Error("invalid preference contract");
    }
    return {
      preferences: { schemaVersion: 1, removedProjectIds: Object.freeze([...record.removedProjectIds]) },
      recovery: null,
    };
  } catch {
    return { preferences: EMPTY_PREFERENCES, recovery: "unsupported-or-invalid-project-recents" };
  }
}

export function forgetRecentProject(
  preferences: ProjectPreferencesV1,
  projectId: string,
): ProjectPreferencesV1 {
  if (!PROJECT_ID.test(projectId)) throw new Error(`invalid recent project id: ${projectId}`);
  return {
    schemaVersion: 1,
    removedProjectIds: [...new Set([...preferences.removedProjectIds, projectId])].toSorted(),
  };
}

export function saveProjectPreferences(
  storage: KeyValueStorage,
  preferences: ProjectPreferencesV1,
): "project-recents-unavailable" | null {
  try {
    storage.setItem(
      PROJECT_RECENTS_STORAGE_KEY,
      JSON.stringify({ schemaVersion: 1, removedProjectIds: preferences.removedProjectIds }),
    );
    return null;
  } catch {
    return "project-recents-unavailable";
  }
}

export function projectIntent(
  project: RecentProject,
  action: "locate" | "open" | "remove",
): ProjectSelectionIntent {
  assertProject(project);
  if (action === "remove") return { type: "remove-recent", projectId: project.id };
  if (action === "locate") {
    if (project.availability !== "missing") throw new Error("available project does not require repair");
    return { type: "locate-existing", projectId: project.id };
  }
  if (project.availability !== "available") throw new Error("missing project requires explicit repair");
  return { type: "open-existing", projectId: project.id };
}

function dispatchIntent(target: Element, intent: ProjectSelectionIntent): boolean {
  const view = target.ownerDocument.defaultView;
  if (!view) return false;
  return target.dispatchEvent(
    new view.CustomEvent<ProjectSelectionIntent>(PROJECT_SELECTION_EVENT, {
      bubbles: true,
      cancelable: true,
      detail: Object.freeze(intent),
    }),
  );
}

function browserStorage(documentRoot: Document): KeyValueStorage {
  return {
    getItem(key: string): string | null {
      const view = documentRoot.defaultView;
      if (!view) throw new Error("window unavailable");
      return view.localStorage.getItem(key);
    },
    setItem(key: string, value: string): void {
      const view = documentRoot.defaultView;
      if (!view) throw new Error("window unavailable");
      view.localStorage.setItem(key, value);
    },
  };
}

function projectStatus(documentRoot: Document): HTMLElement {
  const existing = documentRoot.querySelector<HTMLElement>("[data-project-selection-status]");
  if (existing) return existing;
  const status = documentRoot.createElement("div");
  status.className = "notice";
  status.dataset.projectSelectionStatus = "idle";
  status.setAttribute("role", "status");
  status.setAttribute("aria-live", "polite");
  status.hidden = true;
  const workflow = documentRoot.querySelector("main#main-content .workflow-context");
  workflow?.insertAdjacentElement("afterend", status);
  return status;
}

function announce(status: HTMLElement, state: "error" | "recovery" | "success", message: string): void {
  status.dataset.projectSelectionStatus = state;
  status.textContent = message;
  status.hidden = false;
}

function renderEmptyState(documentRoot: Document, grid: HTMLElement): void {
  if (grid.querySelector("[data-project-empty-state]")) return;
  const empty = documentRoot.createElement("article");
  empty.className = "card card-lg";
  empty.dataset.projectEmptyState = "ready";
  const title = documentRoot.createElement("h2");
  title.className = "section-title";
  title.textContent = "No recent projects";
  const explanation = documentRoot.createElement("p");
  explanation.className = "small muted";
  explanation.textContent = "Open an existing project location or explicitly create a new local project.";
  const create = documentRoot.createElement("a");
  create.className = "btn btn-primary";
  create.href = "new-project.html";
  create.textContent = "New local project";
  empty.append(title, explanation, create);
  grid.append(empty);
}

function installProjectsPage(documentRoot: Document): () => void {
  const cleanups: Array<() => void> = [];
  const status = projectStatus(documentRoot);
  const grid = documentRoot.querySelector<HTMLElement>("main#main-content section.grid.grid-3.section");
  if (!grid) {
    documentRoot.body.dataset.projectSelection = "recovery-required";
    announce(status, "error", "Project selection is unavailable because the approved project grid is missing.");
    return () => undefined;
  }
  const storage = browserStorage(documentRoot);
  const loaded = loadProjectPreferences(storage);
  let preferences = loaded.preferences;
  if (loaded.recovery) {
    announce(
      status,
      "recovery",
      "Recent-project preferences could not be trusted. Defaults are shown without rewriting the stored record.",
    );
  }

  let projects: RecentProject[];
  try {
    projects = orderRecentProjects(DEFAULT_RECENT_PROJECTS, preferences);
  } catch (error) {
    documentRoot.body.dataset.projectSelection = "recovery-required";
    announce(status, "error", error instanceof Error ? error.message : "Project catalog is invalid.");
    return () => undefined;
  }
  const cards = [...grid.querySelectorAll<HTMLElement>(":scope > article.card")];
  const cardsByTitle = new Map(
    cards.map((card) => [card.querySelector(".section-title")?.textContent?.trim() ?? "", card] as const),
  );
  if (cardsByTitle.size !== DEFAULT_RECENT_PROJECTS.length) {
    documentRoot.body.dataset.projectSelection = "recovery-required";
    announce(status, "error", "The approved project catalog does not match the application fixture.");
    return () => undefined;
  }

  const activeIds = new Set(projects.map(({ id }) => id));
  for (const project of DEFAULT_RECENT_PROJECTS) {
    const card = cardsByTitle.get(project.title);
    if (!card) {
      documentRoot.body.dataset.projectSelection = "recovery-required";
      announce(status, "error", `The approved project card is missing: ${project.title}`);
      return () => undefined;
    }
    if (!activeIds.has(project.id)) {
      card.remove();
      continue;
    }
    card.dataset.recentProjectId = project.id;
    card.dataset.projectAvailability = project.availability;
    const primary = card.querySelector<HTMLAnchorElement>(".source-actions a.btn-primary");
    const remove = card.querySelector<HTMLButtonElement>(".source-actions button");
    const badge = card.querySelector<HTMLElement>(".badge");
    if (!primary || !remove || !badge) {
      documentRoot.body.dataset.projectSelection = "recovery-required";
      announce(status, "error", `Project actions are incomplete: ${project.title}`);
      return () => undefined;
    }
    primary.dataset.projectAction = project.availability === "available" ? "open-existing" : "locate-existing";
    remove.dataset.projectAction = "remove-recent";
    remove.textContent = "Remove";
    remove.setAttribute("aria-label", `Remove ${project.title} from recent projects`);
    if (project.availability === "missing") {
      badge.className = "badge badge-warning";
      badge.textContent = "Location unavailable";
      primary.textContent = "Locate project";
      const locateListener = (event: Event): void => {
        event.preventDefault();
        dispatchIntent(primary, projectIntent(project, "locate"));
        announce(status, "recovery", "Choose the existing project location or remove this recent entry.");
      };
      primary.addEventListener("click", locateListener);
      cleanups.push(() => primary.removeEventListener("click", locateListener));
    } else {
      const openListener = (event: Event): void => {
        event.preventDefault();
        dispatchIntent(primary, projectIntent(project, "open"));
        announce(status, "recovery", "The local project authority must confirm this existing project before it opens.");
      };
      primary.addEventListener("click", openListener);
      cleanups.push(() => primary.removeEventListener("click", openListener));
    }
    const removeListener = (event: Event): void => {
      event.preventDefault();
      const next = forgetRecentProject(preferences, project.id);
      const saveError = saveProjectPreferences(storage, next);
      if (saveError) {
        announce(status, "error", "The recent entry was not removed because preferences are unavailable.");
        return;
      }
      preferences = next;
      dispatchIntent(remove, projectIntent(project, "remove"));
      card.remove();
      announce(status, "success", `${project.title} was removed from recent projects.`);
      const remaining = grid.querySelectorAll(":scope > article.card[data-recent-project-id]").length;
      documentRoot.body.dataset.recentProjectCount = String(remaining);
      if (remaining === 0) renderEmptyState(documentRoot, grid);
    };
    remove.addEventListener("click", removeListener);
    cleanups.push(() => remove.removeEventListener("click", removeListener));
  }
  if (projects.length === 0) renderEmptyState(documentRoot, grid);
  documentRoot.body.dataset.projectSelection = "ready";
  documentRoot.body.dataset.recentProjectCount = String(projects.length);
  return () => cleanups.forEach((cleanup) => cleanup());
}

function installNewProjectPage(documentRoot: Document): () => void {
  const create = documentRoot.querySelector<HTMLAnchorElement>(
    'main#main-content .page-actions a.btn-primary[href="intent-contract.html"]',
  );
  if (!create) {
    documentRoot.body.dataset.projectSelection = "recovery-required";
    return () => undefined;
  }
  create.dataset.projectAction = "create-new";
  const listener = (event: Event): void => {
    event.preventDefault();
    dispatchIntent(create, { type: "create-new" });
  };
  create.addEventListener("click", listener);
  documentRoot.body.dataset.projectSelection = "ready";
  return () => create.removeEventListener("click", listener);
}

export function installProjectSelection(documentRoot: Document, route: DesktopRoute): () => void {
  if (route === "projects.html") return installProjectsPage(documentRoot);
  if (route === "new-project.html") return installNewProjectPage(documentRoot);
  return () => undefined;
}
