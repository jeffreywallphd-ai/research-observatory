import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { build } from "vite";

import {
  BoundaryStatePanel,
  DialogSurface,
  EvidenceStateBadge,
  StatusBadge,
  UncertaintyState,
} from "@research-observatory/ui-components";

describe("ui-components package boundary", () => {
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
          diagnosticReference="RO-LOCAL-OPERATION-FAILED"
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
    expect(markup).toContain("RO-LOCAL-OPERATION-FAILED");
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
