import { invoke } from "@tauri-apps/api/core";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

import {
  BoundaryStatePanel,
  Panel,
  StatusBadge,
  type BoundaryState,
} from "@research-observatory/ui-components";

export const LOCAL_SERVICE_DIAGNOSTIC_REFERENCE = "RO-CORE-SUPERVISOR-UNAVAILABLE" as const;

const RUNTIME_STATES = [
  "starting",
  "ready",
  "crashed",
  "stopped",
  "incompatible",
  "recovery-required",
] as const;

type RuntimeState = (typeof RUNTIME_STATES)[number];

const SNAPSHOT_DIAGNOSTICS = new Set<string>([
  "RO-CORE-STARTING",
  "RO-CORE-STOPPED",
  "RO-CORE-CRASHED",
  "RO-CORE-STATUS-FAILED",
  "RO-CORE-SPAWN-FAILED",
  "RO-CORE-CONTAINMENT-FAILED",
  "RO-CORE-HANDSHAKE-MISSING",
  "RO-CORE-LOG-PIPE-FAILED",
  "RO-CORE-CONTROL-PIPE-FAILED",
  "RO-CORE-START-TIMEOUT",
  "RO-CORE-EARLY-EXIT",
  "RO-CORE-HANDSHAKE-INVALID",
  "RO-CORE-INCOMPATIBLE",
  "RO-CORE-RESTART-LIMIT",
  "RO-CORE-NOT-PACKAGED",
  "RO-CORE-INTEGRITY-FAILED",
  LOCAL_SERVICE_DIAGNOSTIC_REFERENCE,
] as const);

export interface LocalServiceProbeResult {
  readonly state: RuntimeState;
  readonly attempt: number;
  readonly retryAvailable: boolean;
  readonly diagnosticReference: string | null;
}

// Native command output crosses a runtime trust boundary. Keep it unknown until
// the exact allowlisted snapshot has been decoded below.
export type LocalServiceProbe = (signal: AbortSignal) => Promise<unknown>;

export interface LocalServiceBoundaryProps {
  readonly announce: (message: string) => void;
  readonly probe?: LocalServiceProbe;
  readonly statusProbe?: LocalServiceProbe;
  readonly stopProbe?: () => Promise<unknown>;
}

interface LocalServiceView {
  readonly state: BoundaryState | "ready";
  readonly runtimeState: RuntimeState;
  readonly title: string;
  readonly message: string;
  readonly retryAvailable: boolean;
  readonly diagnosticReference?: string | undefined;
}

const UNAVAILABLE_VIEW: LocalServiceView = {
  state: "recovery-required",
  runtimeState: "recovery-required",
  title: "Local analytical service unavailable",
  message: "The local service requires the supervised desktop host. Retry after the packaged runtime is available.",
  retryAvailable: true,
  diagnosticReference: LOCAL_SERVICE_DIAGNOSTIC_REFERENCE,
};

const LOADING_VIEW: LocalServiceView = {
  state: "loading",
  runtimeState: "starting",
  title: "Starting local analytical service",
  message: "Verifying the package, starting Core, and waiting for local readiness. Existing command input remains unchanged.",
  retryAvailable: false,
};

function hasTauriRuntime(): boolean {
  return typeof globalThis.window !== "undefined" && "__TAURI_INTERNALS__" in globalThis.window;
}

function isRuntimeState(value: string): value is RuntimeState {
  return (RUNTIME_STATES as readonly string[]).includes(value);
}

function abortError(): DOMException {
  return new DOMException("Local service check cancelled", "AbortError");
}

async function invokeRuntime(command: "core_runtime_start" | "core_runtime_status", signal: AbortSignal): Promise<unknown> {
  if (signal.aborted) throw abortError();
  if (!hasTauriRuntime()) {
    return {
      state: "recovery-required",
      attempt: 0,
      retryAvailable: true,
      diagnosticReference: LOCAL_SERVICE_DIAGNOSTIC_REFERENCE,
    } satisfies LocalServiceProbeResult;
  }
  return await new Promise((resolve, reject) => {
    const cancelled = (): void => reject(abortError());
    signal.addEventListener("abort", cancelled, { once: true });
    void invoke<unknown>(command).then(resolve, reject).finally(() => signal.removeEventListener("abort", cancelled));
  });
}

export async function packagedLocalServiceProbe(signal: AbortSignal): Promise<unknown> {
  return await invokeRuntime("core_runtime_start", signal);
}

