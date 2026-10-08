import { copyFileSync, existsSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import { pnpm, python, root, run, runUv, uvVersion } from "./lib.mjs";

try {
  for (const [example, local] of [
    [".env.example", ".env"],
    ["frontend/.env.example", "frontend/.env.local"],
  ]) {
    const destination = join(root, local);
    if (!existsSync(destination)) {
      copyFileSync(join(root, example), destination);
      console.log(`Created ${local} from its example.`);
    }
  }
  const uvTarget = join(root, ".tools", "uv");
  mkdirSync(uvTarget, { recursive: true });
  if (!existsSync(join(uvTarget, `uv-${uvVersion}.dist-info`))) {
    run(python, [
      "-m",
      "pip",
      "install",
      "--disable-pip-version-check",
      "--cache-dir",
      join(root, ".tools", "pip-cache"),
      "--target",
      uvTarget,
      "--upgrade",
      `uv==${uvVersion}`,
    ]);
  }
  run(pnpm, ["--dir", "frontend", "install", "--frozen-lockfile"]);
  runUv(["sync", "--project", "backend", "--locked"]);
  console.log("Setup complete. Run pnpm run dev to start the three local services.");
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
}
