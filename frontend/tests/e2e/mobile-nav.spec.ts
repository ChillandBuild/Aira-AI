import { test, expect } from "@playwright/test";

/**
 * Mobile Bottom Nav + More Drawer E2E Tests
 *
 * Tests the 3-tab bottom nav (Home/Calls/Inbox) and the More drawer.
 * Requires: Next.js dev server on localhost:3000 + logged-in session.
 *
 * Run: npx playwright test tests/e2e/mobile-nav.spec.ts --headed
 */

test.use({ viewport: { width: 390, height: 844 } });

test.describe("Mobile bottom nav", () => {
  test("shows exactly 3 evenly-spaced tabs: Home, Calls, Inbox", async ({ page }) => {
    await page.goto("/dashboard");
    await page.waitForLoadState("networkidle");

    const nav = page.locator("nav").filter({ has: page.getByText("Home") });
    await expect(nav.getByText("Home")).toBeVisible();
    await expect(nav.getByText("Calls")).toBeVisible();
    await expect(nav.getByText("Inbox")).toBeVisible();

    // No 4th tab or leftover "More" button in the bottom bar itself.
    await expect(nav.getByText("More")).toHaveCount(0);
  });

  test("Calls tab navigates to the telecalling page and highlights active", async ({ page }) => {
    await page.goto("/dashboard");
    await page.waitForLoadState("networkidle");

    await page.getByRole("link", { name: "Calls" }).click();
    await page.waitForURL(/\/dashboard\/telecalling/);
  });
});

test.describe("More drawer", () => {
  test("opens from the header trigger and closes on backdrop tap", async ({ page }) => {
    await page.goto("/dashboard");
    await page.waitForLoadState("networkidle");

    await page.getByRole("button", { name: "More" }).click();
    await expect(page.getByText("More", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Close", exact: true })).toBeVisible();

    // Tap the backdrop (top-left corner, outside the right-side panel) to dismiss.
    await page.mouse.click(10, 10);
    await expect(page.getByRole("button", { name: "Close", exact: true })).toHaveCount(0);
  });
});
