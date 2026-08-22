import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react";

import {
  CoreApiClientError,
  createCoreApiClient,
  type CacheClearPreview,
  type CacheClearResult,
  type DocumentRetentionPolicy,
  type PrivacyNetworkPolicy,
  type PrivacyPolicyProjection,
  type ProjectProjection,
  type TelemetryMode,
  type CoreApiTransport,
} from "@research-observatory/contracts/core-api";
import { Button, Notification, Panel, StatusBadge, Typography } from "@research-observatory/ui-components";

import { packagedProjectTransport } from "./ProjectsWorkspace";

const EGRESS_CONSENT_TOKEN = "acknowledge-egress-preview-v1";

export interface ProjectSettingsWorkspaceProps {
  readonly project: ProjectProjection | null;
  readonly announce: (message: string) => void;
  readonly transport?: CoreApiTransport;
}

interface SafeFailure {
  readonly title: string;
  readonly message: string;
}

function safeFailure(error: unknown): SafeFailure {
  if (error instanceof CoreApiClientError) {
    return {
      title: `${error.problem.title} (${error.problem.code})`,
      message: `${error.problem.detail} ${error.problem.remediation}`,
    };
  }
  return {
    title: "RO-CORE-PRIVACY-ACTION-FAILED",
    message: "The local privacy action did not complete. Existing restrictions remain unchanged.",
  };
}

export function projectSettingsAvailability(project: ProjectProjection | null): {
  readonly available: boolean;
  readonly message: string;
} {
  if (!project) {
    return { available: false, message: "Open a compatible local project before changing project settings." };
  }
  if (!project.open) {
    return { available: false, message: "The selected project is closed. Open it to load project settings." };
  }
  if (project.accessMode !== "read-write" || project.compatibilityState !== "compatible") {
    return {
      available: false,
      message: "This project is read-only. Keep it unchanged and use the displayed backup-first recovery path.",
    };
  }
  return { available: true, message: "Project settings are available for this exclusive local session." };
}

export function egressBoundary(network: PrivacyNetworkPolicy): {
  readonly sends: string;
  readonly excludes: string;
} {
  if (network === "offline") {
    return {
      sends: "Nothing. Offline is enforced as a denial at the object-access boundary.",
      excludes: "Documents, document metadata, prompts, citations, identifiers, and telemetry remain local.",
    };
  }
  if (network === "metadata-only") {
    return {
      sends: "This preference only records future eligibility for bounded metadata requests; it does not send data by itself.",
      excludes: "Document bytes and derived object content remain denied. A later implemented provider action still needs its own preview.",
    };
  }
  return {
    sends: "This preference only records future eligibility for approved providers; it does not send data by itself.",
    excludes: "Every later provider task remains blocked until an exact task preview and confirmation. Telemetry stays separate and off by default.",
  };
}

function deletionLimitations(policy: PrivacyPolicyProjection | null): readonly string[] {
  return policy?.deletionDisclosure.limitations ?? [
    "Filesystem deletion cannot prove physical media erasure.",
    "SSD wear levelling and device remapping can retain prior blocks.",
    "Journals, snapshots, backups, and hard links can retain copies.",
    "Only rebuildable project cache is in scope; canonical project data is excluded.",
  ];
}

