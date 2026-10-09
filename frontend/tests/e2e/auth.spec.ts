import { test, expect } from "@playwright/test";

test("unauthenticated dashboard and API requests are blocked", async ({ page, request }) => {
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/auth\/sign-in$/);
  expect((await request.get("/api/faultbrief/me")).status()).toBe(401);
  expect((await request.get("/api/auth/admin/list-users")).status()).toBe(404);
  expect(
    (
      await request.post("/api/auth/sign-in/email", {
        headers: { Origin: "https://untrusted.example" },
        data: {},
      })
    ).status(),
  ).toBe(403);
});

test("signup creates a session, authorizes API calls, and logout removes access", async ({
  page,
  context,
}) => {
  await page.goto("/auth/sign-up");
  await page.getByLabel("Full name").fill("Jamie Engineer");
  await page.getByLabel("Email address").fill("jamie@example.invalid");
  await page.getByLabel("Password", { exact: true }).fill("synthetic-password-123");
  await page.getByRole("button", { name: "Create account", exact: true }).click();
  await expect(page).toHaveURL(/\/dashboard$/, { timeout: 30000 });
  await expect(
    page.getByText("Your verified identity is connected", { exact: false }),
  ).toBeVisible();
  await page.getByLabel("Company or workspace name").fill("Browser test company");
  await page.getByRole("button", { name: "Create workspace", exact: true }).click();
  await expect(page.getByText("Browser test company", { exact: true })).toBeVisible();
  const cookies = await context.cookies();
  expect(
    cookies
      .filter((c) => c.name.includes("session"))
      .every((c) => c.httpOnly && c.sameSite === "Lax"),
  ).toBe(true);
  const crossOrigin = await context.request.post("/api/faultbrief/workspaces", {
    headers: { Origin: "https://untrusted.example" },
    data: { name: "Forbidden" },
  });
  expect(crossOrigin.status()).toBe(403);
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page).toHaveURL(/\/auth\/sign-in$/);
  expect((await context.request.get("/api/faultbrief/me")).status()).toBe(401);
});

test("invalid credentials show an error; valid credentials sign in", async ({ page }) => {
  await page.goto("/auth/sign-in");
  await page.getByLabel("Email address").fill("support@example.invalid");
  await page.getByLabel("Password", { exact: true }).fill("wrong-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Sign-in failed");
  await expect(page).toHaveURL(/\/auth\/sign-in$/);
  await page.getByLabel("Password", { exact: true }).fill("synthetic-password-123");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/dashboard$/, { timeout: 30000 });
});

test("signup requiring verification does not pretend to authenticate", async ({ page }) => {
  await page.goto("/auth/sign-up");
  await page.getByLabel("Full name").fill("Unverified User");
  await page.getByLabel("Email address").fill("verify@example.invalid");
  await page.getByLabel("Password", { exact: true }).fill("synthetic-password-123");
  await page.getByRole("button", { name: "Create account", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Check your email");
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/auth\/sign-in$/);
});
