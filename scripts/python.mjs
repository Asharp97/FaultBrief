import { runUv } from "./lib.mjs";

try {
  if (process.argv.length < 3)
    throw new Error(
      "Pass a uv command, for example: node scripts/python.mjs sync --project backend --locked",
    );
  runUv(process.argv.slice(2));
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
}