export function ProjectSettingsWorkspace({
  project,
  announce,
  transport = packagedProjectTransport,
}: ProjectSettingsWorkspaceProps): ReactNode {
  const client = useMemo(() => createCoreApiClient(transport), [transport]);
  const availability = projectSettingsAvailability(project);
  const [policy, setPolicy] = useState<PrivacyPolicyProjection | null>(null);
  const [network, setNetwork] = useState<PrivacyNetworkPolicy>("offline");
  const [telemetry, setTelemetry] = useState<TelemetryMode>("off");
  const [logRetentionDays, setLogRetentionDays] = useState(14);
  const [documentRetention, setDocumentRetention] = useState<DocumentRetentionPolicy>("project-lifetime");
  const [cacheRetentionDays, setCacheRetentionDays] = useState(30);
  const [consent, setConsent] = useState(false);
  const [cachePreview, setCachePreview] = useState<CacheClearPreview | null>(null);
  const [cacheResult, setCacheResult] = useState<CacheClearResult | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [failure, setFailure] = useState<SafeFailure | null>(null);

  const applyPolicy = (next: PrivacyPolicyProjection): void => {
    setPolicy(next);
    setNetwork(next.networkPolicy);
    setTelemetry(next.telemetryMode);
    setLogRetentionDays(next.logRetentionDays);
    setDocumentRetention(next.documentRetention);
    setCacheRetentionDays(next.cacheRetentionDays);
    setConsent(next.egressConsentRecorded);
    setCachePreview(null);
    setCacheResult(null);
  };

  useEffect(() => {
    setPolicy(null);
    setCachePreview(null);
    setCacheResult(null);
    setFailure(null);
    if (!availability.available || !project) return;
    let cancelled = false;
    setBusy("load");
    void client.privacy({ root: project.root }).then((next) => {
      if (!cancelled) applyPolicy(next);
    }).catch((error: unknown) => {
      if (!cancelled) setFailure(safeFailure(error));
    }).finally(() => {
      if (!cancelled) setBusy(null);
    });
    return () => {
      cancelled = true;
    };
  }, [availability.available, client, project]);

  const boundary = egressBoundary(network);
  const needsConsent = network !== "offline";

  const save = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    if (!project || !policy || !availability.available || (needsConsent && !consent)) return;
    setBusy("save");
    setFailure(null);
    void client.updatePrivacy({
      root: project.root,
      expectedRevision: policy.revision,
      networkPolicy: network,
      remoteModelApproval: "preview-every-task",
      telemetryMode: telemetry,
      logRetentionDays,
      documentRetention,
      cacheRetentionDays,
      egressConsentToken: needsConsent ? EGRESS_CONSENT_TOKEN : null,
    }).then((next) => {
      applyPolicy(next);
      announce("Project privacy and retention settings saved locally.");
    }).catch((error: unknown) => {
      const safe = safeFailure(error);
      setFailure(safe);
      announce(`Project settings were not saved. ${safe.title}`);
    }).finally(() => setBusy(null));
  };

  const previewCache = (): void => {
    if (!project || !availability.available) return;
    setBusy("preview");
    setFailure(null);
    setCacheResult(null);
    void client.previewCache({ root: project.root }).then((preview) => {
      setCachePreview(preview);
      announce("Cache cleanup preview ready. Review the deletion limitations before confirming.");
    }).catch((error: unknown) => {
      setFailure(safeFailure(error));
    }).finally(() => setBusy(null));
  };

  const clearCache = (): void => {
    if (!project || !cachePreview || !availability.available) return;
    setBusy("clear");
    setFailure(null);
    void client.clearCache({
      root: project.root,
      previewToken: cachePreview.previewToken,
      confirmation: cachePreview.confirmation,
    }).then((result) => {
      setCacheResult(result);
      setCachePreview(null);
      announce(result.cleanupPending
        ? "Cache was logically cleared; best-effort staging cleanup remains pending."
        : "Rebuildable project cache cleared.");
    }).catch((error: unknown) => {
      const safe = safeFailure(error);
      setFailure(safe);
      announce(`Cache was not cleared. ${safe.title}`);
    }).finally(() => setBusy(null));
  };

  return (
    <section className="project-settings-workspace" aria-labelledby="project-settings-title" data-project-settings-workspace>
      <div className="page-header">
        <Typography id="project-settings-title" as="h1" variant="page-title">Project settings</Typography>
        <Typography className="page-subtitle">
          Privacy, rights and egress preferences are project-scoped. Defaults are offline with usage telemetry off.
        </Typography>
      </div>

      {!availability.available ? (
        <Notification tone="warning" title="Project settings unavailable">{availability.message}</Notification>
      ) : null}
      {failure ? <Notification tone="danger" title={failure.title}>{failure.message}</Notification> : null}
      {availability.available && !policy ? <p role="status">{busy === "load" ? "Loading local project settings…" : "Project settings are unavailable."}</p> : null}

      {availability.available && policy ? (
        <>
          <form className="privacy-settings-form" onSubmit={save}>
            <Panel title="Privacy, rights & egress">
              <div className="settings-field-grid">
                <label htmlFor="privacy-network-policy">Network policy</label>
                <select
                  id="privacy-network-policy"
                  value={network}
                  onChange={(event) => {
                    const next = event.currentTarget.value as PrivacyNetworkPolicy;
                    setNetwork(next);
                    setConsent(next === "offline");
                  }}
                >
                  <option value="offline">Offline · send nothing</option>
                  <option value="metadata-only">Metadata only · content denied</option>
                  <option value="approved-providers">Approved providers · preview every task</option>
                </select>

                <label htmlFor="remote-model-approval">Remote model approval</label>
                <select id="remote-model-approval" value="preview-every-task" disabled>
                  <option value="preview-every-task">Preview and confirm every task</option>
                </select>

                <label htmlFor="usage-telemetry">Usage telemetry</label>
                <select
                  id="usage-telemetry"
                  value={telemetry}
                  onChange={(event) => setTelemetry(event.currentTarget.value as TelemetryMode)}
                >
                  <option value="off">Off</option>
                  <option value="local-diagnostics-only">Local diagnostics only · never sent</option>
                </select>
              </div>

              <div className="egress-preview" aria-live="polite" data-egress-preview={network}>
                <Typography as="h3" variant="section-title">What this setting does</Typography>
                <p><strong>Will send:</strong> {boundary.sends}</p>
                <p><strong>Will not send:</strong> {boundary.excludes}</p>
              </div>

              {needsConsent ? (
                <label className="consent-boundary">
                  <input
                    type="checkbox"
                    checked={consent}
                    onChange={(event) => setConsent(event.currentTarget.checked)}
                  />
                  I reviewed the will-send/will-not-send boundary and understand this preference does not bypass task preview.
                </label>
              ) : (
                <StatusBadge tone="success">Offline denial enforced</StatusBadge>
              )}
            </Panel>

            <Panel title="Retention">
              <div className="settings-field-grid">
                <label htmlFor="log-retention">Local log retention</label>
                <select id="log-retention" value={logRetentionDays} onChange={(event) => setLogRetentionDays(Number(event.currentTarget.value))}>
                  <option value={7}>7 days</option>
                  <option value={14}>14 days</option>
                  <option value={30}>30 days</option>
                  <option value={90}>90 days</option>
                </select>

                <label htmlFor="document-retention">Document retention</label>
                <select id="document-retention" value={documentRetention} onChange={(event) => setDocumentRetention(event.currentTarget.value as DocumentRetentionPolicy)}>
                  <option value="project-lifetime">Keep for project lifetime</option>
                  <option value="review-after-90-days">Review after 90 days · no automatic deletion</option>
                  <option value="review-after-365-days">Review after 365 days · no automatic deletion</option>
                </select>

                <label htmlFor="cache-retention">Rebuildable cache retention</label>
                <select id="cache-retention" value={cacheRetentionDays} onChange={(event) => setCacheRetentionDays(Number(event.currentTarget.value))}>
                  <option value={7}>7 days</option>
                  <option value={14}>14 days</option>
                  <option value={30}>30 days</option>
                  <option value={90}>90 days</option>
                </select>
              </div>
              <p className="field-note">Retention selections are local project policy. Review intervals never delete documents automatically.</p>
            </Panel>

            <div className="settings-save-row">
              <span>Policy revision {policy.revision}</span>
              <Button tone="primary" type="submit" disabled={busy !== null || (needsConsent && !consent)}>
                {busy === "save" ? "Saving…" : "Save project settings"}
              </Button>
            </div>
          </form>

          <Panel title="Clean rebuildable project cache">
            <p>Preview the exact current cache inventory before clearing. Canonical project data is excluded.</p>
            <ul className="deletion-limitations">
              {deletionLimitations(policy).map((limitation) => <li key={limitation}>{limitation}</li>)}
            </ul>
            {!cachePreview ? (
              <Button disabled={busy !== null} onClick={previewCache}>{busy === "preview" ? "Preparing preview…" : "Preview cache cleanup"}</Button>
            ) : (
              <div className="cache-clear-confirmation" data-cache-clear-preview>
                <p><strong>In scope:</strong> {cachePreview.itemCount} item(s), {cachePreview.byteCount} byte(s) of rebuildable cache.</p>
                <p><strong>Guarantee:</strong> Logical removal only; physical media erasure is not guaranteed.</p>
                <Button tone="primary" disabled={busy !== null} onClick={clearCache}>
                  {busy === "clear" ? "Clearing…" : "Confirm clear rebuildable cache"}
                </Button>
                <Button disabled={busy !== null} onClick={() => setCachePreview(null)}>Cancel</Button>
              </div>
            )}
            {cacheResult ? (
              <Notification tone={cacheResult.cleanupPending ? "warning" : "success"} title="Cache cleanup result">
                {cacheResult.cleanupPending
                  ? "The active cache was logically removed, but best-effort staging cleanup remains pending. Physical erasure is not guaranteed."
                  : `Cleared ${cacheResult.itemCount} rebuildable item(s). Physical erasure is not guaranteed.`}
              </Notification>
            ) : null}
          </Panel>
        </>
      ) : null}
    </section>
  );
}
