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
    await expect(page.getByText("New Leads Today", { exact: true })).toBeVisible({ timeout: 10000 });
    await expect(page.getByText("New Hot Leads Today", { exact: true })).toBeVisible();
    await expect(page.getByText("Conversions Today", { exact: true })).toBeVisible();
    await expect(page.getByText(/total leads all-time/)).toBeVisible();
    await expect(page.getByText("Is my AI carrying its weight?")).toBeVisible();
    await expect(page.getByText("Pipeline Activity")).toBeVisible();
    await expect(page.getByText("Where did today's leads come from?")).toBeVisible();

    await page.screenshot({
      path: `test-results/dashboard-redesign-${vp.label}.png`,
      fullPage: true,
    });
  });
}

test("analytics exposes client-controlled reporting and comparison ranges", async ({ page }) => {
  await page.goto("/dashboard/analytics");
  await page.waitForLoadState("networkidle");

  // Both pickers render inline in the header, no intermediate panel to open first.
  await expect(page.getByText("Reporting period", { exact: true })).toBeVisible();
  await expect(page.getByText("Compare with", { exact: true })).toBeVisible();
  await expect(page.getByRole("combobox").first()).toHaveValue("today");
  await expect(page.locator("#analytics-range-from")).toHaveCount(0);

  // Selecting Custom exposes the reporting date pair.
  await page.getByRole("combobox").first().selectOption("custom");
  await expect(page.locator("#analytics-range-from")).toBeVisible();
  await expect(page.locator("#analytics-range-to")).toBeVisible();

  // The comparison control starts off, labelled inline.
  await expect(page.getByRole("combobox").last()).toHaveValue("off");
  await expect(page.getByRole("combobox").last()).toContainText("Previous period");

  // Enabling a custom comparison exposes a second, uniquely-prefixed date pair.
  await expect(page.locator("#comparison-range-from")).toHaveCount(0);
  await page.getByRole("combobox").last().selectOption("custom");
  await expect(page.locator("#comparison-range-from")).toBeVisible();
  await expect(page.locator("#comparison-range-to")).toBeVisible();
  await expect(page.getByLabel("From")).toHaveCount(2);
  await expect(page.getByLabel("To")).toHaveCount(2);
});
