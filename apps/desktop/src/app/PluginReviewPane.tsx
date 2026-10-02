import { useEffect, useRef, useState, type ReactNode } from "react";
import type { ProjectProjection } from "@research-observatory/contracts/core-api";
import { Button, Notification, StatusBadge } from "@research-observatory/ui-components";
import { choosePluginPackage, type PluginNativeTransport, type ReviewedPluginPackage } from "./pluginIntake";
import { disablePlugin, discardPluginReview, enablePlugin, pluginGrantStatus, pluginTrustStatus, refreshPluginReview, removePluginPublisherTrust, trustPluginPublisher, type PluginGrantState, type PluginTrustState } from "./pluginActions";

interface Props {
  readonly project: ProjectProjection;
  readonly announce: (message: string) => void;
  readonly active: boolean;
  readonly initialPackage?: ReviewedPluginPackage;
  readonly nativeTransport?: PluginNativeTransport;
}

function destinationLabel(value: { readonly scheme: string; readonly host: string; readonly port: number; readonly pathTemplate: string }): string {
  return `${value.scheme}://${value.host}${value.port === 443 ? "" : `:${value.port}`}${value.pathTemplate}`;
}
function permissionChanges(selected: ReviewedPluginPackage, previous: PluginGrantState | null): string[] {
  if (!previous || previous.status !== "enabled") return [];
  const review = selected.review;
  const old = new Set([...previous.permissions, ...previous.destinations.map(destinationLabel)]);
  return [...review.permissions, ...review.destinations.map(destinationLabel)].filter((item) => !old.has(item));
}
export function samePackageIdentity(left: ReviewedPluginPackage, right: ReviewedPluginPackage): boolean {
  return left.review.pluginId === right.review.pluginId
    && left.review.packageSha256 === right.review.packageSha256
    && left.review.manifestSha256 === right.review.manifestSha256
    && left.review.signatureSha256 === right.review.signatureSha256
    && left.review.publisherKeyId === right.review.publisherKeyId;
}
export function grantMatchesPackage(grant: PluginGrantState | null, selected: ReviewedPluginPackage): boolean {
  return selected.review.grantStatus === "enabled" && grant?.status === "enabled" && grant.pluginId === selected.review.pluginId
    && grant.packageSha256 === selected.review.packageSha256
    && grant.manifestSha256 === selected.review.manifestSha256;
}
function enableReason(selected: ReviewedPluginPackage, trust: PluginTrustState | null, grant: PluginGrantState | null, consent: boolean): string {
  const review = selected.review;
  if (Date.parse(selected.expiresAt) <= Date.now()) return "This package review expired. Choose the package again.";
  if (review.trustStatus === "invalid") return "The package signature or files do not verify. Quarantine this package and obtain a valid publisher release; there is no bypass.";
  if (review.trustStatus === "revoked") return "The publisher key was removed locally. This package cannot run.";
  if (review.runtimeStatus !== "ready") return "The signed isolated worker is not installed and verified. Enabling is unavailable.";
  if (review.trustStatus !== "active" || trust?.status !== "active") return "Trust the publisher's independently supplied key before enabling this package.";
  if (!grant) return "Current project permission could not be verified.";
  if (!consent) return "Explicitly confirm this exact package digest and the displayed project permissions.";
  return "Enable this verified package for this project only; current rights and privacy policy still govern each request.";
}

