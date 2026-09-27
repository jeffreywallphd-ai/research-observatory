// Bundle actual production components for the focused browser/Core contract test.
import path from "node:path";
import { writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";
const repo = process.cwd(), destination = path.resolve(process.argv[2]);
const allowed = path.join(repo, "artifacts", "tmp") + path.sep;
if (!destination.startsWith(allowed)) throw new Error("Harness output must be confined to ignored artifacts");
const app = path.join(repo, "apps", "desktop"), require = createRequire(path.join(app, "package.json"));
const { build } = await import(pathToFileURL(require.resolve("vite")).href);
const { default: react } = await import(pathToFileURL(require.resolve("@vitejs/plugin-react")).href);
const modulePath = (value) => JSON.stringify(value.replaceAll("\\", "/"));
await writeFile(path.join(destination, "entry.ts"), `
import { createElement, createRef } from ${modulePath(require.resolve("react"))};
import { createRoot } from ${modulePath(require.resolve("react-dom/client"))};
import { createCoreApiClient } from ${modulePath(path.join(repo, "packages/contracts/core-api/generated.ts"))};
import { ReconciliationPane } from ${modulePath(path.join(app, "src/app/ReconciliationPane.tsx"))};
import ${modulePath(require.resolve("@research-observatory/ui-tokens/index.css"))};
import ${modulePath(path.join(repo, "packages/ui-components/src/styles.css"))};
import ${modulePath(path.join(app, "src/app.css"))};
const root = createRoot(document.getElementById("root"));
window.requests = []; window.flags = {};
const client = createCoreApiClient(async request => {
  window.requests.push(request);
  if (window.flags.failStatus && request.path.endsWith("batches/status")) throw new Error("Synthetic status failure");
  if (window.flags.failVersionPreview && request.path.endsWith("versions/preview")) throw new Error("Synthetic version preview failure");
  const response = await window.coreExchange(request);
  if (window.flags.dropVersionCommit && request.path.endsWith("versions/commit")) {
    window.flags.dropVersionCommit = false; throw new Error("Synthetic lost version reply");
  }
  if (window.flags.dropCommit && request.path.endsWith("review/commit")) {
    window.flags.dropCommit = false; throw new Error("Synthetic lost commit reply");
  }
  return response;
});
window.reconciliationClient = client;
window.mount = (project) => root.render(createElement(ReconciliationPane, { key: project.projectId,
  ...project, client, headingRef: createRef(), announce: message => document.getElementById("announcer").textContent = message }));
window.clearProtectedState = () => root.render(null);
`);
await writeFile(path.join(destination, "index.html"), '<!doctype html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Reconciliation integration</title></head><body><main id="root"></main><div id="announcer" role="status" aria-live="polite"></div><script type="module" src="./entry.ts"></script></body></html>');
await build({ configFile: false, root: destination, plugins: [react()], logLevel: "warn",
  resolve: { alias: { react: path.dirname(require.resolve("react/package.json")), "react-dom": path.dirname(require.resolve("react-dom/package.json")) } },
  build: { outDir: path.join(destination, "dist"), emptyOutDir: true, target: "es2023" } });
