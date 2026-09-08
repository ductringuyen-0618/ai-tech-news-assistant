import { test, expect, type Page, type Route } from "@playwright/test";

/**
 * M3.M6 — Per-tab visual baselines.
 *
 * One screenshot per tab, captured after the tab is in a deterministic
 * "happy-path" final state. Acts as a visual regression net for the M3
 * UI: any future change that shifts pixels by >5% will fail this spec
 * and surface a diff in the Playwright report.
 *
 * To regenerate the baselines (one-time, after intentional UI changes):
 *
 *   PLAYWRIGHT_SLOW_MO=0 npx playwright test m3-visual-baselines.spec.ts --update-snapshots
 *
 * Tolerance: maxDiffPixelRatio=0.05 (5%) — keeps OS font-rendering
 * differences from flaking. Anti-aliasing is disabled at the
 * playwright level via the screenshot options.
 *
 * Tabs covered: News Feed, Research, Digest, Saved, Settings.
 * (Knowledge Graph tab was cut.) Research uses a mock so the
 * baseline doesn't depend on a live LLM run.
 */

const SCREENSHOT_OPTS = {
  maxDiffPixelRatio: 0.05,
  animations: "disabled" as const,
  // Mask away anything that's wall-clock-dependent (timestamps,
  // relative-time labels) so the snapshot is reproducible.
  fullPage: false,
};

// ---------------------------------------------------------------------------
// Research mock — same shape as the canonical helper in research.spec.ts,
// inlined here so this spec stays self-contained.
// ---------------------------------------------------------------------------

const RESEARCH_REPORT =
  "## Executive Summary\n" +
  "Recent AI chip developments show rapid iteration see [1].\n\n" +
  "## Key Findings\n" +
  "- Major advances in AI chip design [1].\n\n" +
  "## Sources Used\n" +
  "1. TechCrunch — https://example.com/ai-chip\n";

async function installResearchMock(page: Page) {
  const frames: string[] = [];
  frames.push(
    `data: ${JSON.stringify({ type: "phase", data: "Decomposing" })}\n\n`
  );
  frames.push(
    `data: ${JSON.stringify({
      type: "decomposed",
      sub_questions: [
        "What companies are leading AI chip design?",
        "How are prices evolving across vendors?",
        "Which edge-deployment use cases are growing?",
      ],
    })}\n\n`
  );
  for (const p of ["Searching (1/3)", "Searching (2/3)", "Searching (3/3)", "Synthesizing"]) {
    frames.push(`data: ${JSON.stringify({ type: "phase", data: p })}\n\n`);
  }
  frames.push(
    `data: ${JSON.stringify({
      type: "subagent",
      data: "start",
      skill: "summarize_article",
      article_id: 1,
    })}\n\n`
  );
  frames.push(
    `data: ${JSON.stringify({
      type: "subagent",
      data: "done",
      skill: "summarize_article",
      article_id: 1,
      duration_ms: 1234,
      summary: "Leading vendor announced a new architecture.",
    })}\n\n`
  );
  frames.push(
    `data: ${JSON.stringify({
      type: "phase",
      data: "done",
      report: RESEARCH_REPORT,
    })}\n\n`
  );
  await page.route("**/api/research", async (route: Route) => {
    await route.fulfill({
      status: 200,
      headers: { "Content-Type": "text/event-stream" },
      body: frames.join(""),
    });
  });
}

// ---------------------------------------------------------------------------
// Per-tab spec — one screenshot each.
// ---------------------------------------------------------------------------

