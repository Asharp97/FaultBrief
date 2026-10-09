import { readFileSync, writeFileSync } from "node:fs";
import { spawnSync } from "node:child_process";

const snapshots = ["next-env.d.ts", "tsconfig.json"].map((path) => ({
  path,
  data: readFileSync(path),
}));
try {
  const result = spawnSync(
    process.execPath,
    [process.env.npm_execpath, "exec", "playwright", "test", ...process.argv.slice(2)],
    { stdio: "inherit" },
  );
  if (result.error) throw result.error;
  process.exitCode = result.status ?? 1;
} finally {
  for (const snapshot of snapshots) {
    if (readFileSync(snapshot.path, "utf8").includes(".next-smoke/"))
      writeFileSync(snapshot.path, snapshot.data);
  }
}
