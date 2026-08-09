import { useEffect, type ReactNode } from "react";

import { installApplicationFrame } from "./frame";
import { installProjectSelection } from "./projectSelection";
import type { DesktopRoute } from "./routes";

export interface ApplicationRuntimeProps {
  readonly route: DesktopRoute;
  readonly text: string;
}

export function ApplicationRuntime({ route, text }: ApplicationRuntimeProps): ReactNode {
  useEffect(() => {
    const disposeFrame = installApplicationFrame(document, route);
    const disposeProjectSelection = installProjectSelection(document, route);
    return () => {
      disposeProjectSelection();
      disposeFrame();
    };
  }, [route]);
  return text;
}
