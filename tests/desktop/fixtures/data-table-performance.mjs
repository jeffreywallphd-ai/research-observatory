import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const fixtureRoot = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(fixtureRoot, "..", "..", "..");
const packageRoot = join(repoRoot, "packages", "ui-components");
const viteModule = join(packageRoot, "node_modules", "vite", "dist", "node", "index.js");
const { build } = await import(pathToFileURL(viteModule).href);
const temporary = await mkdtemp(join(tmpdir(), "ro-data-table-performance-"));

try {
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
    ssr: {
      noExternal: true,
    },
    build: {
      ssr: join(fixtureRoot, "data-table-10000.tsx"),
      outDir: temporary,
      emptyOutDir: true,
      minify: false,
      rollupOptions: {
        output: {
          entryFileNames: "benchmark.mjs",
        },
      },
    },
  });
  const benchmark = await import(`${pathToFileURL(join(temporary, "benchmark.mjs")).href}?${Date.now()}`);
  process.stdout.write(JSON.stringify(benchmark.runDataTableBenchmark()));
} finally {
  await rm(temporary, { recursive: true, force: true });
}
