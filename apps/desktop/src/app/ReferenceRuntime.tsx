import { useEffect, type ReactNode } from "react";

import { installApplicationFrame } from "./frame";
import { installProjectSelection } from "./projectSelection";
import type { DesktopRoute } from "./routes";

export interface ReferenceRuntimeProps {
  readonly route: DesktopRoute;
  readonly text: string;
}

export function ApplicationRuntime({ route, text }: ReferenceRuntimeProps): ReactNode {
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
