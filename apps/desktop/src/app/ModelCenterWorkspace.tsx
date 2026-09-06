import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  CoreApiClientError, createCoreApiClient, decodeModelCatalogProjection,
  type CoreApiTransport, type ModelCatalogEntry, type ModelCatalogProjection,
  type ModelCatalogReadRequest, type ProjectProjection,
  type PrivacyPolicyProjection,
} from "@research-observatory/contracts/core-api";
import { Button, Notification, Panel, StatusBadge, Typography } from "@research-observatory/ui-components";

import { packagedProjectTransport } from "./ProjectsWorkspace";

interface ModelCenterProps {
  readonly project: ProjectProjection | null;
  readonly announce: (message: string) => void;
  readonly transport?: CoreApiTransport;
  readonly initialProjection?: ModelCatalogProjection;
  readonly onOpenSettings?: () => void;
}

export function modelCenterAvailability(project: ProjectProjection | null): { readonly readable: boolean; readonly writable: boolean } {
  return {
    readable: !!project?.open && project.accessMode !== "closed",
    writable: !!project?.open && project.accessMode === "read-write" && project.compatibilityState === "compatible",
  };
}

export function modelCenterResultMatches(project: ProjectProjection | null, requestedRoot: string, result: ModelCatalogProjection): boolean {
  return modelCenterAvailability(project).readable && project?.root === requestedRoot && project.projectId === result.projectId;
}

function failureMessage(error: unknown): string {
  return error instanceof CoreApiClientError
    ? `${error.problem.title} (${error.problem.code}). ${error.problem.detail} ${error.problem.remediation}`
    : "Model inventory could not be verified. Reload to check its current version. No model was executed.";
}

function ModelCard({ entry }: { readonly entry: ModelCatalogEntry }): ReactNode {
  const model = entry.manifest;
  return <Panel title={`${model.identity.modelId} · ${model.identity.modelVersion}`}>
    <div className="ro-cluster">
      <StatusBadge tone={entry.availability === "ready" ? "info" : "neutral"}>Runtime {entry.availability}</StatusBadge>
      <StatusBadge tone="neutral">{model.deployment}</StatusBadge>
      {model.retired ? <StatusBadge tone="warning">Retired</StatusBadge> : null}
    </div>
    <Typography>Provider: {model.identity.providerId} {model.identity.providerVersion} · Runtime: {model.identity.runtimeId} {model.identity.runtimeVersion}</Typography>
    <Typography>Tasks: {model.capabilities.join(", ")} · Modalities: {model.modalities.join(", ")}</Typography>
    <Typography>Features: {model.features.join(", ") || "None declared"} · Citation support: {model.supportsCitations ? "Declared" : "Not declared"}</Typography>
    <Typography>Context: {model.contextTokens.toLocaleString()} tokens · Maximum output: {model.maxOutputTokens.toLocaleString()} tokens</Typography>
    <Typography>Hardware: {model.minimumMemoryMiB.toLocaleString()} MiB minimum memory; {model.accelerator === "gpu" ? "GPU required" : "no accelerator required"}. Platforms: {model.platforms.join(", ")}</Typography>
    <Typography>License: {model.licenseId} · Declared data classes: {model.allowedDataClasses.join(", ") || "None allowed"}</Typography>
    <Typography>Quality tier: {model.qualityTier} · Verified task qualifications: {entry.qualifiedTaskKinds.join(", ") || "Not currently verified"}</Typography>
    <Typography>Evaluation reference: {model.identity.evaluationId === null ? "Not reported" : `${model.identity.evaluationId} ${model.identity.evaluationVersion}`}</Typography>
    <Typography>Manifest version {model.revision} · Declared availability: {model.declaredAvailability}</Typography>
    <Typography variant="compact">Checks: {entry.reasonCodes.map((code) => code.replaceAll("-", " ")).join("; ")}. Ready does not mean permission to run a task.</Typography>
  </Panel>;
}

