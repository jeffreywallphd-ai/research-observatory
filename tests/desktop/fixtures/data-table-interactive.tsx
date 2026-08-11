import { createRoot } from "react-dom/client";

import { DataTable } from "../../../packages/ui-components/src/index";

const rows = Object.freeze(Array.from({ length: 10_000 }, (_value, index) => Object.freeze({
  id: `record-${index}`,
  title: `Research record ${index}`,
})));

const root = document.getElementById("root");
if (!root) throw new Error("interactive DataTable fixture requires #root");

createRoot(root).render(
  <DataTable
    caption="10,000-row interactive inventory"
    columns={[
      { id: "id", label: "Identifier" },
      { id: "title", label: "Title" },
    ]}
    rows={rows}
    rowKey={(row) => String(row.id)}
    pageSize={50}
    compact
  />,
);

requestAnimationFrame(() => requestAnimationFrame(() => {
  document.body.dataset.tableHarnessReady = "true";
}));
