export type ProjectSessionState =
  | "no-project"
  | "opening"
  | "ready"
  | "read-only"
  | "incompatible"
  | "recovery-required"
  | "closing";

const TRANSITIONS: Readonly<Record<ProjectSessionState, readonly ProjectSessionState[]>> = {
  "no-project": ["opening"],
  opening: ["ready", "read-only", "incompatible", "recovery-required", "no-project"],
  ready: ["closing", "recovery-required"],
  "read-only": ["closing", "recovery-required"],
  incompatible: ["closing"],
  "recovery-required": ["closing", "opening"],
  closing: ["no-project", "recovery-required"],
};

export function transitionProjectSession(
  current: ProjectSessionState,
  next: ProjectSessionState,
): ProjectSessionState {
  if (!TRANSITIONS[current].includes(next)) {
    throw new Error(`invalid project session transition: ${current} -> ${next}`);
  }
  return next;
}