export function ModelCenterWorkspace({
  project, announce, transport = packagedProjectTransport, initialProjection, onOpenSettings,
}: ModelCenterProps): ReactNode {
  const client = useMemo(() => createCoreApiClient(transport), [transport]);
  const key = project ? `${project.projectId}\u0000${project.root}` : "";
  const availability = modelCenterAvailability(project);
  const activeRef = useRef({ project, key });
  activeRef.current = { project, key };
  const requestRef = useRef(0);
  const initial = initialProjection ? decodeModelCatalogProjection(initialProjection) : null;
  const [stored, setStored] = useState<{ readonly key: string; readonly value: ModelCatalogProjection } | null>(
    initial && project && modelCenterResultMatches(project, project.root, initial) ? { key, value: initial } : null,
  );
  const [loading, setLoading] = useState(initial === null);
  const [failure, setFailure] = useState<string | null>(null);
  const [policy, setPolicy] = useState<{ readonly key: string; readonly value: PrivacyPolicyProjection } | null>(null);
  const value = stored?.key === key && availability.readable ? stored.value : null;

  const load = useCallback(async (overrides: Partial<Omit<ModelCatalogReadRequest, "root">> = {}, refresh = false): Promise<void> => {
    const selected = activeRef.current.project;
    const requestKey = activeRef.current.key;
    if (!selected || !modelCenterAvailability(selected).readable) return;
    const generation = ++requestRef.current;
    setLoading(true); setFailure(null);
    try {
      let result: ModelCatalogProjection;
      if (refresh) {
        if (!modelCenterAvailability(selected).writable || stored?.key !== requestKey) return;
        const bytes = crypto.getRandomValues(new Uint8Array(16));
        const id = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
        result = await client.refreshModelCatalog({ root: selected.root, expectedRevision: stored.value.latestRevision }, id);
      } else {
        result = await client.modelCatalog({ root: selected.root, revision: null, afterManifestId: null, beforeHistoryRevision: null, ...overrides });
      }
      const currentPolicy = await client.privacy({ root: selected.root }).catch(() => null);
      if (generation !== requestRef.current || activeRef.current.key !== requestKey) return;
      if (!modelCenterResultMatches(activeRef.current.project, selected.root, result)) throw new Error("model-project-mismatch");
      setStored({ key: requestKey, value: result });
      setPolicy(currentPolicy?.projectId === selected.projectId ? { key: requestKey, value: currentPolicy } : null);
      announce(`Model inventory version ${result.revision} loaded. ${result.modelCount} recorded models. No model was executed.`);
    } catch (error) {
      if (generation !== requestRef.current || activeRef.current.key !== requestKey) return;
      setFailure(failureMessage(error));
      setStored(null);
      setPolicy(null);
      announce("Model inventory is unavailable. Reload to check its current version.");
    } finally {
      if (generation === requestRef.current && activeRef.current.key === requestKey) setLoading(false);
    }
  }, [announce, client, stored]);

  // Project/session changes invalidate late responses before they can reach the
  // view. The effect intentionally follows identity, not the loaded revision.
  const loaderRef = useRef(load);
  loaderRef.current = load;
  useEffect(() => {
    requestRef.current += 1;
    setFailure(null);
    if (availability.readable) void loaderRef.current();
    else { setStored(null); setPolicy(null); setLoading(false); }
    return () => { requestRef.current += 1; };
  }, [key, availability.readable]);

  return <section className="ro-page-region ro-wrap-anywhere" data-model-center-workspace aria-labelledby="model-center-title" aria-busy={loading && availability.readable}>
    <div className="page-header">
      <Typography id="model-center-title" as="h1" variant="page-title">Model &amp; Privacy Center</Typography>
      <Typography className="page-subtitle">Inspect local model inventory, exact versions and capability limits without running a model.</Typography>
    </div>
    <Notification title="Capability matching does not grant permission" tone="info">
      No model is executed here. Each future task must pass fresh project privacy, source-rights, capability and evaluation checks. Recorded metadata is not an installation or permission grant.
    </Notification>
    {!availability.readable ? <Notification title="Open a local project" tone="neutral">
      Model inventory history belongs to a project. Open it from Local projects, then return to this supporting tool.
    </Notification> : <>
      {!availability.writable ? <Notification title="Read-only inspection" tone="neutral">Inventory history can be inspected; this session cannot record a refreshed version.</Notification> : null}
      <div className="ro-action-row" data-model-inventory-actions>
        <Button type="button" disabled={loading} onClick={() => void load()}>Reload inventory</Button>
        <Button type="button" disabled={loading || !availability.writable || !value || value.inventoryState !== "available"}
          onClick={() => void load({}, true)}>Refresh recorded inventory</Button>
      </div>
      {failure ? <Notification title="Inventory unavailable" tone="danger">{failure}</Notification> : null}
      {loading ? <Typography>Checking local inventory…</Typography> : null}
      {value ? <>
        <div data-model-provider-profiles className="ro-stack">
          <Typography as="h2" variant="section-title">Inventory version {value.revision}{value.revision !== value.latestRevision ? ` · Historical (latest ${value.latestRevision})` : ""}</Typography>
          {value.inventoryState === "not-configured" ? <Notification title="No model runtime adapter is configured" tone="neutral">
            Model installation and runtime execution are not available in this build. Existing catalog records remain inspectable; they cannot establish current readiness.
          </Notification> : value.inventoryState === "unavailable" ? <Notification title="Runtime observations unavailable" tone="warning">
            Saved records are shown without verified current availability. Reload to check again.
          </Notification> : null}
          {value.modelCount === 0 ? <Panel title="No models are recorded">
            <Typography>This is an empty catalog, not a failed model run. No model or evaluation result has been invented.</Typography>
          </Panel> : value.entries.map((entry) => <ModelCard key={entry.manifest.manifestId} entry={entry} />)}
          <div className="ro-action-row">
            {value.modelCount > 50 ? <Button type="button" disabled={loading} onClick={() => void load({ revision: value.revision })}>First model page</Button> : null}
            {value.nextManifestId ? <Button type="button" disabled={loading} onClick={() => void load({ revision: value.revision, afterManifestId: value.nextManifestId })}>Next model page</Button> : null}
          </div>
        </div>
        <div data-model-history><Panel title="Inventory history">
          <Typography>Refreshing records a new inventory snapshot. It does not overwrite an earlier version or install a model.</Typography>
          {value.history.length === 0 ? <Typography>No inventory changes have been recorded.</Typography> : value.history.map((summary) => (
            <div className="ro-split-row" key={summary.revision}>
              <Typography>Version {summary.revision} · {summary.modelCount} models · {summary.occurredAt}</Typography>
              <Button type="button" disabled={loading} onClick={() => void load({ revision: summary.revision })}>Inspect version {summary.revision}</Button>
            </div>
          ))}
          {value.nextHistoryRevision ? <Button type="button" disabled={loading} onClick={() => void load({ revision: value.revision || null, beforeHistoryRevision: value.nextHistoryRevision })}>Older inventory versions</Button> : null}
        </Panel></div>
      </> : null}
    </>}
    <div data-model-routing-policy><Panel title="Task routing and evaluation">
      <Typography>Capabilities, context, hardware, exact model pins and source permissions determine eligibility. Availability alone never selects a route.</Typography>
      <Typography>Live execution, model installation, evaluation runs, fallback and provider setup are not available from this page.</Typography>
      <Typography>University and hosted model pools are deferred to later delivery waves.</Typography>
    </Panel></div>
    <div data-model-egress-budget><Panel title="Privacy, egress and budgets">
      <Typography>No provider request or charge is created by inspecting this catalog. Remote execution and task-specific egress previews are unavailable in this build.</Typography>
      <Typography>Project settings records the current local privacy preference. It does not authorize a model request.</Typography>
      {policy?.key === key && availability.readable ? <Typography>
        Current network policy: {policy.value.networkPolicy.replaceAll("-", " ")} · Policy version {policy.value.revision}. Task-specific egress approval is still required.
      </Typography> : <Typography>Current network policy is not loaded here. No permission is inferred; inspect Project settings.</Typography>}
      {onOpenSettings ? <Button type="button" onClick={onOpenSettings}>Open Project settings</Button> : null}
    </Panel></div>
  </section>;
}
