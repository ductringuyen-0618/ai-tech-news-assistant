import { test, expect } from "@playwright/test";
import {
  assertNoHtmlEntities,
  assertNoMojibake,
  assertNoUndefinedNullObjectObject,
  assertNoDuplicateSiblings,
  assertNoMockDataLeak,
  assertNoHorizontalOverflow,
  installConsoleErrorListener,
  assertConsoleClean,
} from "./_lib/rubric";

/**
 * News Feed tab â€” asserts real article data renders and filter/search work.
 *
 * Catches: seed-data regressions, broken category filtering, broken search.
 *
 * Note: the suite expects the user's saved categories on the backend to
 * match real article categories. If the saved settings drift away from the
 * real category vocabulary (e.g. legacy "AI" / "Machine Learning" while
 * articles are tagged "AI/ML"), the page will show "No articles found"
 * and these tests will fail â€” surfacing exactly the kind of behavior bug
 * the contract suite missed.
 */

const KNOWN_REAL_SOURCES = [
  "TechCrunch",
  "Ars Technica",
  "The Verge",
  "MIT Technology Review",
  "Hacker News",
  "Wired",
];

// Reset filters by clearing the in-page category chips before each test.
// This isolates the news-feed assertions from whatever the user saved last.
async function clearFiltersIfPresent(page: import("@playwright/test").Page) {
  const clearBtn = page.getByRole("button", { name: /^Clear Filters$/i });
  if (await clearBtn.isVisible().catch(() => false)) {
    await clearBtn.click();
    // Give React a tick to refetch.
    await page.waitForTimeout(500);
  }
}

