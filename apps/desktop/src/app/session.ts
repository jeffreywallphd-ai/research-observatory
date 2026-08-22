export type ProjectSessionState =
  | "no-project"
  | "opening"
  | "ready"
  | "read-only"
  | "incompatible"
  | "recovery-required"
  | "locked"
  | "closing";

const TRANSITIONS: Readonly<Record<ProjectSessionState, readonly ProjectSessionState[]>> = {
  "no-project": ["opening", "locked"],
  opening: ["ready", "read-only", "incompatible", "recovery-required", "no-project", "locked"],
  ready: ["closing", "recovery-required", "locked"],
  "read-only": ["closing", "recovery-required", "locked"],
  incompatible: ["closing", "locked"],
  "recovery-required": ["closing", "opening", "locked"],
  locked: ["no-project"],
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
