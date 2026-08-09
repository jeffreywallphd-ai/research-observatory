import type { DesktopRoute } from "./routes";
import { canonicalDesktopPath, resolveDesktopRoute } from "./routes";

export const REQUIRED_FRAME_REGIONS = [
  ["title bar", "header.topbar"],
  ["project context", "a.project-switcher[href]"],
  ["command area", "label.global-search input[type='search']"],
  ["navigation rail", "aside.sidebar nav.nav-scroll"],
  ["workspace", "main#main-content"],
] as const;

interface FrameQuery {
  querySelector(selectors: string): Element | null;
}

export function frameContractErrors(root: FrameQuery): readonly string[] {
  return REQUIRED_FRAME_REGIONS.flatMap(([label, selector]) =>
    root.querySelector(selector) ? [] : [`missing application frame ${label}: ${selector}`],
  );
}

export function nextNavigationIndex(
  current: number,
  length: number,
  key: "ArrowDown" | "ArrowUp" | "End" | "Home",
): number {
  if (length <= 0) return -1;
  if (key === "Home") return 0;
  if (key === "End") return length - 1;
  if (key === "ArrowDown") return (Math.max(current, -1) + 1) % length;
  return (current <= 0 ? length : current) - 1;
}

export function routeFromNavigationHref(href: string | null): DesktopRoute | null {
  if (!href) return null;
  const canonical = canonicalDesktopPath(href);
  if (canonical === null) return null;
  const resolved = resolveDesktopRoute(canonical);
  return resolved === "index.html" && !/(?:^|\/)index\.html$/u.test(canonical) ? null : resolved;
}

export function installApplicationFrame(documentRoot: Document, currentRoute: DesktopRoute): () => void {
  const errors = frameContractErrors(documentRoot);
  documentRoot.body.dataset.applicationFrame = errors.length === 0 ? "ready" : "recovery-required";
  documentRoot.body.dataset.currentWorkspace = currentRoute;
  if (errors.length > 0) {
    documentRoot.body.dataset.applicationFrameError = errors.join("; ");
    return () => undefined;
  }

  const navigationItems = (): HTMLAnchorElement[] => {
    const observedRoutes = new Set<DesktopRoute>();
    return [...documentRoot.querySelectorAll<HTMLAnchorElement>("aside.sidebar a.nav-item[href]")].filter((anchor) => {
      if (anchor.closest("details:not([open])")) return false;
      const route = routeFromNavigationHref(anchor.getAttribute("href"));
      if (route === null || observedRoutes.has(route)) return false;
      observedRoutes.add(route);
      return true;
    });
  };
  documentRoot.body.dataset.navigationWorkspaces = String(navigationItems().length);
  const localAnchors = [...documentRoot.querySelectorAll<HTMLAnchorElement>("a[href]")].filter(
    (anchor) => routeFromNavigationHref(anchor.getAttribute("href")) !== null,
  );
  for (const anchor of localAnchors) {
    if (routeFromNavigationHref(anchor.getAttribute("href")) === currentRoute) {
      anchor.setAttribute("aria-current", "page");
    } else if (anchor.getAttribute("aria-current") === "page") {
      anchor.removeAttribute("aria-current");
    }
  }

  const onCommandKeyDown = (event: KeyboardEvent): void => {
    if (event.ctrlKey && !event.altKey && !event.metaKey && event.key.toLowerCase() === "k") {
      event.preventDefault();
      documentRoot.querySelector<HTMLInputElement>("label.global-search input[type='search']")?.focus();
    }
  };
  const onNavigationKeyDown = (event: KeyboardEvent): void => {
    if (!(["ArrowDown", "ArrowUp", "End", "Home"] as const).includes(event.key as never)) return;
    const view = documentRoot.defaultView;
    if (!view || !(event.target instanceof view.HTMLAnchorElement)) return;
    const currentRoute = routeFromNavigationHref(event.target.getAttribute("href"));
    const navigation = navigationItems();
    const current = navigation.findIndex(
      (anchor) => routeFromNavigationHref(anchor.getAttribute("href")) === currentRoute,
    );
    if (current < 0) return;
    event.preventDefault();
    navigation[
      nextNavigationIndex(current, navigation.length, event.key as "ArrowDown" | "ArrowUp" | "End" | "Home")
    ]?.focus();
  };
  documentRoot.addEventListener("keydown", onCommandKeyDown);
  documentRoot.addEventListener("keydown", onNavigationKeyDown);
  return () => {
    documentRoot.removeEventListener("keydown", onCommandKeyDown);
    documentRoot.removeEventListener("keydown", onNavigationKeyDown);
  };
}
