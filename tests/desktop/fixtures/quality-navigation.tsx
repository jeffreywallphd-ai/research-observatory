// Production ApplicationRuntime navigation with authored child/transport doubles.
// This proves callback ownership only; the actual correction port is qualified separately.
import React from "react";
import {createRoot} from "react-dom/client";
import {ApplicationRuntime} from "../../../apps/desktop/src/app/ApplicationRuntime";
import "../../../packages/ui-tokens/index.css";
import "../../../packages/ui-components/src/styles.css";
import "../../../apps/desktop/src/app.css";
createRoot(document.getElementById("root")!).render(<ApplicationRuntime />);
