import { readFile, readdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const roots = [path.join(appRoot, "src"), path.join(appRoot, "scripts")];
const sourceExtensions = new Set([".ts", ".tsx", ".js", ".mjs"]);
const errors = [];

async function walk(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const candidate = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      await walk(candidate);
    } else if (entry.isFile() && sourceExtensions.has(path.extname(entry.name))) {
      const text = await readFile(candidate, "utf8");
      const relative = path.relative(appRoot, candidate).replaceAll("\\", "/");
      if (relative === "scripts/lint.mjs") continue;
      if (/\bany\b/.test(text)) errors.push(`${relative}: explicit any is not allowed`);
      if (/https?:\/\//i.test(text)) errors.push(`${relative}: renderer/build source must remain offline`);
      if (/\b(TODO|FIXME)\b/.test(text)) errors.push(`${relative}: unresolved work marker`);
    }
  }
}

for (const root of roots) await walk(root);
if (errors.length) throw new Error(errors.join("\n"));
console.log("desktop lint: PASS");
