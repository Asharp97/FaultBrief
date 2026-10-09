import { test, expect } from "@playwright/test";

const url = "http://127.0.0.1:58112";
const appKey = "synthetic-demo-app-" + "a".repeat(32);
const operatorKey = "synthetic-demo-operator-" + "o".repeat(32);

test("reporting UI reproduces a disabled export, resets it, and downloads a CSV", async ({
  page,
}) => {
  await page.goto(url);
  await page.getByLabel("Reporting app token", { exact: true }).fill(appKey);
  await page.getByRole("button", { name: "Connect reporting app" }).click();
  await page.getByText("Lab operator — create or reset a scenario").click();
  await page.getByLabel("Lab operator token", { exact: true }).fill(operatorKey);
  await page.getByRole("button", { name: "Load scenario controls" }).click();
  await page.getByLabel("Scenario", { exact: true }).selectOption("feature_disabled");
  await page.getByRole("button", { name: "Create scenario", exact: true }).click();
  await expect(page.locator("#notice")).toContainText("Probe returned HTTP 409");
  await expect(page.locator("#config")).toContainText("Exports disabled");
  await page.getByRole("button", { name: "Export report", exact: true }).click();
  await expect(page.locator("#notice")).toContainText("HTTP 409");
  await expect(page.locator("#logs")).toContainText("feature_disabled");
  await page.getByRole("button", { name: "Reset this run to healthy" }).click();
  await expect(page.locator("#notice")).toContainText("Run reset");
  await expect(page.locator("#config")).toContainText("Exports enabled");
  const downloadEvent = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download CSV", exact: true }).first().click();
  const download = await downloadEvent;
  expect(download.suggestedFilename()).toBe("revenue-export.csv");
  await page.getByLabel("Act as member").selectOption({ label: "Lee — viewer" });
  await page.getByRole("button", { name: "Export report", exact: true }).click();
  await expect(page.locator("#notice")).toContainText("HTTP 403");
});

test("ambiguous scenario shows partial evidence without a claimed cause", async ({ page }) => {
  await page.goto(url);
  await page.getByLabel("Reporting app token", { exact: true }).fill(appKey);
  await page.getByRole("button", { name: "Connect reporting app" }).click();
  await page.getByText("Lab operator — create or reset a scenario").click();
  await page.getByLabel("Lab operator token", { exact: true }).fill(operatorKey);
  await page.getByRole("button", { name: "Load scenario controls" }).click();
  await page.getByLabel("Scenario", { exact: true }).selectOption("ambiguous");
  await page.getByRole("button", { name: "Create scenario", exact: true }).click();
  await expect(page.locator("#coverage")).toContainText("partial");
  await expect(page.locator("#jobs")).toContainText("EXPORT_TIMEOUT");
  await expect(page.locator("#logs")).toContainText("diagnostics are unavailable");
});
