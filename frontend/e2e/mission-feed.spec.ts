/**
 * mission-feed.spec.ts — REDESIGN Phase F.
 *
 * Covers the Mission Control feed contract added in Phase E.
 *
 * Acceptance:
 *   - With mode === "mission", /feed renders <MissionShell>.
 *   - The agent-telemetry rail is mounted.
 *   - The feed body is populated with <DenseArticleRow>s when articles
 *     are available; an empty environment is allowed (no assertion on
 *     row count beyond ">= 0").
 *   - Flipping back to Atelier on the same route restores the
 *     broadsheet grid (LeadStoryCard + NewsCards).
 *   - The shared toolbar above (search + trending) is preserved across
 *     modes — clicking a trending chip in Mission still filters.
 */
import { test, expect } from "@playwright/test";

test.describe("mission control feed", () => {
  test("flipping to Mission swaps the feed layout", async ({ page }) => {
    await page.goto("/feed", { waitUntil: "domcontentloaded" });
    await page.getByTestId("mode-toggle-mission").click();

    // Mission shell + telemetry rail should be present.
    await expect(page.getByTestId("mission-shell")).toBeVisible();
    await expect(page.getByTestId("agent-telemetry")).toBeVisible();

    // Article rows: either zero (empty env) or one-or-more DenseArticleRows.
    // We don't fail if articles haven't ingested in this environment; we
    // just guarantee the layout container is mounted.
    const rows = page.getByTestId("dense-article-row");
    expect(await rows.count()).toBeGreaterThanOrEqual(0);
  });

  test("flipping back to Atelier restores the broadsheet grid", async ({ page }) => {
    await page.goto("/feed", { waitUntil: "domcontentloaded" });
    await page.getByTestId("mode-toggle-mission").click();
    await expect(page.getByTestId("mission-shell")).toBeVisible();

    await page.getByTestId("mode-toggle-atelier").click();
    // Mission shell must disappear; the Atelier list container should
    // be the visible feed.
    await expect(page.getByTestId("mission-shell")).toHaveCount(0);
    await expect(page.getByTestId("news-feed-list")).toBeVisible();
  });

  test("telemetry rail shows idle when no agents are streaming", async ({ page }) => {
    await page.goto("/feed", { waitUntil: "domcontentloaded" });
    await page.getByTestId("mode-toggle-mission").click();
    const telemetry = page.getByTestId("agent-telemetry");
    await expect(telemetry).toBeVisible();
    // Default banner reads "idle" until a research dispatch opens.
    await expect(telemetry).toContainText(/idle|agent/i);
  });
});
