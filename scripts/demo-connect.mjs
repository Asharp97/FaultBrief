import { run, runUv, root } from "./lib.mjs";
import { join } from "node:path";

const args = process.argv.slice(2);
if (args[0] === "--") args.shift();
try {
  if (!args.includes("--help") && !args.includes("-h")) {
    run(process.execPath, [join(root, "scripts", "configure-demo.mjs")]);
    run(process.execPath, [join(root, "scripts", "configure-diagnostics.mjs")]);
  }
  runUv([
    "run",
    "--project",
    "backend",
    "--locked",
    "python",
    "-m",
    "demo.evaluation.prepare",
    ...args,
  ]);
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
}
