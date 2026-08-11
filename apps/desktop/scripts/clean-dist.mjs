import { rm } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const outputs = ["dist", "product-dist"];
for (const name of outputs) {
  const output = path.join(appRoot, name);
  if (path.dirname(output) !== appRoot || path.basename(output) !== name) {
    throw new Error("refusing to clean a noncanonical desktop output path");
  }
  await rm(output, { recursive: true, force: true });
}
