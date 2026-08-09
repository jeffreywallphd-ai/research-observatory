import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import {
  DataTable,
  DialogSurface,
  Field,
  Notification,
  Panel,
  StatusBadge,
  Typography,
  UI_COMPONENT_CONTRACT_VERSION,
} from "@research-observatory/ui-components";
import type { SemanticTone } from "@research-observatory/ui-tokens";

describe("Academic Minimal design system", () => {
  it("renders accessible component contracts and documented semantic variants", () => {
    const markup = renderToStaticMarkup(
      <main>
        <Typography as="h1" variant="page-title">Evidence workspace</Typography>
        <Field id="query" label="Search" description="Local sources" error="Query is required" />
        <StatusBadge tone="violet">Inferred</StatusBadge>
        <Notification tone="danger" title="Blocked">Evidence is insufficient.</Notification>
        <Panel tone="success" title="Verified evidence" evidenceState="verified">Checked.</Panel>
        <DataTable
          caption="Evidence states"
          columns={[{ id: "state", label: "State" }]}
          rows={[{ state: "Observed" }]}
          rowKey={(row) => String(row.state)}
        />
        <DialogSurface id="confirm" title="Confirm link" open>Researcher authority is retained.</DialogSurface>
      </main>,
    );

    expect(UI_COMPONENT_CONTRACT_VERSION).toBe("1.0.0");
    expect(markup).toContain("aria-describedby=\"query-description query-error\"");
    expect(markup).toContain("aria-invalid=\"true\"");
    expect(markup).toContain("role=\"alert\"");
    expect(markup).toContain("data-evidence-state=\"verified\"");
    expect(markup).toContain("<caption>Evidence states</caption>");
    expect(markup).toContain("aria-labelledby=\"confirm-title\"");
  });

  it("fails closed for unsupported tones and malformed structural contracts", () => {
    expect(() => renderToStaticMarkup(<StatusBadge tone={"invented" as SemanticTone}>Invalid</StatusBadge>)).toThrow(
      "unsupported semantic tone",
    );
    expect(() => renderToStaticMarkup(<Field id="" label="Search" />)).toThrow("field id and label");
    expect(() =>
      renderToStaticMarkup(
        <DataTable
          caption="Duplicate"
          columns={[{ id: "state", label: "State" }, { id: "state", label: "Duplicate" }]}
          rows={[]}
          rowKey={() => "unused"}
        />,
      ),
    ).toThrow("caption and unique columns");
  });
});
