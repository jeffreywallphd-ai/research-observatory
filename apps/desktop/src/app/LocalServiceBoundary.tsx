import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

import { BoundaryStatePanel, type BoundaryState } from "@research-observatory/ui-components";

export const LOCAL_SERVICE_DIAGNOSTIC_REFERENCE = "RO-CAP01-SERVICE-NOT-PACKAGED" as const;

export interface LocalServiceProbeResult {
  readonly status: "unavailable";
  readonly diagnosticReference: typeof LOCAL_SERVICE_DIAGNOSTIC_REFERENCE;
}

// Adapter output crosses a runtime trust boundary. Keep it unknown until the
// exact allowlisted result has been decoded below.
export type LocalServiceProbe = (signal: AbortSignal) => Promise<unknown>;

export interface LocalServiceBoundaryProps {
  readonly announce: (message: string) => void;
  readonly probe?: LocalServiceProbe;
}

interface LocalServiceView {
  readonly state: BoundaryState;
  readonly title: string;
  readonly message: string;
  readonly diagnosticReference?: typeof LOCAL_SERVICE_DIAGNOSTIC_REFERENCE;
}

const UNAVAILABLE_VIEW: LocalServiceView = {
  state: "recovery-required",
  title: "Local analytical service unavailable",
  message: "This build does not yet package the CAP-01 local service. The desktop shell remains fully local and usable.",
  diagnosticReference: LOCAL_SERVICE_DIAGNOSTIC_REFERENCE,
};

const LOADING_VIEW: LocalServiceView = {
  state: "loading",
  title: "Checking local analytical service",
  message: "The check is local, bounded, and cancellable. Existing command input remains unchanged.",
};

export async function packagedLocalServiceProbe(signal: AbortSignal): Promise<LocalServiceProbeResult> {
  await Promise.resolve();
  if (signal.aborted) throw new DOMException("Local service check cancelled", "AbortError");
  return { status: "unavailable", diagnosticReference: LOCAL_SERVICE_DIAGNOSTIC_REFERENCE };
}

export function secretSafeServiceFailure(error: unknown): LocalServiceView {
  void error;
  return {
    state: "failed",
    title: "Local service check failed",
    message: "The check failed without changing local input. Retry or copy the opaque diagnostic reference.",
    diagnosticReference: LOCAL_SERVICE_DIAGNOSTIC_REFERENCE,
  };
}

export function localServiceViewFromProbeResult(result: unknown): LocalServiceView {
  try {
    if (result === null || typeof result !== "object" || Array.isArray(result)) {
      return secretSafeServiceFailure(result);
    }

    const keys = Reflect.ownKeys(result);
    if (
      keys.length === 2
      && keys.every((key) => key === "status" || key === "diagnosticReference")
      && Reflect.get(result, "status") === "unavailable"
      && Reflect.get(result, "diagnosticReference") === LOCAL_SERVICE_DIAGNOSTIC_REFERENCE
    ) {
      return UNAVAILABLE_VIEW;
    }
  } catch {
    // Proxies and hostile getters are untrusted adapter failures too.
  }

  return secretSafeServiceFailure(result);
}

export function LocalServiceBoundary({ announce, probe = packagedLocalServiceProbe }: LocalServiceBoundaryProps): ReactNode {
  const [view, setView] = useState<LocalServiceView>(UNAVAILABLE_VIEW);
  const activeProbe = useRef<AbortController | null>(null);

  useEffect(() => () => activeProbe.current?.abort(), []);

  const retry = useCallback(async () => {
    activeProbe.current?.abort();
    const controller = new AbortController();
    activeProbe.current = controller;
    setView(LOADING_VIEW);
    announce("Checking the packaged local service.");
    try {
      const result = await probe(controller.signal);
      if (controller.signal.aborted) return;
      const nextView = localServiceViewFromProbeResult(result);
      setView(nextView);
      announce(
        nextView.state === "recovery-required"
          ? "Local service check complete. The service is not packaged; local shell input was retained."
          : "Local service check failed. Local shell input was retained.",
      );
    } catch (error) {
      if (controller.signal.aborted) return;
      setView(secretSafeServiceFailure(error));
      announce("Local service check failed. Local shell input was retained.");
    } finally {
      if (activeProbe.current === controller) activeProbe.current = null;
    }
  }, [announce, probe]);

  const cancel = useCallback(() => {
    activeProbe.current?.abort();
    activeProbe.current = null;
    setView(UNAVAILABLE_VIEW);
    announce("Local service check cancelled. Local shell input was retained.");
  }, [announce]);

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

  return (
    <div data-local-service-boundary data-boundary-state={view.state}>
      <BoundaryStatePanel
        id="local-service-boundary"
        state={view.state}
        title={view.title}
        message={view.message}
        {...(view.state === "loading" ? { progress: { label: "Local readiness check", value: 50 } } : {})}
        {...(view.diagnosticReference ? { diagnosticReference: view.diagnosticReference } : {})}
        {...(view.state === "loading" ? { onCancel: cancel } : { onRetry: () => void retry() })}
        onContinueOffline={continueLocally}
        onCopyDiagnostic={(reference) => void copyDiagnostic(reference)}
      >
        <p>Application commands and local shell navigation remain available; no researcher data is discarded.</p>
      </BoundaryStatePanel>
    </div>
  );
}