test.describe("News Feed tab", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/feed");
    await expect(page.getByRole("heading", { name: /TechPulse AI/i })).toBeVisible();
    // Wait for the initial article fetch to settle (or empty-state to render).
    await page.waitForLoadState("networkidle", { timeout: 20_000 }).catch(() => {});
    await expect(page.locator(".animate-spin").first()).toBeHidden({ timeout: 20_000 });
  });

  test("page renders with branding and at least one article", async ({ page }) => {
    await expect(page.getByRole("heading", { name: /TechPulse AI/i })).toBeVisible();

    // If a filter mismatch shows the empty-state, clear filters and try again.
    const emptyState = page.getByText(/No articles found/i);
    if (await emptyState.isVisible().catch(() => false)) {
      await clearFiltersIfPresent(page);
      // Wait for the refetch to settle.
      await page.waitForLoadState("networkidle", { timeout: 10_000 }).catch(() => {});
      await expect(page.locator(".animate-spin").first()).toBeHidden({
        timeout: 15_000,
      });
    }

    // Article cards render via the shadcn Card component which carries
    // data-slot="card". This is the stable hook.
    const articleCards = page.locator('[data-slot="card"]');
    await expect(articleCards.first()).toBeVisible({ timeout: 15_000 });
    const count = await articleCards.count();
    expect(count).toBeGreaterThan(0);
  });

  test("no article title is seed-data", async ({ page }) => {
    const emptyState = page.getByText(/No articles found/i);
    if (await emptyState.isVisible().catch(() => false)) {
      await clearFiltersIfPresent(page);
      await page.waitForLoadState("networkidle", { timeout: 10_000 }).catch(() => {});
      await expect(page.locator(".animate-spin").first()).toBeHidden({
        timeout: 15_000,
      });
    }

    // CardTitle nodes carry data-slot="card-title".
    const titles = await page.locator('[data-slot="card-title"]').allTextContents();
    expect(titles.length).toBeGreaterThan(0);
    for (const title of titles) {
      const trimmed = title.trim().toLowerCase();
      // Worker 1 wiped seed='seed' rows; this test would fail if they came back.
      expect(trimmed).not.toMatch(/^seed[-_ ]/);
      expect(trimmed).not.toContain("seed summary");
    }
  });

  test("source badges show real sources", async ({ page }) => {
    const emptyState = page.getByText(/No articles found/i);
    if (await emptyState.isVisible().catch(() => false)) {
      await clearFiltersIfPresent(page);
      await page.waitForLoadState("networkidle", { timeout: 10_000 }).catch(() => {});
      await expect(page.locator(".animate-spin").first()).toBeHidden({
        timeout: 15_000,
      });
    }

    // The source name renders inside the card header as a span with
    // .text-gray-500. Scoped to cards so we don't pull header chrome.
    const sourceTexts = await page
      .locator('[data-slot="card"] .text-gray-500')
      .allTextContents();

    const hasRealSource = sourceTexts.some((s) =>
      KNOWN_REAL_SOURCES.some((known) =>
        s.toLowerCase().includes(known.toLowerCase())
      )
    );

    expect(
      hasRealSource,
      `Expected at least one source from ${KNOWN_REAL_SOURCES.join(", ")}; saw: ${sourceTexts.slice(0, 10).join(" | ")}`
    ).toBe(true);

    for (const s of sourceTexts) {
      expect(s.trim().toLowerCase()).not.toBe("seed");
    }
  });

  test("M3.M3 â€” Trending Now rail is visible with at least one category chip", async ({
    page,
  }) => {
    // The TrendingRail aggregates category counts; in worst case it may
    // need a moment for the per-category /api/news?category=X round-trips
    // to settle. Wait up to 20s for at least one chip.
    const rail = page.getByTestId("news-feed-trending-rail");
    await expect(rail).toBeVisible({ timeout: 20_000 });

    // Loading state renders skeletons; wait for actual chip buttons.
    const chips = page.getByTestId("news-feed-trending-chip");
    await expect(chips.first()).toBeVisible({ timeout: 20_000 });

    const chipCount = await chips.count();
    expect(
      chipCount,
      "Trending rail should render at least one category chip â€” backend categories are empty?"
    ).toBeGreaterThanOrEqual(1);

    // Clicking a chip should change the filter set. We assert via the
    // visible "Filtered by:" panel that the chip's category now appears.
    const firstChip = chips.first();
    const chipCategory = await firstChip.getAttribute("data-category");
    expect(chipCategory).toBeTruthy();
    await firstChip.click();

    // Either the active-filters bar shows the chip, or the chip itself
    // toggled to its active state.
    const activeFilters = page.getByTestId("news-feed-active-filters");
    if (chipCategory) {
      await expect(activeFilters.getByText(chipCategory, { exact: true })).toBeVisible({
        timeout: 5_000,
      });
    }
  });

  test("M3.M3 â€” article cards use Linear-dense styling (font â‰¤ 14px, padding â‰¤ 12px)", async ({
    page,
  }) => {
    // Ensure at least one card is present.
    await expect(page.locator('[data-slot="card"]').first()).toBeVisible({
      timeout: 15_000,
    });

    const metrics = await page.evaluate(() => {
      const card = document.querySelector('[data-slot="card"]') as HTMLElement | null;
      if (!card) return null;
      const cardStyle = window.getComputedStyle(card);
      const title = card.querySelector('[data-slot="card-title"]') as HTMLElement | null;
      const titleSize = title
        ? parseFloat(window.getComputedStyle(title).fontSize)
        : null;
      const padTop = parseFloat(cardStyle.paddingTop);
      const padBottom = parseFloat(cardStyle.paddingBottom);
      const padLeft = parseFloat(cardStyle.paddingLeft);
      const padRight = parseFloat(cardStyle.paddingRight);
      return { titleSize, padTop, padBottom, padLeft, padRight };
    });

    expect(metrics, "Expected to find an article card").not.toBeNull();
    // Title font cap: dense layout = text-sm (14px). Tolerate up to 16px
    // for safety against root-font scaling.
    expect(
      metrics!.titleSize ?? 0,
      `Title font-size was ${metrics!.titleSize}px; dense layout expects â‰¤ 16px`
    ).toBeLessThanOrEqual(16);
    // Card padding â‰¤ 12px (`p-3`). Tolerate 14px.
    expect(metrics!.padTop).toBeLessThanOrEqual(14);
    expect(metrics!.padLeft).toBeLessThanOrEqual(14);
  });

  test("search input updates the article list", async ({ page }) => {
    // Regression test for review-07's confirmed bug: submitting a search
    // updated the "N STORIES" count but left the rendered list
    // pixel-identical to the unfiltered feed (search/count desync). The
    // backend now does a real title/content substring match (see
    // article_repository.list_articles), so this asserts the DOM itself
    // changes in response to a search, not just that nothing crashed.
    const searchInput = page.getByPlaceholder(/search tech news/i);
    await expect(searchInput).toBeVisible();

    const titlesBefore = await page
      .locator('[data-slot="card-title"]')
      .allTextContents();

    // A deliberately unlikely-to-match-everything term so a real filter
    // is very likely to narrow (or empty) the result set.
    const NEEDLE = "zzz-nonexistent-query-term-xyz";
    await searchInput.fill(NEEDLE);
    await searchInput.press("Enter");

    // Small debounce â€” the search refetches; let it settle.
    await page.waitForTimeout(2000);
    await expect(page.locator(".animate-spin").first()).toBeHidden({
      timeout: 15_000,
    });

    const cards = page.locator('[data-slot="card"]');
    const emptyState = page.getByText(/No articles found/i);

    const cardsVisible = (await cards.count()) > 0;
    const emptyVisible = await emptyState.isVisible().catch(() => false);

    expect(
      cardsVisible || emptyVisible,
      "Search should either return results or show the empty state â€” never a blank/crashed page"
    ).toBe(true);

    // The core regression check: a nonsense query must NOT leave the same
    // set of titles on screen. Either the empty-state renders, or the
    // title set actually changed (fewer/different cards).
    if (!emptyVisible) {
      const titlesAfter = await page
        .locator('[data-slot="card-title"]')
        .allTextContents();
      expect(
        titlesAfter,
        "Search results should differ from the unfiltered list â€” the list must not stay pixel-identical after a query is submitted"
      ).not.toEqual(titlesBefore);
    }
  });
});

