import { runUv } from "./lib.mjs";

try {
  runUv([
    "run",
    "--project",
    "backend",
    "--locked",
    "python",
    "-m",
    "backend.app.migrations",
    process.argv[2] || "upgrade",
  ]);
} catch {
  console.error("Database migration command failed. Check configuration and migration history.");
  process.exitCode = 1;
}
