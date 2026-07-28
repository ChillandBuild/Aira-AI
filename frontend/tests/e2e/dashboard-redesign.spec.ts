import { test, expect } from "@playwright/test";
import path from "node:path";

const VIEWPORTS = [
  { width: 320, height: 800, label: "320-mobile" },
  { width: 768, height: 1024, label: "768-tablet" },
  { width: 1024, height: 768, label: "1024-desktop-sm" },
  { width: 1440, height: 900, label: "1440-desktop-lg" },
];

test.describe("Dashboard Redesign Verification", () => {
  test.beforeEach(async ({ context, page }) => {
    await context.addCookies([
      {
        name: "e2e-mock-user",
        value: "true",
        domain: "localhost",
        path: "/",
      },
    ]);

    await page.addInitScript(() => {
      window.localStorage.setItem(
        "aira_role_cache",
        JSON.stringify({
          userId: "user-1",
          role: "owner",
          roleId: "r1",
          roleName: "Owner",
          roleSlug: "owner",
          permissions: ["dashboard.view", "analytics.view"],
          callerId: null,
          enabledFeatures: ["whatsapp", "telecalling"],
          isSystemAdmin: false,
          forcePasswordReset: false,
        })
      );
    });

    await page.route("**/auth/v1/user*", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: "user-1",
          email: "owner@astrotamil.com",
          role: "authenticated",
          aud: "authenticated",
        }),
      });
    });

    await page.route("**/api/v1/team/me", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          role: "owner",
          role_id: "r1",
          role_name: "Owner",
          role_slug: "owner",
          permissions: ["dashboard.view", "analytics.view"],
          caller_id: null,
          enabled_features: ["whatsapp", "telecalling"],
          is_system_admin: false,
          force_password_reset: false,
        }),
      });
    });

    await page.route("**/api/v1/subscriptions/me", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ status: "active" }),
      });
    });

    await page.route("**/api/v1/analytics/overview*", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          daily_leads: [
            { day: "2026-07-22", count: 4 },
            { day: "2026-07-23", count: 8 },
            { day: "2026-07-24", count: 12 },
            { day: "2026-07-25", count: 15 },
            { day: "2026-07-26", count: 10 },
            { day: "2026-07-27", count: 18 },
            { day: "2026-07-28", count: 22 },
          ],
          daily_leads_trend_pct: 25,
          daily_messages: [
            { day: "2026-07-22", inbound: 10, outbound: 15, ai: 12, human: 3 },
            { day: "2026-07-28", inbound: 25, outbound: 30, ai: 24, human: 6 },
          ],
          funnel: { inquiries: 89, engaged: 45, hot: 18, converted: 8 },
          ai_vs_human: { ai: 150, human: 30 },
          unreplied_24h: 2,
          converted_7d: 8,
          converted_7d_trend_pct: 14,
          ai_handled_today: 24,
          by_segment: { A: 18, B: 27, C: 34, D: 10 },
          channel_breakdown: { whatsapp: 50, instagram: 20, facebook: 10, telegram: 5, upload: 4, manual: 0 },
          total_leads: 89,
          ad_attributed_leads: 30,
          new_hot_leads_7d: 18,
          new_hot_leads_7d_daily: [
            { day: "2026-07-22", count: 2 },
            { day: "2026-07-28", count: 5 },
          ],
          new_hot_leads_7d_trend_pct: 50,
        }),
      });
    });

    await page.route("**/api/v1/chat-handovers/count", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ count: 3 }),
      });
    });

    await page.route("**/api/v1/analytics/telecalling", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          calls_today: 42,
          calls_this_week: 210,
          outcome_breakdown: { converted: 12, callback: 8, not_interested: 15, invalid: 7 },
        }),
      });
    });

    await page.route("**/api/v1/analytics/ad-performance", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          campaigns: [{ id: "c1", name: "July Promo" }],
          totals: { campaigns: 1, tracked_leads: 30, conversion_rate: 0.25, progressive_rate: 0.4 },
        }),
      });
    });
  });

  for (const vp of VIEWPORTS) {
    test(`renders redesigned dashboard correctly at ${vp.label}`, async ({ page }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await page.goto("/aira/dashboard");

      // Verify key question-driven sections render
      await expect(page.getByText("Total Leads")).toBeVisible({ timeout: 10000 });
      await expect(page.getByText("New Hot Leads (7d)")).toBeVisible();
      await expect(page.getByText("Conversions (7d)")).toBeVisible();
      await expect(page.getByText("Is my AI carrying its weight?")).toBeVisible();
      await expect(page.getByText("Pipeline Activity")).toBeVisible();
      await expect(page.getByText("Where are leads coming from?")).toBeVisible();
      await expect(page.getByText("Team & Calls")).toBeVisible();
      await expect(page.getByText("Ad Spend")).toBeVisible();

      // Save screenshots into artifact directory
      const artifactDir = "/Users/prem/.gemini/antigravity/brain/61d7598f-fcce-4d1c-ae0e-ab0ced01d878";
      await page.screenshot({
        path: path.join(artifactDir, `dashboard-${vp.label}.png`),
        fullPage: true,
      });
    });
  }
});
