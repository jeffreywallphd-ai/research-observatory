import { useEffect, type ReactNode } from "react";

import { installApplicationFrame } from "./frame";
import type { DesktopRoute } from "./routes";

export interface ApplicationRuntimeProps {
  readonly route: DesktopRoute;
  readonly text: string;
}

export function ApplicationRuntime({ route, text }: ApplicationRuntimeProps): ReactNode {
  useEffect(() => installApplicationFrame(document, route), [route]);
  return text;
}