export function PluginReviewPane({ project, announce, active, initialPackage, nativeTransport }: Props): ReactNode {
  const [selected, setSelected] = useState<ReviewedPluginPackage | null>(initialPackage ?? null);
  const [trust, setTrust] = useState<PluginTrustState | null>(null);
  const [grant, setGrant] = useState<PluginGrantState | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [consent, setConsent] = useState(false);
  const [trustRemovalAcknowledged, setTrustRemovalAcknowledged] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const live = useRef(true);
  const generation = useRef(0);
  const pending = useRef<AbortController | null>(null);
  const chooseButton = useRef<HTMLButtonElement>(null);
  const reviewHeading = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    live.current = active;
    if (!active) {
      generation.current++; pending.current?.abort(); pending.current = null;
      setSelected(null); setTrust(null); setGrant(null); setConsent(false); setTrustRemovalAcknowledged(false);
    }
    return () => { live.current = false; generation.current++; pending.current?.abort(); };
  }, [active]);

  async function refresh(current: ReviewedPluginPackage, revision: number): Promise<{ review: ReviewedPluginPackage; trust: PluginTrustState; grant: PluginGrantState } | null> {
    const address = { root: project.root, projectId: project.projectId };
    const [fresh, currentTrust, currentGrant] = await Promise.all([
      refreshPluginReview(address, current.packageToken, nativeTransport),
      pluginTrustStatus(address, current.review.publisherKeyId, nativeTransport),
      pluginGrantStatus(address, current.review.pluginId, nativeTransport),
    ]);
    if (!live.current || revision !== generation.current) return null;
    if (!fresh || !currentTrust || !currentGrant) {
      setFailure("The current package, publisher trust or project permission could not be verified. Refresh or choose the package again; no action was retried.");
      setTrust(null); setGrant(null);
      return null;
    }
    if (!samePackageIdentity(fresh, current)
      || currentTrust.publisherKeyId !== current.review.publisherKeyId || currentGrant.pluginId !== current.review.pluginId) {
      setFailure("Package identity changed during review. Choose the package again.");
      setTrust(null); setGrant(null);
      return null;
    }
    setSelected(fresh); setTrust(currentTrust); setGrant(currentGrant); setFailure(null);
    return { review: fresh, trust: currentTrust, grant: currentGrant };
  }

  async function choose(): Promise<void> {
    if (busy || !active) return;
    const owner = new AbortController(); pending.current = owner;
    const revision = ++generation.current;
    setBusy("choose"); setNotice(null); setFailure(null);
    try {
      const outcome = await choosePluginPackage({ root: project.root, projectId: project.projectId }, owner.signal, nativeTransport);
      if (!live.current || revision !== generation.current || owner.signal.aborted) return;
      if (outcome.status === "reviewed") {
        setSelected(outcome.package); setTrust(null); setGrant(null); setConsent(false); setTrustRemovalAcknowledged(false);
        announce("Connector package inspected locally. No code ran and no project permission was granted.");
        await refresh(outcome.package, revision);
        requestAnimationFrame(() => { if (live.current) reviewHeading.current?.focus(); });
      } else if (outcome.status === "cancelled") {
        announce("Connector selection cancelled. Prior configuration is unchanged.");
      } else setFailure("The package could not be inspected through the native local boundary. No connector was enabled.");
    } finally {
      if (pending.current === owner) pending.current = null;
      if (live.current && revision === generation.current) setBusy(null);
    }
  }

  function cancelReview(): void {
    if (busy) return;
    generation.current++; pending.current?.abort(); pending.current = null;
    if (selected) void discardPluginReview({ root: project.root, projectId: project.projectId }, selected.packageToken, nativeTransport);
    setSelected(null); setTrust(null); setGrant(null); setConsent(false); setTrustRemovalAcknowledged(false); setFailure(null);
    setNotice("Review closed. Select a package to view its current publisher trust and project permission.");
    announce("Connector review closed. Select a package to view its current publisher trust and project permission.");
    requestAnimationFrame(() => { if (live.current) chooseButton.current?.focus(); });
  }

  async function act(kind: "trust" | "enable" | "disable" | "remove-trust" | "refresh"): Promise<void> {
    if (!selected || busy || !active) return;
    const revision = ++generation.current;
    const current = selected;
    const address = { root: project.root, projectId: project.projectId };
    const owner = new AbortController(); pending.current = owner;
    setBusy(kind); setFailure(null); setNotice(null);
    try {
      const outcome = kind === "trust" ? await trustPluginPublisher(address, current.review.publisherKeyId, owner.signal, nativeTransport)
        : kind === "enable" && trust && grant ? await enablePlugin(address, current, trust, grant, nativeTransport)
          : kind === "disable" && grant ? await disablePlugin(address, grant, nativeTransport)
            : kind === "remove-trust" && trust ? await removePluginPublisherTrust(address, trust, nativeTransport)
              : { status: "ok" as const, value: null };
      if (!live.current || revision !== generation.current) return;
      const state = await refresh(current, revision);
      if (!live.current || revision !== generation.current) return;
      if (kind === "refresh" && state) setNotice("Current package, local publisher trust and project permission were rechecked.");
      else if (outcome.status === "ok") {
        const verified = state && (kind === "trust" ? state.trust.status === "active"
          : kind === "enable" ? grantMatchesPackage(state.grant, state.review)
            : kind === "disable" ? state.grant.status === "disabled"
              : state.trust.status === "revoked");
        if (!verified) {
          setFailure("The action returned, but its current effect could not be verified. Review current status before trying again.");
          return;
        }
        const message = kind === "trust" ? "Publisher key trusted locally. This package is not yet enabled for the project."
          : kind === "enable" ? "Connector enabled for this project. Each request still needs current policy checks."
            : kind === "disable" ? "Connector disabled for this project. New requests stop, and in-flight results cannot publish after disabling. Imported evidence remains."
              : "Local publisher trust removed. Dependent packages can no longer run; imported evidence remains.";
        setNotice(message); announce(message);
        if (kind === "enable") setConsent(false);
        if (kind === "remove-trust") setTrustRemovalAcknowledged(false);
      } else if (outcome.status === "cancelled") announce("Connector action was cancelled before submission. Review current status before trying again.");
      else setFailure(state
        ? "The action result could not be confirmed. Current status was refreshed; no mutation was retried."
        : "The action result and current status could not be confirmed. Refresh status before trying again; no mutation was retried.");
    } finally {
      if (pending.current === owner) pending.current = null;
      if (live.current && revision === generation.current) setBusy(null);
    }
  }

  const changes = selected ? permissionChanges(selected, grant) : [];
  const reason = selected ? enableReason(selected, trust, grant, consent) : "Choose a connector package to review.";
  const enableAvailable = !!selected && reason.startsWith("Enable this verified package") && !busy && active;
  const sameGrant = !!selected && grantMatchesPackage(grant, selected);
  return <section className="ro-panel ro-stack" id="connector-review" aria-labelledby="connector-review-title" onKeyDown={(event) => { if (event.key === "Escape" && selected && !busy) { event.stopPropagation(); cancelReview(); } }} data-plugin-review>
    <h2 className="ro-typography ro-typography--section-title" id="connector-review-title" ref={reviewHeading} tabIndex={-1}>Review connector access</h2>
    <p>Selecting a local package inspects its declared identity and permissions. It does not run code, test a connection or retrieve research data.</p>
    <div className="ro-action-row"><Button ref={chooseButton} disabled={!!busy || !active} onClick={() => void choose()}>Choose connector package…</Button>
      {selected ? <><Button disabled={!!busy || !active} onClick={() => void act("refresh")}>Refresh review</Button><Button disabled={!!busy} onClick={cancelReview}>Cancel review</Button></> : null}</div>
    {busy ? <p role="status">{busy === "choose" ? "Inspecting the selected local package…" : "Checking current connector authority…"}</p> : null}
    {failure ? <Notification tone="warning" title="Connector review needs attention">{failure}</Notification> : null}
    {notice ? <Notification tone="info" title="Connector review">{notice}</Notification> : null}
    {!selected ? <p>No package selected. Select one to inspect its current publisher trust and project permission.</p> : <>
      <StatusBadge tone={selected.review.trustStatus === "invalid" || selected.review.trustStatus === "revoked" ? "danger" : selected.review.grantStatus === "enabled" ? "success" : "warning"}>{selected.review.trustStatus === "invalid" ? "Quarantined · signature invalid" : selected.review.trustStatus === "revoked" ? "Publisher trust removed" : selected.review.grantStatus === "enabled" ? "Project permission recorded" : selected.review.grantStatus === "renewal-required" ? "Project permission needs renewal" : "Not enabled"}</StatusBadge>
      <dl className="ro-key-value"><dt>Package</dt><dd>{selected.review.sourceDisplayName} · version {selected.review.pluginVersion}</dd>
        <dt>Package digest</dt><dd className="ro-wrap-anywhere"><code>{selected.review.packageSha256}</code></dd>
        <dt>Manifest digest</dt><dd className="ro-wrap-anywhere"><code>{selected.review.manifestSha256}</code></dd>
        <dt>Publisher</dt><dd>{selected.review.publisherKeyId} · {selected.review.trustStatus === "active" ? "trusted key and package signature verified" : selected.review.trustStatus === "invalid" ? "signature or file verification failed" : "publisher signature not yet verified against local trust"}</dd>
        <dt>Local trust scope</dt><dd>This Windows account, across projects; it does not grant this project access.</dd>
        <dt>Credential state</dt><dd>{selected.review.credentialScopes.length ? `Broker-scoped credential requested: ${selected.review.credentialScopes.join(", ")}. Availability is not verified; secret values are never shown.` : "No credential scope requested."}</dd>
        <dt>Operations</dt><dd>{selected.review.operations.join(", ")}</dd>
        <dt>Destinations</dt><dd>{selected.review.destinations.length ? <ul>{selected.review.destinations.map((destination) => <li key={destinationLabel(destination)} className="ro-wrap-anywhere"><code>{destinationLabel(destination)}</code></li>)}</ul> : "None declared"}</dd>
        <dt>Data sent</dt><dd>{selected.review.dataClasses.join(", ")}</dd>
        <dt>Worker</dt><dd>{selected.review.runtimeStatus === "ready" ? "Signed isolated runtime available" : "Signed isolated runtime unavailable"}</dd>
      </dl>
      <div className="ro-grid ro-grid--two">
        <div><h3 className="ro-typography ro-typography--card-title">1. Local publisher trust</h3><p>Trust identifies this publisher's verified packages on this computer. It does not enable a connector or override project rights.</p>
          {trust?.publicKeySha256 ? <p className="ro-wrap-anywhere">Trusted key: <code>{trust.publicKeySha256}</code></p> : null}
          <div className="ro-action-row"><Button disabled={!!busy || !active || selected.review.trustStatus === "invalid" || trust?.status === "active"} onClick={() => void act("trust")}>Review publisher trust…</Button></div>
          {trust?.status === "active" ? <><label className="ro-cluster"><input type="checkbox" checked={trustRemovalAcknowledged} disabled={!!busy} onChange={(event) => setTrustRemovalAcknowledged(event.currentTarget.checked)} />I understand removing local trust affects dependent packages in every project.</label>
            <Button tone="danger" disabled={!!busy || !trustRemovalAcknowledged} onClick={() => void act("remove-trust")}>Remove local publisher trust</Button></> : null}
        </div>
        <div><h3 className="ro-typography ro-typography--card-title">2. Project permission</h3><p>Enabling applies only to this project and this exact package digest. It remains subject to current rights and privacy policy.</p>
          {grant?.status === "enabled" ? <p>Current project package: <code className="ro-wrap-anywhere">{grant.packageSha256}</code></p> : null}
          {changes.length ? <p>Newly requested access: {changes.join(", ")}. Renewed consent is required.</p> : null}
          {grant?.status === "enabled" && !sameGrant ? <p>The existing grant does not authorize this package under current publisher trust; review and consent are required again.</p> : null}
          <label className="ro-cluster"><input type="checkbox" checked={consent} disabled={!!busy || !active} onChange={(event) => setConsent(event.currentTarget.checked)} />I consent to this exact package and its displayed project operations, destinations and data classes.</label>
          <div className="ro-action-row"><Button tone="primary" disabled={!enableAvailable || sameGrant} aria-describedby="connector-enable-help" onClick={() => void act("enable")}>Enable for this project</Button>
            {grant?.status === "enabled" ? <Button tone="danger" disabled={!!busy || !active} onClick={() => void act("disable")}>Disable in this project</Button> : null}</div>
          <p className="field-note" id="connector-enable-help">{sameGrant ? "This exact package already has a recorded project grant." : reason}</p>
        </div>
      </div>
      {selected.review.trustStatus === "invalid" || selected.review.trustStatus === "revoked" ? <Notification tone="warning" title="Connector blocked">The current package cannot be enabled. Obtain a correctly signed package or review the publisher's independently supplied key. There is no bypass.</Notification> : null}
      <p className="field-note">Connection testing is a separate explicit network action. Import history and provenance remain after disabling or quarantine.</p>
    </>}
  </section>;
}
