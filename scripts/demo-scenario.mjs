import { runUv } from "./lib.mjs";

const args = process.argv.slice(2);
if (args[0] === "--") args.shift();
runUv([
  "run",
  "--project",
  "backend",
  "--locked",
  "python",
  "-m",
  "demo.evaluation.control",
  ...args,
]);
