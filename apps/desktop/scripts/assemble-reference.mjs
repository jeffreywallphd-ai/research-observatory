import { createHash } from "node:crypto";
import { cp, mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(appRoot, "..", "..");
const referenceRoot = path.join(repoRoot, "design", "ui-reference");
const distRoot = path.join(appRoot, "dist");
const excludedInputDirectories = new Set(["dist", "node_modules", "target"]);

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

for (const source of await filesBelow(referenceRoot)) {
  const relative = path.relative(referenceRoot, source).replaceAll("\\", "/");
  if (!relative.endsWith(".html") && !relative.startsWith("assets/")) continue;
  const destination = path.join(distRoot, relative);
  await mkdir(path.dirname(destination), { recursive: true });
  if (relative.endsWith(".html")) {
    const html = await readFile(source, "utf8");
    const marker = "</body>";
    if (!html.includes(marker)) throw new Error(`HTML document lacks body terminator: ${relative}`);
    const generated = html.replace(marker, '    <script type="module" src="runtime/main.js"></script>\n    </body>');
    await writeFile(destination, generated, { encoding: "utf8", flag: "wx" });
  } else {
    await cp(source, destination, { errorOnExist: true, force: false });
  }
}

const sourceFiles = {};
for (const source of await filesBelow(appRoot, excludedInputDirectories)) {
  const relative = path.relative(repoRoot, source).replaceAll("\\", "/");
  sourceFiles[relative] = sha256(await readFile(source));
}
for (const relative of ["Cargo.toml", "Cargo.lock", "package.json", "pnpm-lock.yaml", "verification/extensions/desktop-ui.json"]) {
  sourceFiles[relative] = sha256(await readFile(path.join(repoRoot, relative)));
}

const artifacts = {};
for (const artifact of await filesBelow(distRoot)) {
  const relative = path.relative(distRoot, artifact).replaceAll("\\", "/");
  if (relative !== "application-manifest.json") artifacts[relative] = sha256(await readFile(artifact));
}

const manifest = {
  schemaVersion: "1.0",
  documentType: "desktop-application-build-manifest",
  referenceId: "RO-UI-ACADEMIC-MINIMAL-1.6",
  referencePackageSha256: "8d7fdc7ae43f04477ab55574542ad928500270f48d100bec74c4872ccb4366ea",
  sourceFiles,
  artifacts,
};
await writeFile(
  path.join(distRoot, "application-manifest.json"),
  `${JSON.stringify(manifest, null, 2)}\n`,
  { encoding: "utf8", flag: "wx" },
);
console.log(`assembled desktop reference conformance fixture: ${Object.keys(artifacts).length} artifacts`);
