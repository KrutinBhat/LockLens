import { test, expect } from "@playwright/test";

/**
 * Critical end-to-end workflow:
 * register → library visible → run lost-update scenario → evidence → export.
 * Requires the backend (port 8000) and a frontend preview (port 4173) with /api proxied.
 */
test("create account → execute scenario → inspect evidence → export", async ({ page }) => {
  const email = `e2e_${Date.now()}@test.dev`;
  await page.goto("/login");
  await page.getByRole("button", { name: "Create account" }).click();
  await page.getByPlaceholder("Email").fill(email);
  await page.getByPlaceholder("Display name").fill("e2e");
  await page.getByPlaceholder(/Password/).fill("password123");
  await page.getByRole("button", { name: "Create account" }).last().click();
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();

  await page.goto("/scenarios");
  const card = page.locator("div.rounded-2xl", { has: page.getByRole("heading", { name: /Lost Update/i }) });
  await expect(card).toBeVisible();
  await card.getByRole("button", { name: "Run" }).click();

  await expect(page).toHaveURL(/\/runs\/\d+/);
  await expect(page.getByText("anomaly detected", { exact: false })).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText("Evidence-backed findings")).toBeVisible();

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "JSON" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toContain("locklens-run");
});
