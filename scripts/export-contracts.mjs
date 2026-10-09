import { runUv } from "./lib.mjs";

try {
  runUv([
    "run",
    "--project",
    "backend",
    "--locked",
    "python",
    "-m",
    "backend.app.export_contracts",
    ...process.argv.slice(2),
  ]);
} catch {
  process.exitCode = 1;
}
