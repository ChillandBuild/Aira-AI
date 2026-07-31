import { test, expect } from "@playwright/test";

/**
 * Dashboard Redesign Verification E2E Tests
 *
 * Verifies the redesigned tenant home dashboard (2026-07-28 spec) renders its
 * real, non-adaptive sections across breakpoints, against a real backend
 * response -- not mocked data. Requires: Next.js dev server on localhost:3000
 * + backend on its configured port + a logged-in session (this suite does
 * not authenticate itself; no auth bypass exists in this codebase on purpose).
 *
 * Run: npx playwright test tests/e2e/dashboard-redesign.spec.ts --headed
 */

const VIEWPORTS = [
  { width: 320, height: 800, label: "320-mobile" },
  { width: 768, height: 1024, label: "768-tablet" },
  { width: 1024, height: 768, label: "1024-desktop-sm" },
  { width: 1440, height: 900, label: "1440-desktop-lg" },
];

for (const vp of VIEWPORTS) {
  test(`redesigned dashboard renders its core sections at ${vp.label}`, async ({ page }) => {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await page.goto("/dashboard");
    await page.waitForLoadState("networkidle");

    // Sections present on every tenant, regardless of enabled_features.
    await expect(page.getByText("Total Leads")).toBeVisible({ timeout: 10000 });
    await expect(page.getByText("New Hot Leads (7d)")).toBeVisible();
    await expect(page.getByText("Conversions (7d)")).toBeVisible();
    await expect(page.getByText("Is my AI carrying its weight?")).toBeVisible();
    await expect(page.getByText("Pipeline Activity")).toBeVisible();
    await expect(page.getByText("Where are leads coming from?")).toBeVisible();

    await page.screenshot({
      path: `test-results/dashboard-redesign-${vp.label}.png`,
      fullPage: true,
    });
  });
}

test("analytics exposes client-controlled reporting and comparison ranges", async ({ page }) => {
  await page.goto("/dashboard/analytics");
  await page.waitForLoadState("networkidle");

  // Reporting period picker offers a custom date range.
  await expect(page.getByText("Reporting period")).toBeVisible();
  await expect(page.getByRole("button", { name: "Custom", exact: true }).first()).toBeVisible();

  // Comparison control is labelled and starts off.
  await expect(page.getByText("Compare with")).toBeVisible();
  await expect(page.getByRole("button", { name: "Off", exact: true })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(page.getByRole("button", { name: "Previous period", exact: true })).toBeVisible();

  // No date pair exists yet: reporting starts on a preset and comparison is off.
  await expect(page.locator("#overview-range-from")).toHaveCount(0);
  await expect(page.locator("#comparison-range-from")).toHaveCount(0);

  // Enabling a custom reporting range exposes the first date pair.
  await page.getByRole("button", { name: "Custom", exact: true }).first().click();
  await expect(page.locator("#overview-range-from")).toBeVisible();
  await expect(page.locator("#overview-range-to")).toBeVisible();

  // Enabling a custom comparison exposes a second, uniquely-prefixed date pair.
  await page.getByRole("button", { name: "Custom", exact: true }).nth(1).click();
  await expect(page.locator("#comparison-range-from")).toBeVisible();
  await expect(page.locator("#comparison-range-to")).toBeVisible();
  await expect(page.getByLabel("From")).toHaveCount(2);
  await expect(page.getByLabel("To")).toHaveCount(2);
});
