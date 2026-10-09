import { build, loadConfigFromFile } from "../../../node_modules/vite/dist/node/index.js";
import { resolve } from "node:path";

const repo = resolve(import.meta.dirname, "../../..");
const output = resolve(process.env.RO_VIEWER_DECODER_FIXTURE ?? "");
if (!output.startsWith(resolve(repo, "artifacts/tmp") + "/") && !output.startsWith(resolve(repo, "artifacts/tmp") + "\\")) {
  throw new Error("decoder-fixture-output-not-owned");
}
const { config } = await loadConfigFromFile({ command: "build", mode: "production" }, resolve(repo, "apps/desktop/vite.product.config.ts"));
await build({ ...config, root: resolve(repo, "apps/desktop"), configFile: false,
  build: { ...config.build, outDir: output, emptyOutDir: false,
    rollupOptions: { input: resolve(import.meta.dirname, "viewer-decoder.ts"),
      output: { entryFileNames: "decoder.js", chunkFileNames: "[name].js", assetFileNames: "[name][extname]" } } } });
