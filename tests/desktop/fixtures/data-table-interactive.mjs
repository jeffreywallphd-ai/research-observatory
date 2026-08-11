import { mkdir } from "node:fs/promises";
import { dirname, isAbsolute, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const fixtureRoot = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(fixtureRoot, "..", "..", "..");
const packageRoot = join(repoRoot, "packages", "ui-components");
const viteModule = join(packageRoot, "node_modules", "vite", "dist", "node", "index.js");
const outputRoot = process.argv[2];
if (!outputRoot || !isAbsolute(outputRoot)) {
  throw new Error("interactive DataTable output must be an absolute temporary directory");
}

await mkdir(outputRoot, { recursive: true });
const { build } = await import(pathToFileURL(viteModule).href);
await build({
  configFile: false,
  logLevel: "silent",
  root: packageRoot,
  resolve: {
    alias: {
      react: join(packageRoot, "node_modules", "react"),
      "react-dom": join(packageRoot, "node_modules", "react-dom"),
      "@research-observatory/ui-tokens": join(repoRoot, "packages", "ui-tokens", "src", "index.ts"),
    },
  },
  define: {
    "process.env.NODE_ENV": JSON.stringify("production"),
  },
  build: {
    outDir: outputRoot,
    emptyOutDir: true,
    minify: false,
    lib: {
      entry: join(fixtureRoot, "data-table-interactive.tsx"),
      formats: ["iife"],
      name: "ResearchObservatoryDataTableHarness",
      fileName: () => "data-table-interactive.js",
    },
  },
});
