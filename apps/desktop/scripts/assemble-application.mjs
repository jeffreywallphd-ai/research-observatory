import { createHash } from "node:crypto";
import { readFile, readdir, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(appRoot, "..", "..");
const productRoot = path.join(appRoot, "product-dist");
const referenceRoot = path.join(repoRoot, "design", "ui-reference");
const excludedInputDirectories = new Set(["dist", "product-dist", "node_modules", "target"]);
const packageInputRoots = [
  path.join(repoRoot, "packages", "ui-components"),
  path.join(repoRoot, "packages", "ui-tokens"),
];
const expectedArtifacts = new Set(["assets/app.css", "assets/app.js", "assets/app.js.map", "index.html"]);

function sha256(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

async function filesBelow(root, excludedDirectories = new Set()) {
  const result = [];
  async function walk(directory) {
    const entries = await readdir(directory, { withFileTypes: true });
    entries.sort((left, right) => left.name.localeCompare(right.name, "en"));
    for (const entry of entries) {
      const candidate = path.join(directory, entry.name);
      if (entry.isSymbolicLink()) throw new Error(`redirected build input/output: ${candidate}`);
      if (entry.isDirectory()) {
        if (directory !== root || !excludedDirectories.has(entry.name)) await walk(candidate);
      } else if (entry.isFile()) {
        result.push(candidate);
      } else {
        throw new Error(`unsupported build input/output: ${candidate}`);
      }
    }
  }
  await walk(root);
  return result;
}

const referencePages = new Set(
  JSON.parse(await readFile(path.join(referenceRoot, "SITE_MANIFEST.json"), "utf8"))
    .pages.map((page) => page.file),
);
const artifacts = {};
for (const artifact of await filesBelow(productRoot)) {
  const relative = path.relative(productRoot, artifact).replaceAll("\\", "/");
  if (relative === "application-manifest.json") continue;
  if (!expectedArtifacts.has(relative)) throw new Error(`unexpected desktop product artifact: ${relative}`);
  if (relative !== "index.html" && referencePages.has(relative)) {
    throw new Error(`reference-only page entered the desktop product bundle: ${relative}`);
  }
  artifacts[relative] = sha256(await readFile(artifact));
}
if (Object.keys(artifacts).sort().join("\n") !== [...expectedArtifacts].sort().join("\n")) {
  throw new Error(`desktop product artifact inventory is incomplete: ${Object.keys(artifacts).sort().join(", ")}`);
}

const index = await readFile(path.join(productRoot, "index.html"), "utf8");
for (const forbidden of ["prototype-index.html", "style-guide.html", "data-workflow-select", "data-all-tools"]) {
  if (index.includes(forbidden)) throw new Error(`reference-only marker entered the desktop product HTML: ${forbidden}`);
}

const sourceFiles = {};
for (const source of await filesBelow(appRoot, excludedInputDirectories)) {
  const relative = path.relative(repoRoot, source).replaceAll("\\", "/");
  sourceFiles[relative] = sha256(await readFile(source));
}
for (const packageRoot of packageInputRoots) {
  for (const source of await filesBelow(packageRoot, excludedInputDirectories)) {
    const relative = path.relative(repoRoot, source).replaceAll("\\", "/");
    sourceFiles[relative] = sha256(await readFile(source));
  }
}
for (const relative of ["Cargo.toml", "Cargo.lock", "package.json", "pnpm-lock.yaml", "pnpm-workspace.yaml", "verification/extensions/desktop-ui.json"]) {
  sourceFiles[relative] = sha256(await readFile(path.join(repoRoot, relative)));
}

const manifest = {
  schemaVersion: "1.0",
  documentType: "desktop-product-build-manifest",
  buildRole: "tauri-frontend",
  implementedCapabilities: ["CAP-01", "CAP-02.S01.T03", "CAP-02.S04.T02", "CAP-02.S04.T03"],
  routes: ["index.html"],
  referenceUse: "design-contract-only",
  referenceId: "RO-UI-ACADEMIC-MINIMAL-1.3",
  referencePackageSha256: "db13c8d5eeee71c890ca8530d7355a7fa95ca17630e8d53adba4fc7724d609e2",
  sourceFiles: Object.fromEntries(Object.entries(sourceFiles).sort()),
  artifacts: Object.fromEntries(Object.entries(artifacts).sort()),
};
await writeFile(
  path.join(productRoot, "application-manifest.json"),
  `${JSON.stringify(manifest, null, 2)}\n`,
  { encoding: "utf8", flag: "wx" },
);
console.log(`assembled functional desktop product: ${Object.keys(artifacts).length} artifacts`);