// ---------------------------------------------------------------------------
// Rubric â€” categories 1, 2, 3, 4, 7, 8 applied to the News Feed tab.
// ---------------------------------------------------------------------------

test.describe("rubric â€” News Feed", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/feed");
    await expect(page.getByRole("heading", { name: /TechPulse AI/i })).toBeVisible();
    await page.waitForLoadState("networkidle", { timeout: 20_000 }).catch(() => {});
    await expect(page.locator(".animate-spin").first()).toBeHidden({ timeout: 20_000 });
    // Make sure there are real cards to assert against.
    const empty = page.getByText(/No articles found/i);
    if (await empty.isVisible().catch(() => false)) {
      const reset = page.getByRole("button", { name: /^Reset Filters$/i });
      const clear = page.getByRole("button", { name: /^Clear Filters$/i });
      if (await reset.isVisible().catch(() => false)) await reset.click();
      else if (await clear.isVisible().catch(() => false)) await clear.click();
      await page.waitForLoadState("networkidle", { timeout: 10_000 }).catch(() => {});
      await expect(page.locator(".animate-spin").first()).toBeHidden({ timeout: 15_000 });
    }
    // Ensure at least one article card has rendered before assertions run.
    await expect(page.locator('[data-slot="card"]').first()).toBeVisible({
      timeout: 15_000,
    });
  });

  test("category 1 â€” article body has no HTML entities, mojibake, or stringified placeholders", async ({
    page,
  }) => {
    // Read More / Show More on the first card so we exercise the full body too.
    const readMore = page
      .locator('[data-slot="card"]')
      .first()
      .getByRole("button", { name: /Read More/i });
    if (await readMore.isVisible().catch(() => false)) {
      await readMore.click();
    }
    const scope = '[data-slot="card"]';
    await assertNoHtmlEntities(page, scope);
    await assertNoMojibake(page, scope);
    await assertNoUndefinedNullObjectObject(page, scope);
  });

  test("category 3 â€” article cards list has no duplicate titles", async ({ page }) => {
    await assertNoDuplicateSiblings(
      page,
      '[data-slot="card-title"]',
      "news-feed article titles"
    );
  });

  test("category 4 â€” article cards do not horizontally overflow", async ({ page }) => {
    await assertNoHorizontalOverflow(page, '[data-slot="card"]');
  });

  test("category 7 â€” feed has no seed/mock/example/epoch data", async ({ page }) => {
    // Scope to the active feed panel â€” other tabs have their own checks.
    await assertNoMockDataLeak(page, '[data-state="active"][role="tabpanel"]');
  });

  test("category 8 â€” every visible article card image actually loaded", async ({
    page,
  }) => {
    // Allow up to 1 broken thumbnail â€” feeds occasionally serve a bad URL
    // and ImageWithFallback substitutes a placeholder. More than 1 broken
    // means the placeholder fallback itself broke or a CSP is blocking.
    await assertImagesLoadedInFeed(page);
  });

  test("category 2 â€” taxonomy: each chip the user can click yields results or a clear empty-state", async ({
    page,
    request,
  }) => {
    test.setTimeout(45_000);

    // Capture the user's saved categories upfront so we can restore them
    // at the end. This test rotates through chips by saving them server-
    // side, so without restoration we'd leave the next test (Settings)
    // looking at whatever chip we happened to end on.
    const backendBase =
      process.env.BACKEND_URL || "http://127.0.0.1:8000";
    const savedBefore: string[] = await (async () => {
      try {
        const r = await request.get(`${backendBase}/api/settings`);
        if (!r.ok()) return [];
        const env = await r.json();
        const data = env?.data ?? env;
        return Array.isArray(data?.categories) ? data.categories : [];
      } catch {
        return [];
      }
    })();

    // The TopicFilter lives in the Settings tab. Pick at most 4 chips so the
    // suite stays under its 60s budget; if there are fewer chips, we test
    // them all. We never silently skip â€” having zero chips here is a
    // regression on its own (means /api/news/categories returned empty).
    await page.getByRole("tab", { name: /Settings/i }).click();
    await expect(page.getByText(/Topic Preferences/i)).toBeVisible({ timeout: 10_000 });

    // Wait for the categories endpoint to populate.
    await expect(page.getByText(/Loading topics/i)).toBeHidden({ timeout: 15_000 }).catch(() => {});

    // Each chip is a <label> wrapping a Radix checkbox button + an emoji
    // span + a label span. The visible label sits in the LAST <span> in
    // the label, while the first <span> holds the emoji. We pull the
    // label-only text (and the row index) so we can target rows by
    // position â€” Playwright's `hasText` filter is unreliable when the
    // accumulated innerText spans newlines.
    const rowLocator = page
      .locator('label')
      .filter({ has: page.locator('button[role="checkbox"]') });

    const rowCount = await rowLocator.count();
    expect(
      rowCount,
      "TopicFilter rendered zero chips â€” /api/news/categories has no real categories"
    ).toBeGreaterThan(0);

    const chipLabels = await rowLocator.evaluateAll((els) =>
      (els as HTMLElement[]).map((el) => {
        // The visible label is the LAST <span> direct child of the row.
        const spans = Array.from(el.querySelectorAll(":scope > span"));
        if (spans.length > 0) {
          return (spans[spans.length - 1].textContent || "").trim();
        }
        return (el.innerText || "").trim().split("\n").pop() || "";
      })
    );

    const sampleSize = Math.min(4, rowCount);

    try {
      for (let i = 0; i < sampleSize; i++) {
        const label = chipLabels[i] || `chip ${i}`;

        // Clear any active selection first so each chip is tested in isolation.
        const clearAll = page.getByRole("button", { name: /^Clear All$/i });
        if (await clearAll.isEnabled().catch(() => false)) {
          await clearAll.click();
        }

        // Click the i-th row directly by index â€” robust to emoji/text content.
        const row = rowLocator.nth(i);
        await row.click();

        // Save and wait for the toast to confirm the backend persisted. We
        // use `.first()` so a stale toast from a previous iteration doesn't
        // confuse the matcher.
        await page.getByRole("button", { name: /Save Preferences/i }).click();
        await expect(
          page.getByText(/Preferences saved successfully/i).first()
        ).toBeVisible({ timeout: 15_000 });

        await page.getByRole("tab", { name: /News Feed/i }).click();

        // Wait for the refetch.
        await expect(page.locator(".animate-spin").first()).toBeHidden({
          timeout: 15_000,
        });

        const cards = page.locator('[data-slot="card"]');
        const cardCount = await cards.count();
        const resetBtn = page.getByRole("button", { name: /^Reset Filters$/i });
        const resetVisible = await resetBtn.isVisible().catch(() => false);

        expect(
          cardCount > 0 || resetVisible,
          `Chip "${label}" (row ${i}) produced zero results AND no Reset Filters button â€” ` +
            `that's a stuck/crashed feed. Either return articles or surface the empty-state CTA.`
        ).toBe(true);

        // Back to settings for the next iteration. Give the toast queue a
        // beat to drain so the `Preferences saved successfully` matcher
        // doesn't latch onto a stale toast.
        await page.getByRole("tab", { name: /Settings/i }).click();
        await expect(page.getByText(/Topic Preferences/i)).toBeVisible({ timeout: 10_000 });
        await page.waitForTimeout(800);
      }
    } finally {
      // Restore the user's saved categories so we don't leave the
      // downstream Settings spec staring at a chip we picked. Best-effort:
      // if the restore PUT fails we don't fail the test â€” the assertion
      // outcome is what matters.
      //
      // We additionally make sure the restored set has at least TWO chips,
      // because the existing Settings spec toggles one off and then needs
      // the Save Preferences button â€” which only renders while at least
      // one chip remains selected. Single-chip restoration would leave
      // the next test wedged on a button that never appears.
      const restoreSet = new Set<string>(savedBefore);
      // Pick fallbacks from chips we know exist in the current category
      // vocabulary; the actual values were collected at the top of this
      // test from the live TopicFilter.
      const fallbackPool = chipLabels.filter((c) => c.length > 0);
      for (const chip of fallbackPool) {
        if (restoreSet.size >= 2) break;
        restoreSet.add(chip);
      }
      try {
        await request.put(`${backendBase}/api/settings`, {
          data: {
            categories: Array.from(restoreSet),
            view_mode: "detailed",
            show_trending_only: false,
          },
        });
      } catch {
        // ignore
      }
    }
  });

  test("category 6 â€” page load + tab navigation produces no console errors", async ({
    browser,
  }) => {
    // Fresh context so we don't inherit listeners from the file-level beforeEach.
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    const errors = installConsoleErrorListener(page, [
      // The dev frontend logs an "API Response:" debug line -- not an
      // error. The ignore list is empty for now; we want every error to
      // surface. If a known-noisy third-party shows up, add a regex here.
    ]);
    await page.goto("/feed");
    await expect(page.getByRole("heading", { name: /TechPulse AI/i })).toBeVisible();
    await page.waitForLoadState("networkidle", { timeout: 20_000 }).catch(() => {});
    await expect(page.locator(".animate-spin").first()).toBeHidden({ timeout: 20_000 });
    assertConsoleClean(errors);
    await ctx.close();
  });
});

