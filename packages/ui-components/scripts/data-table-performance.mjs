import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { build } from "vite";

const packageRoot = dirname(dirname(fileURLToPath(import.meta.url)));
const temporary = await mkdtemp(join(tmpdir(), "ro-data-table-performance-"));

try {
  await build({
    configFile: false,
    logLevel: "silent",
    root: packageRoot,
    define: {
      "process.env.NODE_ENV": JSON.stringify("production"),
    },
    ssr: {
      noExternal: true,
    },
    build: {
      ssr: join(packageRoot, "benchmarks", "data-table-10000.tsx"),
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
