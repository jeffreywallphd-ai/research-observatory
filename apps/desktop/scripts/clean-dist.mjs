import { rm } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const dist = path.join(appRoot, "dist");
if (path.dirname(dist) !== appRoot || path.basename(dist) !== "dist") {
  throw new Error("refusing to clean a noncanonical desktop output path");
}
await rm(dist, { recursive: true, force: true });
