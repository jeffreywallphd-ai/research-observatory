import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import "@research-observatory/ui-tokens/index.css";
import "@research-observatory/ui-components/styles.css";
import "./app.css";

import { ApplicationRuntime } from "./app/ApplicationRuntime";

const root = document.getElementById("root");
if (!root) throw new Error("desktop application root is unavailable");

createRoot(root).render(
  <StrictMode>
    <ApplicationRuntime />
  </StrictMode>,
);