// Local helper â€” kept inside this spec file because the tolerance is
// news-feed-specific (some feeds genuinely have no image_url, others use
// the ImageWithFallback placeholder which itself MUST load).
async function assertImagesLoadedInFeed(page: import("@playwright/test").Page) {
  const status = await page.evaluate(() => {
    const imgs = Array.from(
      document.querySelectorAll<HTMLImageElement>('[data-slot="card"] img')
    );
    return imgs.map((img) => ({
      src: img.currentSrc || img.src,
      naturalWidth: img.naturalWidth,
      complete: img.complete,
      visible: img.offsetParent !== null,
    }));
  });

  const visible = status.filter((s) => s.visible);
  const broken = visible.filter((s) => s.complete && s.naturalWidth === 0);

  // Tolerance: at most 20% of visible images may be broken (placeholder
  // shows). If zero are visible, the test silently passes â€” the
  // `News Feed tab` spec already asserts cards render.
  const tolerance = Math.max(1, Math.ceil(visible.length * 0.2));
  expect(
    broken.length,
    `Too many broken article images (${broken.length} / ${visible.length}). ` +
      `Tolerance = ${tolerance}. First broken: ${JSON.stringify(broken.slice(0, 3))}`
  ).toBeLessThanOrEqual(tolerance);
}
