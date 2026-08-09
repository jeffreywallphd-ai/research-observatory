import { fileURLToPath, URL } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  clearScreen: false,
  build: {
    target: "es2023",
    outDir: "dist/runtime",
    emptyOutDir: false,
    sourcemap: true,
    minify: "oxc",
    lib: {
      entry: "src/main.tsx",
      formats: ["es"],
      fileName: () => "main.js",
    },
    rollupOptions: {
      output: {
        assetFileNames: "[name][extname]",
      },
    },
  },
});
