import { performance } from "node:perf_hooks";

import { renderToStaticMarkup } from "react-dom/server";

import { DataTable } from "../src/index";

export const DATA_TABLE_FIXTURE_VERSION = "data-table-10000-v1" as const;
export const DATA_TABLE_TOTAL_ROWS = 10_000;
export const DATA_TABLE_PAGE_SIZE = 50;
export const DATA_TABLE_REPETITIONS = 20;
export const DATA_TABLE_RENDERS_PER_SAMPLE = 200;
export const DATA_TABLE_WARMUP_BATCHES = 5;

const columns = [
  { id: "id", label: "Identifier" },
  { id: "title", label: "Title" },
  { id: "state", label: "State" },
] as const;

const rows = Array.from({ length: DATA_TABLE_TOTAL_ROWS }, (_value, index) => Object.freeze({
  id: `RO-RECORD-${index.toString().padStart(5, "0")}`,
  title: `Research record ${index}`,
  state: index % 2 === 0 ? "Observed" : "Not reported",
}));

function renderPage(initialPage: number): string {
  return renderToStaticMarkup(
    <DataTable
      caption="10,000-row research inventory"
      columns={columns}
      rows={rows}
      rowKey={(row) => String(row.id)}
      pageSize={DATA_TABLE_PAGE_SIZE}
      initialPage={initialPage}
      compact
    />,
  );
}

function renderedBodyRows(markup: string): number {
  return (markup.match(/<tr/g) ?? []).length - 1;
}

function validateWindow(markup: string, page: "first" | "last"): void {
  if (renderedBodyRows(markup) !== DATA_TABLE_PAGE_SIZE) {
    throw new Error("benchmark table did not preserve its bounded render window");
  }
  if (!markup.includes('data-total-rows="10000"') || !markup.includes('data-rendered-rows="50"')) {
    throw new Error("benchmark table omitted its exact inventory and render-window identity");
  }
  if (page === "first") {
    if (!markup.includes("Research record 49") || markup.includes("Research record 50")) {
      throw new Error("benchmark first page did not contain the exact first window");
    }
  } else if (
    !markup.includes("Research record 9950")
    || !markup.includes("Research record 9999")
    || markup.includes("Research record 9949")
  ) {
    throw new Error("benchmark last page did not contain the exact final window");
  }
}

export function runDataTableBenchmark() {
  const lastPage = DATA_TABLE_TOTAL_ROWS / DATA_TABLE_PAGE_SIZE - 1;
  const warmFirst = renderPage(0);
  const warmLast = renderPage(lastPage);
  validateWindow(warmFirst, "first");
  validateWindow(warmLast, "last");

  for (let batch = 0; batch < DATA_TABLE_WARMUP_BATCHES; batch += 1) {
    for (let renderIndex = 0; renderIndex < DATA_TABLE_RENDERS_PER_SAMPLE; renderIndex += 1) {
      const first = renderIndex % 2 === 0;
      validateWindow(renderPage(first ? 0 : lastPage), first ? "first" : "last");
    }
  }

  const samplesMs: number[] = [];
  for (let repetition = 0; repetition < DATA_TABLE_REPETITIONS; repetition += 1) {
    const startedAt = performance.now();
    for (let renderIndex = 0; renderIndex < DATA_TABLE_RENDERS_PER_SAMPLE; renderIndex += 1) {
      const first = renderIndex % 2 === 0;
      const markup = renderPage(first ? 0 : lastPage);
      validateWindow(markup, first ? "first" : "last");
    }
    samplesMs.push(performance.now() - startedAt);
  }

  return {
    schemaVersion: "1.0",
    documentType: "ui-component-performance-samples",
    fixture: {
      version: DATA_TABLE_FIXTURE_VERSION,
      totalRows: DATA_TABLE_TOTAL_ROWS,
      columns: columns.length,
      pageSize: DATA_TABLE_PAGE_SIZE,
      pageCount: DATA_TABLE_TOTAL_ROWS / DATA_TABLE_PAGE_SIZE,
      maximumRenderedRows: renderedBodyRows(warmFirst),
      firstPageMarkupBytes: Buffer.byteLength(warmFirst, "utf8"),
      lastPageMarkupBytes: Buffer.byteLength(warmLast, "utf8"),
    },
    methodology: {
      state: "warm after five unmeasured render batches; the immutable dataset is constructed before timing",
      operation: "alternating first/last accessible server-rendered pagination windows",
      repetitions: DATA_TABLE_REPETITIONS,
      rendersPerSample: DATA_TABLE_RENDERS_PER_SAMPLE,
      warmupBatches: DATA_TABLE_WARMUP_BATCHES,
      distribution: "nearest-rank p50 and p95 over every measured batch; no samples discarded",
    },
    samplesMs,
  };
}
