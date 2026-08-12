import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { build } from "vite";

import {
  BoundaryStatePanel,
  DataTable,
  DialogSurface,
  EvidenceStateBadge,
  StatusBadge,
  UncertaintyState,
} from "@research-observatory/ui-components";

describe("ui-components package boundary", () => {
  it("bounds a 10,000-row table to one accessible pagination window", () => {
    const rows = Array.from({ length: 10_000 }, (_value, index) => ({
      id: `record-${index}`,
      title: `Research record ${index}`,
    }));
    const markup = renderToStaticMarkup(
      <DataTable
        caption="Large evidence inventory"
        columns={[
          { id: "id", label: "Identifier" },
          { id: "title", label: "Title" },
        ]}
        rows={rows}
        rowKey={(row) => String(row.id)}
        pageSize={50}
      />,
    );

    expect(markup.match(/<tr/g)).toHaveLength(51);
    expect(markup).toContain('data-total-rows="10000"');
    expect(markup).toContain('data-rendered-rows="50"');
    expect(markup).toContain("Rows 1-50 of 10000");
    expect(markup).toContain("Page 1 of 200");
    expect(markup).toContain("Research record 49");
    expect(markup).not.toContain("Research record 50");
    expect(markup).not.toContain("Research record 9999");
    expect(markup).toContain('aria-label="Large evidence inventory pagination"');
  });

  it("rejects page sizes that could restore eager unbounded rendering", () => {
    const render = (pageSize: number) => renderToStaticMarkup(
      <DataTable
        caption="Bounded table"
        columns={[{ id: "id", label: "Identifier" }]}
        rows={[{ id: "record-1" }]}
        rowKey={(row) => String(row.id)}
        pageSize={pageSize}
      />,
    );

    for (const invalid of ([-1, 0, 1.5, 201, Number.NaN, Number.POSITIVE_INFINITY])) {
      expect(() => render(invalid)).toThrow("page size");
    }
  });

  it("resolves its public runtime and accessible dialog contract by package name", () => {
    const markup = renderToStaticMarkup(
      <DialogSurface id="package-dialog" title="Package dialog" open>
        <StatusBadge>Ready</StatusBadge>
        <EvidenceStateBadge state="verified" />
        <UncertaintyState state="not-reported" />
        <BoundaryStatePanel
          state="failed"
          title="Local operation failed"
          message="Input remains available."
          diagnosticReference="RO-CORE-STARTING"
          onRetry={() => undefined}
        >
          <p>Retained input</p>
        </BoundaryStatePanel>
      </DialogSurface>,
    );

    expect(markup).toContain('aria-labelledby="package-dialog-title"');
    expect(markup).toContain('id="package-dialog-title"');
    expect(markup).toContain("Package dialog");
    expect(markup).toContain('data-boundary-state="failed"');
    expect(markup).toContain("RO-CORE-STARTING");
    expect(markup).toContain("Retained input");
  });

  it("tree-shakes components that a package consumer does not import", async () => {
    const packageRoot = fileURLToPath(new URL("..", import.meta.url));
    const temporary = await mkdtemp(join(tmpdir(), "ro-ui-components-"));
    const entry = join(temporary, "tree-shake-entry.ts");
    await writeFile(entry, 'export { StatusBadge } from "@research-observatory/ui-components";\n', "utf8");
    try {
      const result = await build({
        configFile: false,
        logLevel: "silent",
        root: packageRoot,
        resolve: {
          alias: {
            "@research-observatory/ui-components": fileURLToPath(new URL("../src/index.tsx", import.meta.url)),
          },
        },
        build: {
          write: false,
          minify: false,
          lib: {
            entry,
            formats: ["es"],
          },
          rollupOptions: {
            external: ["react", "react/jsx-runtime", "@research-observatory/ui-tokens"],
          },
        },
      });
      const buildResults = Array.isArray(result) ? result : [result];
      const outputs = buildResults.flatMap((item) => ("output" in item ? item.output : []));
      const code = outputs
        .map((item) => (item.type === "chunk" ? item.code : ""))
        .join("\n");

      expect(code).toContain("ro-status-badge");
      expect(code).not.toContain("ro-dialog");
      expect(code).not.toContain("ro-table");
    } finally {
      await rm(temporary, { recursive: true, force: true });
    }
  });
});
