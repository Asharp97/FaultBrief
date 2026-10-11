import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { parseEnv } from "node:util";
import { root } from "./lib.mjs";

try {
  const demo = join(root, "demo", ".env");
  if (!existsSync(demo)) throw new Error("Run pnpm run demo:configure first.");
  const key = parseEnv(readFileSync(demo, "utf8")).DEMO_DIAGNOSTIC_TOKEN;
  if (!key || key.length < 32) throw new Error("The demo needs a valid diagnostic token.");
  const path = join(root, "backend", ".env");
  const before = existsSync(path) ? readFileSync(path, "utf8") : "";
  const values = parseEnv(before);
  if (values.DIAGNOSTIC_DEMO_TOKEN && values.DIAGNOSTIC_DEMO_TOKEN !== key)
    throw new Error(
      "A different diagnostic token is configured. Update backend/.env deliberately.",
    );
  if (!values.DIAGNOSTIC_DEMO_TOKEN) {
    writeFileSync(
      path,
      before.trimEnd() +
        `\n\n# Read-only Ledger connector; never copy the operator or app token.\nDIAGNOSTIC_DEMO_TOKEN=${key}\n`,
      { mode: 0o600 },
    );
  }
  console.log(
    "Read-only diagnostic credential configured in ignored backend/.env; no credentials printed.",
  );
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
}
