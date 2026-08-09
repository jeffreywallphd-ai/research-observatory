export const DESKTOP_ROUTES = [
  "index.html",
  "projects.html",
  "new-project.html",
  "intent-contract.html",
  "help-onboarding.html",
  "search-studio.html",
  "source-manager.html",
  "ingestion-reconciliation.html",
  "corpus-canvas.html",
  "screening.html",
  "document-reader.html",
  "research-notebook.html",
  "parsing-quality.html",
  "evidence-matrix.html",
  "schema-manager.html",
  "claim-graph.html",
  "theory-map.html",
  "critical-lens.html",
  "opportunity-radar.html",
  "novelty-audit.html",
  "synthesis-studio.html",
  "living-monitor.html",
  "task-center.html",
  "audit-lineage.html",
  "model-center.html",
  "project-settings.html",
  "study-design.html",
  "manuscript-blueprint.html",
  "technical-reports.html",
  "manuscript-studio.html",
  "reviewer-simulation.html",
  "revision-response.html",
] as const;

export type DesktopRoute = (typeof DESKTOP_ROUTES)[number];
const ROUTES = new Set<string>(DESKTOP_ROUTES);

export function resolveDesktopRoute(pathname: string): DesktopRoute {
  const candidate = pathname.split(/[?#]/u, 1)[0]?.split("/").pop() || "index.html";
  return ROUTES.has(candidate) ? (candidate as DesktopRoute) : "index.html";
}
