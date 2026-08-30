import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const desktopRoot = path.resolve(scriptDirectory, "..");
const repositoryRoot = path.resolve(desktopRoot, "../..");
const temporaryRoot = await mkdtemp(path.join(tmpdir(), "research-observatory-lock-renderer-"));
const fixturePath = path.join(temporaryRoot, "native-application-lock.json");

function run(command, arguments_, options = {}) {
  const result = spawnSync(command, arguments_, {
    cwd: repositoryRoot,
    encoding: "utf8",
    stdio: "pipe",
    ...options,
  });
  if (result.status !== 0) {
    process.stderr.write(result.stdout ?? "");
    process.stderr.write(result.stderr ?? "");
    throw new Error(`${command} exited with ${result.status ?? "no status"}`);
  }
  process.stdout.write(result.stdout ?? "");
  process.stderr.write(result.stderr ?? "");
}

try {
  run(process.env.CARGO ?? "cargo", [
    "test",
    "--manifest-path",
    "apps/desktop/src-tauri/Cargo.toml",
    "application_lock::tests::renderer_contract_witness",
    "--",
    "--ignored",
    "--exact",
    "--nocapture",
  ], {
    env: { ...process.env, RO_LOCK_CONTRACT_FIXTURE: fixturePath },
  });

  run(process.execPath, [
    path.join(desktopRoot, "node_modules", "vitest", "vitest.mjs"),
    "run",
    "apps/desktop/src/app/applicationSettings.native.integration.test.ts",
  ], {
    env: { ...process.env, RO_LOCK_CONTRACT_FIXTURE: fixturePath },
  });
} finally {
  await rm(temporaryRoot, { recursive: true, force: true });
}
