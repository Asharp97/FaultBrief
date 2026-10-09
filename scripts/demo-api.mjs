import { runUv } from "./lib.mjs";

runUv([
  "run",
  "--project",
  "backend",
  "--locked",
  "python",
  "-m",
  "demo.app.export_contracts",
  ...process.argv.slice(2),
]);
