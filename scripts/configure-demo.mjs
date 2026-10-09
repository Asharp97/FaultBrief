import { randomBytes } from "node:crypto";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { parseEnv } from "node:util";
import { join } from "node:path";
import { root } from "./lib.mjs";

const path = join(root, "demo", ".env");
let text = existsSync(path) ? readFileSync(path, "utf8") : "DEMO_ENVIRONMENT=development\n";
const values = parseEnv(text);
for (const name of ["DEMO_OPERATOR_TOKEN", "DEMO_APP_TOKEN", "DEMO_DIAGNOSTIC_TOKEN"]) {
  if (values[name] && values[name].length < 32)
    throw new Error("Existing demo keys must be at least 32 characters.");
  if (!values[name]) text += `${name}=${randomBytes(32).toString("base64url")}\n`;
}
const keys = parseEnv(text);
if (new Set([keys.DEMO_OPERATOR_TOKEN, keys.DEMO_APP_TOKEN, keys.DEMO_DIAGNOSTIC_TOKEN]).size !== 3)
  throw new Error("Use distinct keys for the three demo roles.");
writeFileSync(path, text, { mode: 0o600 });
console.log(
  "Configured demo/.env with separate app, operator, and read-only diagnostic keys. Values were not printed. Restart the demo service.",
);
