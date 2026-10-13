import { expect, test } from "@playwright/test";

test.describe("real investigation worker", () => {
  test.skip(
    !process.env.FAULTBRIEF_TEST_DATABASE_URL,
    "Requires the disposable PostgreSQL test database configured in CI.",
  );

  for (const scenario of ["feature_disabled", "healthy", "ambiguous"] as const) {
    test(`ticket to supported report: ${scenario}`, async ({ page, context, browser }) => {
      await page.goto("/auth/sign-in");
      await page.getByLabel("Email address").fill(`${scenario}-investigator@example.invalid`);
      await page.getByLabel("Password", { exact: true }).fill("synthetic-password-123");
      await page.getByRole("button", { name: "Sign in", exact: true }).click();
      await expect(page).toHaveURL(/\/dashboard$/);
      await expect(
        page.getByText("Your verified identity is connected", { exact: false }),
      ).toBeVisible();
      const company = `Investigation ${scenario}`;
      await page.getByLabel("Company or workspace name").fill(company);
      await page.getByRole("button", { name: "Create workspace", exact: true }).click();
      await expect(page.getByText(company, { exact: true })).toBeVisible();
      const workspaces = await (await context.request.get("/api/faultbrief/workspaces")).json();
      const wid = workspaces.items.find((item: { name: string }) => item.name === company).id;
      const jwt = (await (await context.request.get("/api/auth/token")).json()).token;
      const fixture = await context.request.post("http://127.0.0.1:58113/test/seed", {
        headers: { Authorization: `Bearer ${jwt}` },
        data: { workspace_id: wid, scenario },
      });
      expect(fixture.status()).toBe(200);
      const references = await fixture.json();
      await page.getByRole("button", { name: `Investigate ${company}`, exact: true }).click();
      const panel = page.getByRole("region", { name: `Investigations for ${company}` });
      await panel.getByLabel("Affected customer").selectOption(references.customer_id);
      await panel
        .getByLabel("What went wrong?")
        .fill("Why did this account's revenue export fail?");
      await panel.getByText("Add request references (optional)", { exact: true }).click();
      await panel.getByLabel("Affected user reference").fill(references.member_id);
      await panel.getByLabel("Request reference", { exact: true }).fill(references.request_id);
      await panel.getByRole("button", { name: "Investigate ticket", exact: true }).click();
      const report = panel.getByRole("article", { name: "Investigation report" });
      await expect(report).toBeVisible({ timeout: 30000 });
      await expect(report).toContainText("AI explanation");
      await expect(report.getByRole("heading", { name: "Observed facts" })).toBeVisible();
      await expect(report.getByRole("heading", { name: "Suggested next steps" })).toBeVisible();
      expect(await report.getByRole("link").count()).toBeGreaterThan(0);
      if (scenario === "feature_disabled")
        await expect(
          report.getByRole("heading", { name: "Exports are disabled for this customer." }),
        ).toBeVisible();
      if (scenario === "healthy") await expect(report).toContainText("completed successfully");
      if (scenario === "ambiguous") {
        await expect(report).toContainText("available evidence does not establish why");
        await expect(report).toContainText("symptom, not an established root cause");
      }
      const cases = await (
        await context.request.get(`/api/faultbrief/workspaces/${wid}/investigations`)
      ).json();
      const iid = cases.items[0].id;
      const outsider = await browser.newContext({ baseURL: test.info().project.use.baseURL });
      try {
        await outsider.request.post("/api/auth/sign-in/email", {
          headers: { Origin: "http://127.0.0.1:58111" },
          data: {
            email: `outsider-${scenario}-investigator@example.invalid`,
            password: "synthetic-password-123",
          },
        });
        expect(
          (
            await outsider.request.get(
              `/api/faultbrief/workspaces/${wid}/investigations/${iid}/report`,
            )
          ).status(),
        ).toBe(404);
        expect(
          (
            await outsider.request.get(
              `/api/faultbrief/workspaces/${wid}/investigations/${iid}/evidence`,
            )
          ).status(),
        ).toBe(404);
      } finally {
        await outsider.close();
      }
      await page.setViewportSize({ width: 390, height: 844 });
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= document.documentElement.clientWidth,
        ),
      ).toBe(true);
    });
  }
});
