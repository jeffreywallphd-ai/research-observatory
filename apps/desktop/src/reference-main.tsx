import { hydrateRoot } from "react-dom/client";

import { ApplicationRuntime as ReferenceRuntime } from "./app/ReferenceRuntime";
import { resolveDesktopRoute } from "./app/routes";

const purpose = document.querySelector<HTMLElement>("main#main-content .page-header .page-subtitle");
if (purpose) {
  const text = purpose.textContent?.trim() ?? "";
  hydrateRoot(purpose, <ReferenceRuntime route={resolveDesktopRoute(window.location.pathname)} text={text} />);
}
