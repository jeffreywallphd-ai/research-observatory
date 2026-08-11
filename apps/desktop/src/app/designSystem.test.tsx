import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import {
  boundaryStates,
  BoundaryStatePanel,
  DataTable,
  DialogSurface,
  EvidenceStateBadge,
  Field,
  Notification,
  Panel,
  StatusBadge,
  Typography,
  UncertaintyState,
  UI_COMPONENT_CONTRACT_VERSION,
} from "@research-observatory/ui-components";
import type { SemanticTone } from "@research-observatory/ui-tokens";
import { evidenceStates, uncertaintyStates } from "@research-observatory/ui-tokens";

describe("Academic Minimal design system", () => {
  it("renders accessible component contracts and documented semantic variants", () => {
    const markup = renderToStaticMarkup(
      <main>
        <Typography as="h1" variant="page-title">Evidence workspace</Typography>
        <Field id="query" label="Search" description="Local sources" error="Query is required" />
        <StatusBadge tone="violet">Inferred</StatusBadge>
        <Notification tone="danger" title="Blocked">Evidence is insufficient.</Notification>
        <Panel tone="success" title="Verified evidence" evidenceState="verified">Checked.</Panel>
        {evidenceStates.map((state) => <EvidenceStateBadge key={state} state={state} />)}
        {uncertaintyStates.map((state) => <UncertaintyState key={state} state={state} />)}
        <DataTable
          caption="Evidence states"
          columns={[{ id: "state", label: "State" }]}
          rows={[{ state: "Observed" }]}
          rowKey={(row) => String(row.state)}
        />
        <DialogSurface id="confirm" title="Confirm link" open>Researcher authority is retained.</DialogSurface>
      </main>,
    );

    expect(UI_COMPONENT_CONTRACT_VERSION).toBe("1.1.0");
    expect(markup).toContain("aria-describedby=\"query-description query-error\"");
    expect(markup).toContain("aria-invalid=\"true\"");
    expect(markup).toContain("role=\"alert\"");
    expect(markup).toContain("data-evidence-state=\"verified\"");
    expect(markup).toContain("<caption>Evidence states</caption>");
    expect(markup).toContain("aria-labelledby=\"confirm-title\"");
    expect(markup).toContain("<h2 id=\"confirm-title\"");
    for (const state of evidenceStates) expect(markup).toContain(`data-evidence-state="${state}"`);
    for (const state of uncertaintyStates) expect(markup).toContain(`data-uncertainty-state="${state}"`);
  });

  it("renders every semantic operation boundary with visible non-color identity", () => {
    const markup = renderToStaticMarkup(
      <main>
        {boundaryStates.map((state) => (
          <BoundaryStatePanel
            key={state}
            state={state}
            title={`${state} title`}
            message={`${state} message`}
            {...(state === "loading" ? { progress: { label: "Local progress", value: 40 } } : {})}
            {...(state === "failed" ? { diagnosticReference: "RO-LOCAL-OPERATION-FAILED" } : {})}
          />
        ))}
      </main>,
    );

    for (const state of boundaryStates) expect(markup).toContain(`data-boundary-state="${state}"`);
    expect(markup).toContain("State: Partial results");
    expect(markup).toContain("Local progress: 40%");
    expect(markup).toContain("RO-LOCAL-OPERATION-FAILED");
  });

  it("maps injected service, network, and data boundaries to actionable retained states", () => {
    const markup = renderToStaticMarkup(
      <main>
        <BoundaryStatePanel
          state="failed"
          title="Service failed"
          message="The local request did not complete."
          diagnosticReference="RO-LOCAL-SERVICE-FAILED"
          onRetry={() => undefined}
        >
          <input name="retained-service-input" defaultValue="retained" />
        </BoundaryStatePanel>
        <BoundaryStatePanel
          state="offline"
          title="Network unavailable"
          message="Remote access is unavailable; local work remains available."
          onRetry={() => undefined}
          onContinueOffline={() => undefined}
        />
        <BoundaryStatePanel
          state="partial"
          title="Partial data"
          message="Missing records remain explicit."
        >
          <p>Two retained validated records</p>
        </BoundaryStatePanel>
        <BoundaryStatePanel
          state="loading"
          title="Loading"
          message="The operation can be cancelled."
          progress={{ label: "Validated", value: 25 }}
          onCancel={() => undefined}
        />
      </main>,
    );

    expect(markup).toContain("Retry");
    expect(markup).toContain("Continue locally");
    expect(markup).toContain("Cancel");
    expect(markup).toContain('value="retained"');
    expect(markup).toContain("Two retained validated records");
    expect(markup).not.toContain("stack");
  });

  it("fails closed for unsupported tones and malformed structural contracts", () => {
    expect(() => renderToStaticMarkup(<StatusBadge tone={"invented" as SemanticTone}>Invalid</StatusBadge>)).toThrow(
      "unsupported semantic tone",
    );
    expect(() => renderToStaticMarkup(<Field id="" label="Search" />)).toThrow("field id and label");
    expect(() => renderToStaticMarkup(<EvidenceStateBadge state={"invented" as never} />)).toThrow(
      "unsupported evidence state",
    );
    expect(() => renderToStaticMarkup(<UncertaintyState state={"invented" as never} />)).toThrow(
      "unsupported uncertainty state",
    );
    expect(() =>
      renderToStaticMarkup(
        <BoundaryStatePanel state={"invented" as never} title="Invalid" message="Invalid state" />,
      ),
    ).toThrow("unsupported boundary state");
    expect(() =>
      renderToStaticMarkup(
        <BoundaryStatePanel
          state="failed"
          title="Failed"
          message="Opaque only"
          diagnosticReference="Bearer-secret-value"
        />,
      ),
    ).toThrow("bounded Research Observatory identifier");
    expect(() =>
      renderToStaticMarkup(
        <BoundaryStatePanel
          state="loading"
          title="Loading"
          message="Invalid progress"
          progress={{ label: "Progress", value: Number.NaN }}
        />,
      ),
    ).toThrow("finite value");
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
