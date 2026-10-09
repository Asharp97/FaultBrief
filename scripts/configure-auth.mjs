import { randomBytes } from "node:crypto";
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { parseEnv } from "node:util";
import { join } from "node:path";
import { root } from "./lib.mjs";

try {
  const backend = parseEnv(readFileSync(join(root, "backend", ".env"), "utf8"));
  const baseUrl = process.env.NEON_AUTH_BASE_URL || backend.AUTH_URL || backend.NEON_AUTH_BASE_URL;
  if (!baseUrl) throw new Error("Configure AUTH_URL in backend/.env first.");
  const url = new URL(baseUrl);
  if (url.protocol !== "https:" || url.username || url.password)
    throw new Error("The Neon Auth URL must be HTTPS without embedded credentials.");
  const path = join(root, "frontend", ".env.local");
  let text = existsSync(path) ? readFileSync(path, "utf8") : "";
  const values = parseEnv(text);
  if (values.NEON_AUTH_BASE_URL && values.NEON_AUTH_BASE_URL !== baseUrl)
    throw new Error(
      "Frontend and backend Auth URLs differ. Review your local configuration before continuing.",
    );
  if (!values.NEON_AUTH_BASE_URL) text += `\nNEON_AUTH_BASE_URL=${JSON.stringify(baseUrl)}\n`;
  if (values.NEON_AUTH_COOKIE_SECRET && values.NEON_AUTH_COOKIE_SECRET.length < 32)
    throw new Error("The existing cookie secret must be at least 32 characters.");
  if (!values.NEON_AUTH_COOKIE_SECRET)
    text += `NEON_AUTH_COOKIE_SECRET=${randomBytes(32).toString("base64url")}\n`;
  if (!values.FAULTBRIEF_API_BASE_URL) text += "FAULTBRIEF_API_BASE_URL=http://127.0.0.1:8000\n";
  writeFileSync(path, text, { mode: 0o600 });
  console.log(
    "Configured frontend Neon Auth and a private cookie secret. No values were printed. Restart pnpm run dev.",
  );
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
}
