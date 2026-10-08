import { resolve, join, isAbsolute } from "node:path";
import { build, loadConfigFromFile } from "../../../node_modules/vite/dist/node/index.js";
const repo = resolve(import.meta.dirname, "../../.."), output = process.argv[2];
if (!output || !isAbsolute(output) || !resolve(output).startsWith(join(repo, "artifacts", "tmp") + (process.platform === "win32" ? "\\" : "/"))) throw new Error("Use an owned absolute artifacts/tmp output");
const { config } = await loadConfigFromFile({ command: "build", mode: "production" }, join(repo, "apps/desktop/vite.product.config.ts"));
await build({ ...config, configFile: false, root: join(repo, "apps/desktop"), logLevel: "silent",
  build: { ...config.build, outDir: output, emptyOutDir: false, minify: false,
    rollupOptions: { input: join(import.meta.dirname, "document-viewer.tsx"), output: { entryFileNames: "document-viewer.js", assetFileNames: "[name][extname]" } } } });
