import type { ReactNode } from "react";

import type { DesktopRoute } from "./routes";

export interface ApplicationRuntimeProps {
  readonly route: DesktopRoute;
  readonly text: string;
}

export function ApplicationRuntime({ route, text }: ApplicationRuntimeProps): ReactNode {
  void route;
  return text;
}