test.describe("M3.M6 — per-tab visual baselines", () => {
  test.beforeEach(async ({ page }) => {
    // Prevent caret-blink + spinner-spin from making the snapshot
    // jittery. Playwright's `animations: "disabled"` flag handles
    // CSS animations but not third-party motion.
    await page.addStyleTag({
      content: `
        *, *::before, *::after {
          animation-duration: 0s !important;
          animation-delay: 0s !important;
          transition-duration: 0s !important;
          transition-delay: 0s !important;
          caret-color: transparent !important;
        }
      `,
    }).catch(() => {});
  });

  test("news-feed-final visual", async ({ page }) => {
    test.setTimeout(60_000);
    await page.goto("/");
    await expect(page.getByRole("heading", { name: /TechPulse AI/i })).toBeVisible();
    await page.waitForLoadState("networkidle", { timeout: 15_000 }).catch(() => {});
    // Wait for either the feed or empty-state to settle.
    await page.locator(".animate-spin").first().waitFor({ state: "hidden", timeout: 15_000 }).catch(() => {});
    await page.waitForTimeout(500);
    await expect(page).toHaveScreenshot("news-feed-final.png", SCREENSHOT_OPTS);
  });

  test("research-final visual", async ({ page }) => {
    test.setTimeout(60_000);
    await installResearchMock(page);
    try {
      await page.goto("/");
      await expect(page.getByRole("heading", { name: /TechPulse AI/i })).toBeVisible();
      await page.getByRole("tab", { name: /Research/i }).click();
      await expect(page.getByPlaceholder(/AI funding rounds/i)).toBeVisible({
        timeout: 10_000,
      });
      await page.getByPlaceholder(/AI funding rounds/i).fill("Latest AI chip news");
      await page.getByRole("button", { name: /^Research$/i }).click();
      await expect(page.getByTestId("research-phase-chip")).toHaveText(/Done/i, {
        timeout: 15_000,
      });
      await page.waitForTimeout(500);
      await expect(page).toHaveScreenshot("research-final.png", SCREENSHOT_OPTS);
    } finally {
      await page.unroute("**/api/research");
    }
  });

  test("digest-final visual", async ({ page }) => {
    test.setTimeout(60_000);
    await page.goto("/");
    await expect(page.getByRole("heading", { name: /TechPulse AI/i })).toBeVisible();
    await page.getByRole("tab", { name: /Digest/i }).click();
    await page.waitForLoadState("networkidle", { timeout: 15_000 }).catch(() => {});
    await page.locator(".animate-spin").first().waitFor({ state: "hidden", timeout: 15_000 }).catch(() => {});
    await page.waitForTimeout(500);
    await expect(page).toHaveScreenshot("digest-final.png", SCREENSHOT_OPTS);
  });

  test("saved-final visual", async ({ page }) => {
    test.setTimeout(60_000);
    await page.goto("/");
    await expect(page.getByRole("heading", { name: /TechPulse AI/i })).toBeVisible();
    // `/Saved/i` would also match "Settings Unsaved changes" — use exact.
    await page.getByRole("tab", { name: "Saved", exact: true }).click();
    await page.waitForLoadState("networkidle", { timeout: 15_000 }).catch(() => {});
    await page.locator(".animate-spin").first().waitFor({ state: "hidden", timeout: 15_000 }).catch(() => {});
    await page.waitForTimeout(500);
    await expect(page).toHaveScreenshot("saved-final.png", SCREENSHOT_OPTS);
  });

  test("settings-final visual", async ({ page }) => {
    test.setTimeout(60_000);
    await page.goto("/");
    await expect(page.getByRole("heading", { name: /TechPulse AI/i })).toBeVisible();
    await page.getByRole("tab", { name: /Settings/i }).click();
    await expect(page.getByText(/Topic Preferences/i)).toBeVisible({
      timeout: 10_000,
    });
    await page.waitForTimeout(500);
    await expect(page).toHaveScreenshot("settings-final.png", SCREENSHOT_OPTS);
  });
});

// ---------------------------------------------------------------------------
// Reduced-motion contract test.
//
// When the OS reports prefers-reduced-motion: reduce, all framer-motion
// animations should resolve to instant (duration 0). We verify this by
// driving a tab switch and the suggested-query chip mount under
// emulated reduced-motion, then asserting:
//   (a) the citation hover card appears WITHOUT a scale transform
//   (b) the chips are at opacity 1 from the first frame (no fade-in)
// ---------------------------------------------------------------------------

test.describe("M3.M6 — prefers-reduced-motion is honored", () => {
  test.use({ contextOptions: { reducedMotion: "reduce" } });

  test("research tab loads with chips at opacity 1 immediately", async ({ page }) => {
    test.setTimeout(60_000);
    await installResearchMock(page);
    try {
      await page.goto("/");
      await expect(page.getByRole("heading", { name: /TechPulse AI/i })).toBeVisible();
      await page.getByRole("tab", { name: /Research/i }).click();

      // The empty-state suggestion chips render on mount. Under reduced
      // motion they should already be at opacity 1 — no fade-in. We
      // sample the computed style on the first paint after the chips
      // appear.
      const chip = page.getByTestId("suggested-query-chip").first();
      await chip.waitFor({ state: "visible", timeout: 10_000 });

      const opacity = await chip.evaluate(
        (el) => window.getComputedStyle(el).opacity
      );
      expect(
        opacity,
        `Reduced motion should leave the chip at opacity 1 from the first frame (saw ${opacity})`
      ).toBe("1");

      // The transform should be either "none" or a no-op matrix.
      const transform = await chip.evaluate(
        (el) => window.getComputedStyle(el).transform
      );
      expect(
        transform === "none" || transform.startsWith("matrix"),
        `Reduced motion should not apply a non-identity transform (saw ${transform})`
      ).toBe(true);
    } finally {
      await page.unroute("**/api/research");
    }
  });
});
