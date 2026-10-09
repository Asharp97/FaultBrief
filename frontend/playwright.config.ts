import { defineConfig } from "@playwright/test";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { randomUUID } from "node:crypto";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: "list",
  use: { baseURL: "http://127.0.0.1:58111", trace: "off", screenshot: "off" },
  webServer: [
    {
      command:
        "node ../scripts/python.mjs run --project backend --locked uvicorn --app-dir demo app.main:app --host 127.0.0.1 --port 58112 --log-level warning --no-access-log",
      url: "http://127.0.0.1:58112/health",
      reuseExistingServer: false,
      env: {
        DEMO_ENVIRONMENT: "test",
        DEMO_DATABASE_PATH: join(tmpdir(), `faultbrief-demo-${randomUUID()}.sqlite3`),
        DEMO_OPERATOR_TOKEN: "synthetic-demo-operator-" + "o".repeat(32),
        DEMO_APP_TOKEN: "synthetic-demo-app-" + "a".repeat(32),
        DEMO_DIAGNOSTIC_TOKEN: "synthetic-demo-diagnostic-" + "d".repeat(32),
      },
    },
    {
      command: "node tests/mock-auth.mjs",
      url: "http://127.0.0.1:58110/health",
      reuseExistingServer: false,
    },
    {
      command: "pnpm dev --hostname 127.0.0.1 --port 58111",
      url: "http://127.0.0.1:58111/auth/sign-in",
      timeout: 120000,
      reuseExistingServer: false,
      env: {
        NEON_AUTH_BASE_URL: "http://127.0.0.1:58110/neondb/auth",
        NEON_AUTH_COOKIE_SECRET: "synthetic-browser-tests-cookie-secret-32-characters",
        FAULTBRIEF_API_BASE_URL: "http://127.0.0.1:58110",
        FAULTBRIEF_SMOKE: "1",
      },
    },
  ],
});
