import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: "list",
  use: { baseURL: "http://127.0.0.1:58111", trace: "off", screenshot: "off" },
  webServer: [
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
