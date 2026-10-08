import { mkdir } from "node:fs/promises";
import { dirname, isAbsolute, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const fixtureRoot = dirname(fileURLToPath(import.meta.url));
const repo = resolve(fixtureRoot, "../../..");
const desktop = join(repo, "apps/desktop");
const output = process.argv[2];
if (!output || !isAbsolute(output) || !resolve(output).startsWith(join(repo, "artifacts", "tmp") + (process.platform === "win32" ? "\\" : "/"))) throw new Error("Use an owned absolute artifacts/tmp output");
await mkdir(output, { recursive: true });
const { build } = await import(pathToFileURL(join(desktop, "node_modules/vite/dist/node/index.js")).href);
const { default: react } = await import(pathToFileURL(join(desktop, "node_modules/@vitejs/plugin-react/dist/index.js")).href);
await build({ configFile: false, root: desktop, logLevel: "silent", plugins: [react()],
  define: { "process.env.NODE_ENV": JSON.stringify("production") },
  resolve: { alias: {
    react: join(desktop, "node_modules/react"), "react-dom": join(desktop, "node_modules/react-dom"),
    "@research-observatory/ui-components": join(repo, "packages/ui-components/src/index.tsx"),
    "@research-observatory/ui-tokens": join(repo, "packages/ui-tokens/src/index.ts"),
    "@research-observatory/contracts/core-api": join(repo, "packages/contracts/core-api/generated.ts"),
    "@tauri-apps/api": join(desktop, "node_modules/@tauri-apps/api"),
  } },
  build: { outDir: output, emptyOutDir: false, minify: false, lib: {
    entry: join(fixtureRoot, "source-anchor-reader.tsx"), formats: ["iife"], name: "SourceAnchorReaderFixture",
    fileName: () => "source-anchor-reader.js", cssFileName: "source-anchor-reader",
  } },
});