export async function packagedLocalServiceStatusProbe(signal: AbortSignal): Promise<unknown> {
  return await invokeRuntime("core_runtime_status", signal);
}

export async function stopPackagedLocalService(): Promise<unknown> {
  if (!hasTauriRuntime()) return undefined;
  return await invoke<unknown>("core_runtime_stop");
}

export function decodeLocalServiceProbeResult(result: unknown): LocalServiceProbeResult | null {
  try {
    if (result === null || typeof result !== "object" || Array.isArray(result)) return null;
    const keys = Reflect.ownKeys(result);
    if (
      keys.length !== 4
      || !keys.every((key) => ["state", "attempt", "retryAvailable", "diagnosticReference"].includes(String(key)))
    ) return null;
    const state = Reflect.get(result, "state");
    const attempt = Reflect.get(result, "attempt");
    const retryAvailable = Reflect.get(result, "retryAvailable");
    const diagnosticReference = Reflect.get(result, "diagnosticReference");
    if (
      typeof state !== "string"
      || !isRuntimeState(state)
      || !Number.isInteger(attempt)
      || typeof attempt !== "number"
      || attempt < 0
      || attempt > 3
      || typeof retryAvailable !== "boolean"
      || (diagnosticReference !== null
        && (typeof diagnosticReference !== "string" || !SNAPSHOT_DIAGNOSTICS.has(diagnosticReference)))
      || (state === "ready" && diagnosticReference !== null)
    ) return null;
    return { state, attempt, retryAvailable, diagnosticReference };
  } catch {
    return null;
  }
}

export function secretSafeServiceFailure(error: unknown): LocalServiceView {
  void error;
  return {
    state: "failed",
    runtimeState: "crashed",
    title: "Local service check failed",
    message: "The check failed without changing local input. Retry or copy the opaque diagnostic reference.",
    retryAvailable: true,
    diagnosticReference: "RO-CORE-STATUS-FAILED",
  };
}

export function localServiceViewFromProbeResult(result: unknown): LocalServiceView {
  const snapshot = decodeLocalServiceProbeResult(result);
  if (!snapshot) return secretSafeServiceFailure(result);
  const diagnostic = snapshot.diagnosticReference ?? undefined;
  switch (snapshot.state) {
    case "ready":
      return {
        state: "ready",
        runtimeState: "ready",
        title: "Local analytical service",
        message: "Core is running locally and ready for implemented application capabilities.",
        retryAvailable: false,
      };
    case "starting":
      return { ...LOADING_VIEW, retryAvailable: snapshot.retryAvailable, diagnosticReference: diagnostic };
    case "stopped":
      return {
        state: "offline",
        runtimeState: snapshot.state,
        title: "Local analytical service stopped",
        message: "Core is stopped. Retry starts a new bounded local process without changing project input.",
        retryAvailable: snapshot.retryAvailable,
        diagnosticReference: diagnostic,
      };
    case "crashed":
      return {
        state: "failed",
        runtimeState: snapshot.state,
        title: "Local analytical service stopped unexpectedly",
        message: "Core exited unexpectedly. Retry uses the remaining bounded restart budget; project input remains unchanged.",
        retryAvailable: snapshot.retryAvailable,
        diagnosticReference: diagnostic,
      };
    case "incompatible":
      return {
        state: "recovery-required",
        runtimeState: snapshot.state,
        title: "Local analytical service is incompatible",
        message: "The desktop rejected the service handshake. Repair or reinstall the matching application package.",
        retryAvailable: snapshot.retryAvailable,
        diagnosticReference: diagnostic,
      };
    case "recovery-required":
      return {
        state: "recovery-required",
        runtimeState: snapshot.state,
        title: "Local analytical service needs recovery",
        message: snapshot.diagnosticReference === "RO-CORE-RESTART-LIMIT"
          ? "The bounded restart budget is exhausted. Quit and reopen the application after reviewing diagnostics."
          : "The packaged service is unavailable or failed integrity checks. Repair or reinstall the application package.",
        retryAvailable: snapshot.retryAvailable,
        diagnosticReference: diagnostic,
      };
  }
}

