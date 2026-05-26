/**
 * atelier-home.spec.ts — REDESIGN Phase F.
 *
 * Covers the Atelier home (`/`) contract added in Phase C.
 *
 * Acceptance:
 *   - WelcomeScreen still exists as the home root (no test file rename).
 *   - AtelierHero renders the conversational headline + both CTAs +
 *     the dismiss link.
 *   - The "Research a topic" CTA navigates to /research.
 *   - The "Read today's brief" CTA navigates to /feed.
 *   - The digest grid renders when /api/digest/topics has data; it is
 *     allowed to be absent in environments without an active backend.
 */
import { test, expect } from "@playwright/test";

test.describe("atelier home", () => {
  test("renders the Atelier hero with both CTAs and the dismiss link", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });

    await expect(page.getByTestId("welcome-screen")).toBeVisible();
    await expect(page.getByTestId("atelier-hero")).toBeVisible();

    // CTAs — copy is intentionally Atelier ("Research a topic" / "Read today's brief").
    const researchCta = page.getByTestId("welcome-cta-research");
    const feedCta = page.getByTestId("welcome-cta-feed");
    const skip = page.getByTestId("welcome-dismiss");
    await expect(researchCta).toBeVisible();
    await expect(feedCta).toBeVisible();
    await expect(skip).toBeVisible();
    await expect(researchCta).toHaveText(/research a topic/i);
    await expect(feedCta).toHaveText(/read today.+brief/i);
  });

  test("research CTA routes to /research", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.getByTestId("welcome-cta-research").click();
    await expect(page).toHaveURL(/\/research$/);
  });

  test("feed CTA routes to /feed", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.getByTestId("welcome-cta-feed").click();
    await expect(page).toHaveURL(/\/feed$/);
  });

  test("digest grid renders when topics are available", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    // Generous wait — /api/digest/topics can be slow on cold start.
    const grid = page.getByTestId("atelier-digest-grid");
    const visible = await grid.isVisible({ timeout: 8_000 }).catch(() => false);
    if (visible) {
      const cards = page.getByTestId("agent-digest-card");
      const count = await cards.count();
      expect(count).toBeGreaterThan(0);
      expect(count).toBeLessThanOrEqual(4);
    } else {
      // Topic clusters not warm yet — that's a soft-allow per the
      // Atelier graceful-degradation contract. The hero still has to
      // be visible (asserted above) so the user always has CTAs.
      test.info().annotations.push({
        type: "soft-skip",
        description: "digest topics not available in this environment",
      });
    }
  });
});
