import { fileURLToPath, URL } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { boundedPdfWorker, pdfAssetNotices } from "./pdfjsWorkerBuild";

export default defineConfig({
  plugins: [react(), boundedPdfWorker(), pdfAssetNotices()],
  worker: { format: "es", plugins: () => [boundedPdfWorker()],
    rollupOptions: { output: { entryFileNames: "assets/documentViewer.worker.js", chunkFileNames: "assets/pdf.worker.js" } } },
  define: {
    "process.env.NODE_ENV": JSON.stringify("production"),
  },
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  clearScreen: false,
  build: {
    assetsInlineLimit: 0,
    target: "es2023",
    outDir: "product-dist",
    emptyOutDir: true,
    sourcemap: true,
    minify: "oxc",
    rollupOptions: {
      output: {
        entryFileNames: "assets/app.js",
        chunkFileNames: "assets/[name].js",
        assetFileNames: ({ names }) => names.some((name) => name.endsWith(".css"))
          ? "assets/app.css"
          : "assets/[name][extname]",
      },
    },
  },
});
