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
  expect(
    (
      await request.patch("/api/faultbrief/workspaces/unknown/memberships/unknown", {
        headers: { Origin: "https://untrusted.example" },
        data: { role: "owner" },
      })
    ).status(),
  ).toBe(403);
  expect(
    (
      await request.post("/api/auth/request-password-reset", {
        headers: { Origin: "http://127.0.0.1:58111" },
        data: { email: "test@example.invalid", redirectTo: "https://untrusted.example/reset" },
      })
    ).status(),
  ).toBe(400);
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

test("recovery requests do not disclose whether an account exists", async ({ page }) => {
  await page.goto("/auth/sign-in");
  await page.getByRole("link", { name: "Forgot your password?" }).click();
  await expect(page).toHaveURL(/\/auth\/forgot-password$/);
  await page.getByLabel("Email address").fill("unknown-recovery@example.invalid");
  await page.getByRole("button", { name: "Send reset link" }).click();
  await expect(page.getByRole("status")).toContainText("If an account exists");
  await expect(page).toHaveURL(/\/auth\/forgot-password$/);
});

test("email recovery updates the password and the token cannot be reused", async ({
  page,
  request,
}) => {
  const email = "recovery@example.invalid";
  await page.goto("/auth/sign-in");
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password", { exact: true }).fill("synthetic-password-123");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await page.getByRole("link", { name: "Forgot your password?" }).click();
  await expect(page).toHaveURL(/\/auth\/forgot-password$/);
  await page.getByLabel("Email address").fill(email);
  await page.getByRole("button", { name: "Send reset link" }).click();
  await expect(page.getByRole("status")).toContainText("If an account exists");
  const mail = await (
    await request.get(`http://127.0.0.1:58110/test/mailbox?email=${encodeURIComponent(email)}`)
  ).json();
  const token = new URL(mail.url).searchParams.get("token");
  await page.goto(mail.url);
  await expect(page).toHaveURL(/\/auth\/reset-password$/);
  await page.getByLabel("New password", { exact: true }).fill("new-synthetic-password-456");
  await page.getByLabel("Confirm new password").fill("mismatch-password");
  await page.getByRole("button", { name: "Update password" }).click();
  await expect(page.getByRole("status")).toContainText("must match");
  await page.getByLabel("Confirm new password").fill("new-synthetic-password-456");
  await page.getByRole("button", { name: "Update password" }).click();
  await expect(page.getByRole("status")).toContainText("Your password has been updated");
  const replay = await request.post("/api/auth/reset-password", {
    headers: { Origin: "http://127.0.0.1:58111" },
    data: { token, newPassword: "new-synthetic-password-456" },
  });
  expect(replay.status()).toBe(400);
  await page.getByRole("link", { name: "Back to sign in" }).click();
  await expect(page).toHaveURL(/\/auth\/sign-in$/);
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password", { exact: true }).fill("synthetic-password-123");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Sign-in failed");
  await page.getByLabel("Password", { exact: true }).fill("new-synthetic-password-456");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
});

test("missing, invalid and expired recovery links cannot update passwords", async ({ page }) => {
  await page.goto("/auth/reset-password?error=INVALID_TOKEN");
  await expect(page.getByRole("status")).toContainText("missing, invalid, or expired");
  await expect(page.getByRole("button", { name: "Update password" })).toHaveCount(0);
  for (const token of ["invalid-synthetic-token", "expired-synthetic-reset-token"]) {
    await page.goto(`/auth/reset-password?token=${token}`);
    await expect(page).toHaveURL(/\/auth\/reset-password$/);
    await page.getByLabel("New password", { exact: true }).fill("new-synthetic-password-456");
    await page.getByLabel("Confirm new password").fill("new-synthetic-password-456");
    await page.getByRole("button", { name: "Update password" }).click();
    await expect(page.getByRole("status")).toContainText("Could not reset the password");
  }
});

