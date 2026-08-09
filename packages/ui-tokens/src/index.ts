export const DESIGN_TOKEN_CONTRACT_VERSION = "1.0.0" as const;
export const DESIGN_REFERENCE_ID = "RO-UI-ACADEMIC-MINIMAL-1.3" as const;

export const semanticTones = ["neutral", "info", "success", "warning", "danger", "violet"] as const;
export type SemanticTone = (typeof semanticTones)[number];

export const evidenceStates = [
  "observed",
  "extracted",
  "inferred",
  "verified",
  "disputed",
  "adjudicated",
  "stale",
] as const;
export type EvidenceState = (typeof evidenceStates)[number];

export const uncertaintyStates = ["unknown", "not-reported", "not-applicable", "ambiguous"] as const;
export type UncertaintyState = (typeof uncertaintyStates)[number];

export function isSemanticTone(value: string): value is SemanticTone {
  return semanticTones.some((tone) => tone === value);
}

