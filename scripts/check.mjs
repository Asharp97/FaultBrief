import { pnpm, root, run, runUv } from "./lib.mjs";
import { join } from "node:path";

try {
  run(pnpm, [
    "--dir",
    "frontend",
    "exec",
    "prettier",
    root,
    "--ignore-path",
    join(root, ".prettierignore"),
    "--ignore-path",
    join(root, ".gitignore"),
    "--check",
  ]);
  runUv(["run", "--project", "backend", "--locked", "ruff", "check", "backend", "demo", "tests"]);
  runUv([
    "run",
    "--project",
    "backend",
    "--locked",
    "ruff",
    "format",
    "--check",
    "backend",
    "demo",
    "tests",
  ]);
  runUv(["run", "--project", "backend", "--locked", "pytest"]);
  runUv([
    "run",
    "--project",
    "backend",
    "--locked",
    "python",
    "-m",
    "backend.app.export_contracts",
    "--check",
  ]);
  runUv([
    "run",
    "--project",
    "backend",
    "--locked",
    "python",
    "-m",
    "demo.app.export_contracts",
    "--check",
  ]);
  run(pnpm, ["--dir", "frontend", "build"]);
  run(pnpm, ["--dir", "frontend", "typecheck"]);
  console.log("All repository checks passed.");
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
}
