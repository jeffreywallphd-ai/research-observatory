import type { DesktopRoute } from "./routes";
import { resolveDesktopRoute } from "./routes";

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
  let decoded: string;
  try {
    decoded = decodeURIComponent(href.split(/[?#]/u, 1)[0] ?? "");
  } catch {
    return null;
  }
  if (
    decoded.includes("\\") ||
    decoded.startsWith("//") ||
    /^[a-z][a-z0-9+.-]*:/iu.test(decoded) ||
    decoded.split("/").some((segment) => segment === "." || segment === "..")
  ) {
    return null;
  }
  const resolved = resolveDesktopRoute(decoded);
  return resolved === "index.html" && !/(?:^|\/)index\.html$/u.test(decoded) ? null : resolved;
}

export function installApplicationFrame(documentRoot: Document, currentRoute: DesktopRoute): () => void {
  const errors = frameContractErrors(documentRoot);
  documentRoot.body.dataset.applicationFrame = errors.length === 0 ? "ready" : "recovery-required";
  if (errors.length > 0) {
    documentRoot.body.dataset.applicationFrameError = errors.join("; ");
    return () => undefined;
  }

  const navigation = [...documentRoot.querySelectorAll<HTMLAnchorElement>("aside.sidebar a.nav-item[href]")].filter(
    (anchor) => routeFromNavigationHref(anchor.getAttribute("href")) !== null,
  );
  for (const anchor of navigation) {
    if (routeFromNavigationHref(anchor.getAttribute("href")) === currentRoute) anchor.setAttribute("aria-current", "page");
    else anchor.removeAttribute("aria-current");
  }

  const onKeyDown = (event: KeyboardEvent): void => {
    if (event.ctrlKey && !event.altKey && !event.metaKey && event.key.toLowerCase() === "k") {
      event.preventDefault();
      documentRoot.querySelector<HTMLInputElement>("label.global-search input[type='search']")?.focus();
      return;
    }
    if (!(["ArrowDown", "ArrowUp", "End", "Home"] as const).includes(event.key as never)) return;
    const view = documentRoot.defaultView;
    if (!view || !(event.target instanceof view.HTMLAnchorElement)) return;
    const current = navigation.indexOf(event.target);
    if (current < 0) return;
    event.preventDefault();
    navigation[nextNavigationIndex(current, navigation.length, event.key as "ArrowDown" | "ArrowUp" | "End" | "Home")]?.focus();
  };
  documentRoot.addEventListener("keydown", onKeyDown);
  return () => documentRoot.removeEventListener("keydown", onKeyDown);
}