export function LocalServiceBoundary({
  announce,
  probe = packagedLocalServiceProbe,
  statusProbe = packagedLocalServiceStatusProbe,
  stopProbe = stopPackagedLocalService,
}: LocalServiceBoundaryProps): ReactNode {
  const [view, setView] = useState<LocalServiceView>(() => hasTauriRuntime() ? LOADING_VIEW : UNAVAILABLE_VIEW);
  const activeProbe = useRef<AbortController | null>(null);
  const lastAnnouncedState = useRef<RuntimeState>(view.runtimeState);

  const applyResult = useCallback((result: unknown, announceUnchanged = false): void => {
    const nextView = localServiceViewFromProbeResult(result);
    setView(nextView);
    if (announceUnchanged || lastAnnouncedState.current !== nextView.runtimeState) {
      lastAnnouncedState.current = nextView.runtimeState;
      announce(nextView.state === "ready"
        ? "Local analytical service ready."
        : `Local analytical service ${nextView.runtimeState}. Local shell input was retained.`);
    }
  }, [announce]);

  const retry = useCallback(async () => {
    activeProbe.current?.abort();
    const controller = new AbortController();
    activeProbe.current = controller;
    setView(LOADING_VIEW);
    announce("Starting the packaged local service.");
    try {
      const result = await probe(controller.signal);
      if (!controller.signal.aborted) applyResult(result, true);
    } catch (error) {
      if (!controller.signal.aborted) {
        setView(secretSafeServiceFailure(error));
        announce("Local service check failed. Local shell input was retained.");
      }
    } finally {
      if (activeProbe.current === controller) activeProbe.current = null;
    }
  }, [announce, applyResult, probe]);

  useEffect(() => {
    if (probe === packagedLocalServiceProbe && hasTauriRuntime()) void retry();
    return () => activeProbe.current?.abort();
  }, [probe, retry]);

  useEffect(() => {
    if (!hasTauriRuntime() || (view.runtimeState !== "starting" && view.runtimeState !== "ready")) return undefined;
    const timer = globalThis.window.setInterval(() => {
      if (activeProbe.current) return;
      const controller = new AbortController();
      activeProbe.current = controller;
      void statusProbe(controller.signal)
        .then((result) => {
          if (!controller.signal.aborted) applyResult(result);
        })
        .catch((error) => {
          if (!controller.signal.aborted) setView(secretSafeServiceFailure(error));
        })
        .finally(() => {
          if (activeProbe.current === controller) activeProbe.current = null;
        });
    }, 750);
    return () => globalThis.window.clearInterval(timer);
  }, [applyResult, statusProbe, view.runtimeState]);

  const cancel = useCallback(async () => {
    activeProbe.current?.abort();
    activeProbe.current = null;
    setView({ ...LOADING_VIEW, title: "Stopping local analytical service" });
    announce("Stopping the packaged local service.");
    try {
      const result = await stopProbe();
      applyResult(result, true);
    } catch (error) {
      setView(secretSafeServiceFailure(error));
      announce("Local service stop failed. Local shell input was retained.");
    }
  }, [announce, applyResult, stopProbe]);

  const continueLocally = useCallback(() => {
    announce("Continuing with the local desktop shell. No remote service was contacted.");
  }, [announce]);

  const copyDiagnostic = useCallback(async (reference: string) => {
    try {
      await navigator.clipboard.writeText(reference);
      announce("Diagnostic reference copied.");
    } catch {
      announce("Diagnostic copy is unavailable. The reference remains visible for manual copy.");
    }
  }, [announce]);

  if (view.state === "ready") {
    return (
      <div data-local-service-boundary data-boundary-state="ready">
        <Panel title={view.title} tone="success">
          <StatusBadge tone="success">Ready</StatusBadge>
          <p>{view.message}</p>
        </Panel>
      </div>
    );
  }

  return (
    <div data-local-service-boundary data-boundary-state={view.state}>
      <BoundaryStatePanel
        id="local-service-boundary"
        state={view.state}
        title={view.title}
        message={view.message}
        {...(view.state === "loading" ? { progress: { label: "Local readiness", value: 50 } } : {})}
        {...(view.diagnosticReference ? { diagnosticReference: view.diagnosticReference } : {})}
        {...(view.state === "loading"
          ? { onCancel: () => void cancel() }
          : view.retryAvailable
            ? { onRetry: () => void retry() }
            : {})}
        onContinueOffline={continueLocally}
        onCopyDiagnostic={(reference) => void copyDiagnostic(reference)}
      >
        <p>Application commands and local shell navigation remain available; no researcher data is discarded.</p>
      </BoundaryStatePanel>
    </div>
  );
}