test("owners manage team roles, keep an owner, and revoke an existing session's access", async ({
  page,
  browser,
}) => {
  const teammateContext = await browser.newContext({ baseURL: test.info().project.use.baseURL });
  try {
    const teammate = await teammateContext.newPage();
    for (const [target, email] of [
      [page, "team-owner@example.invalid"],
      [teammate, "team-viewer@example.invalid"],
    ] as const) {
      await target.goto("/auth/sign-in");
      await target.getByLabel("Email address").fill(email);
      await target.getByLabel("Password", { exact: true }).fill("synthetic-password-123");
      await target.getByRole("button", { name: "Sign in", exact: true }).click();
      await expect(target).toHaveURL(/\/dashboard$/);
      await expect(
        target.getByText("Your verified identity is connected", { exact: false }),
      ).toBeVisible();
    }
    const userId = (await (await teammateContext.request.get("/api/faultbrief/me")).json()).id;
    await page.getByLabel("Company or workspace name").fill("Team browser company");
    await page.getByRole("button", { name: "Create workspace", exact: true }).click();
    await page.getByRole("button", { name: "View team for Team browser company" }).click();
    const team = page.getByRole("region", { name: "Team for Team browser company" });
    const ownerRow = team.getByRole("listitem").filter({ hasText: "You · owner" });
    await ownerRow.getByRole("combobox").selectOption("viewer");
    await ownerRow.getByRole("button", { name: "Save role" }).click();
    await expect(team.getByRole("status")).toContainText("at least one active owner");
    await team.getByLabel("Teammate user ID").fill(userId);
    await team.getByRole("button", { name: "Add teammate" }).click();
    await expect(team.getByRole("status")).toContainText("Teammate added");
    await teammate.reload();
    await teammate.getByRole("button", { name: "View team for Team browser company" }).click();
    const viewerTeam = teammate.getByRole("region", { name: "Team for Team browser company" });
    await expect(viewerTeam.getByText("You · viewer · active", { exact: true })).toBeVisible();
    await expect(viewerTeam.getByRole("button", { name: "Add teammate" })).toHaveCount(0);
    const spaces = await (await teammateContext.request.get("/api/faultbrief/workspaces")).json();
    const wid = spaces.items.find((w: { name: string }) => w.name === "Team browser company").id;
    const roster = await (
      await teammateContext.request.get(`/api/faultbrief/workspaces/${wid}/memberships`)
    ).json();
    const mid = roster.items.find((m: { user_id: string }) => m.user_id === userId).id;
    expect(
      (
        await teammateContext.request.patch(
          `/api/faultbrief/workspaces/${wid}/memberships/${mid}`,
          {
            headers: { Origin: "http://127.0.0.1:58111" },
            data: { role: "owner" },
          },
        )
      ).status(),
    ).toBe(403);
    const teammateRow = team
      .getByRole("listitem")
      .filter({ has: page.getByText(userId, { exact: true }) });
    await teammateRow.getByRole("combobox").selectOption("support");
    await teammateRow.getByRole("button", { name: "Save role" }).click();
    await expect(
      teammateRow.getByText("Teammate · support · active", { exact: true }),
    ).toBeVisible();
    await teammateRow.getByRole("button", { name: "Deactivate", exact: true }).click();
    await expect(
      teammateRow.getByText("Teammate · support · inactive", { exact: true }),
    ).toBeVisible();
    expect(
      (await teammateContext.request.get(`/api/faultbrief/workspaces/${wid}/memberships`)).status(),
    ).toBe(404);
    await teammate.reload();
    await expect(
      teammate.getByRole("button", { name: "View team for Team browser company" }),
    ).toHaveCount(0);
    await teammateRow.getByRole("button", { name: "Reactivate" }).click();
    await expect(
      teammateRow.getByText("Teammate · support · active", { exact: true }),
    ).toBeVisible();
    expect(
      (await teammateContext.request.get(`/api/faultbrief/workspaces/${wid}/memberships`)).status(),
    ).toBe(200);
  } finally {
    await teammateContext.close();
  }
});
