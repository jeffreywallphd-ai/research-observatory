import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { Plugin } from "vite";

// Apache-2.0 pdfjs-dist 6.4.299. This product integration bounds request
// grouping and scheduling; source authentication and delivery authority stay
// with Core. A dependency change requires reviewing the exact worker again.
const workerSha256 = "07ceb740d746e5d9012fcf9f27d5c7dea09f7d2f5e74f5c8109e5787551a2333";
const groupingBoundary = "if (prevChunk >= 0 && prevChunk + 1 !== chunk) {";
const managerBoundary = "class ChunkedStreamManager {\n  #aborted = false;";
const requestBoundary = "  async sendRequest(begin, end) {\n    const rangeReader = this.pdfStream.getRangeReader(begin, end);";

export function boundPdfWorkerRanges(source: string): string {
  if (createHash("sha256").update(source).digest("hex") !== workerSha256
    || [groupingBoundary, managerBoundary, requestBoundary].some((boundary) => source.split(boundary).length !== 2)) {
    throw new Error("pdf-worker-pin-mismatch");
  }
  return source.replace(groupingBoundary,
    "if (prevChunk >= 0 && (prevChunk + 1 !== chunk || chunk - beginChunk >= Math.max(1, Math.floor(1048576 / this.chunkSize)))) {")
    .replace(managerBoundary, `${managerBoundary}\n  #rangeTurn = Promise.resolve();`)
    .replace(requestBoundary, `  async sendRequest(begin, end) {
    const previous = this.#rangeTurn;
    const turn = Promise.withResolvers();
    this.#rangeTurn = turn.promise;
    try {
      await previous;
      if (this.#aborted) return;
      await this.#readProtectedRange(begin, end);
    } finally {
      turn.resolve();
    }
  }
  async #readProtectedRange(begin, end) {
    const rangeReader = this.pdfStream.getRangeReader(begin, end);`);
}

export function boundedPdfWorker(): Plugin {
  return {
    name: "protected-pdf-worker-ranges",
    enforce: "pre",
    transform(source, id) {
      if (!id.replaceAll("\\", "/").split("?")[0]?.endsWith("/pdfjs-dist/build/pdf.worker.mjs")) return null;
      return { code: boundPdfWorkerRanges(source), map: null };
    },
  };
}

export function pdfAssetNotices(): Plugin {
  return {
    name: "local-pdf-resource-inventory",
    generateBundle() {
      const inventory = JSON.parse(readFileSync(resolve(import.meta.dirname, "pdfjs-assets.json"), "utf8")) as {
        package: string; version: string; files: Record<string, { source: string; sha256: string }>;
      };
      if (inventory.package !== "pdfjs-dist" || inventory.version !== "6.4.299") throw new Error("pdf-resource-pin-mismatch");
      const root = resolve(import.meta.dirname, "node_modules/pdfjs-dist");
      for (const [name, resource] of Object.entries(inventory.files)) {
        if (!/^assets\/[A-Za-z0-9_.-]+$/u.test(name)
          || !/^(?:(?:cmaps|standard_fonts)\/)?[A-Za-z0-9_.-]+$/u.test(resource.source)) throw new Error("pdf-resource-pin-mismatch");
        const bytes = readFileSync(resolve(root, resource.source));
        if (createHash("sha256").update(bytes).digest("hex") !== resource.sha256) throw new Error("pdf-resource-pin-mismatch");
        if (resource.source === "LICENSE" || resource.source.startsWith("standard_fonts/LICENSE")) {
          this.emitFile({ type: "asset", fileName: name, source: bytes });
        }
      }
    },
  };
}
