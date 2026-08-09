import { hydrateRoot } from "react-dom/client";

import { ApplicationRuntime } from "./app/ApplicationRuntime";
import { resolveDesktopRoute } from "./app/routes";

const purpose = document.querySelector<HTMLElement>("main#main-content .page-header .page-subtitle");
if (purpose) {
  const text = purpose.textContent?.trim() ?? "";
  hydrateRoot(purpose, <ApplicationRuntime route={resolveDesktopRoute(window.location.pathname)} text={text} />);
}
