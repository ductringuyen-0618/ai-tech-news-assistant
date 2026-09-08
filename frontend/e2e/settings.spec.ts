import { test, expect } from "@playwright/test";

/**
 * Settings tab - asserts category preferences persist across page reload,
 * proving the backend write actually happened (not just optimistic UI).
 *
 * Uses "Hardware" as the toggle target because the chip list is now
 * dynamically derived from /api/news/categories (the union of category
 * tags actually present in the article DB), so the previous "Robotics"
 * choice would not appear unless an ingested feed maps to it. "Hardware"
 * matches the Ars Technica feed mapping in IngestionService.DEFAULT_FEEDS
 * and is reliably present.
 */

const TARGET_CATEGORY = "Hardware";

test.describe("Settings tab", () => {
  test("toggling a category and saving persists across reload", async ({ page }) => {
    test.setTimeout(60_000);

    await page.goto("/");
    await expect(page.getByRole("heading", { name: /TechPulse AI/i })).toBeVisible();

    // Switch to the Settings tab.
    await page.getByRole("tab", { name: /Settings/i }).click();

    // Wait for the topic-preferences card to render.
    await expect(page.getByText(/Topic Preferences/i)).toBeVisible({
      timeout: 10_000,
    });

    // Find the Robotics row. It's a <label> wrapping a Checkbox + text.
    const robotRow = page.locator("label").filter({ hasText: TARGET_CATEGORY });
    await expect(robotRow).toBeVisible();

    // Read its current state (was it already selected?).
    const checkbox = robotRow.locator('button[role="checkbox"]');
    const initialState = await checkbox.getAttribute("aria-checked");
    const wasChecked = initialState === "true";

    // Toggle it (click) - we want to flip and verify the FLIPPED state
    // persists after reload. That proves the backend wrote the new value.
    if (wasChecked) {
      // Toggle off, save, reload - assert it's off after reload.
      await checkbox.click();
      await page.getByRole("button", { name: /Save Preferences/i }).click();
      await expect(
        page.getByText(/Preferences saved successfully/i)
      ).toBeVisible({ timeout: 10_000 });

      await page.reload();
      await page.getByRole("tab", { name: /Settings/i }).click();
      await expect(page.getByText(/Topic Preferences/i)).toBeVisible({
        timeout: 10_000,
      });

      const reloadedRow = page.locator("label").filter({ hasText: TARGET_CATEGORY });
      const reloadedState = await reloadedRow
        .locator('button[role="checkbox"]')
        .getAttribute("aria-checked");
      expect(
        reloadedState,
        `${TARGET_CATEGORY} should have persisted as unchecked after reload`
      ).toBe("false");

      // Restore: toggle it back on so subsequent tests find the original
      // state. (Not strictly required - tests are independent - but it's
      // courteous when sharing a real backend.)
      await reloadedRow.locator('button[role="checkbox"]').click();
      await page.getByRole("button", { name: /Save Preferences/i }).click();
    } else {
      // Standard path: toggle on, save, reload, expect still on.
      await checkbox.click();
      await expect(checkbox).toHaveAttribute("aria-checked", "true");

      await page.getByRole("button", { name: /Save Preferences/i }).click();
      await expect(
        page.getByText(/Preferences saved successfully/i)
      ).toBeVisible({ timeout: 10_000 });

      await page.reload();
      await expect(page.getByRole("heading", { name: /TechPulse AI/i })).toBeVisible();

      await page.getByRole("tab", { name: /Settings/i }).click();
      await expect(page.getByText(/Topic Preferences/i)).toBeVisible({
        timeout: 10_000,
      });

      const reloadedRow = page.locator("label").filter({ hasText: TARGET_CATEGORY });
      const reloadedState = await reloadedRow
        .locator('button[role="checkbox"]')
        .getAttribute("aria-checked");
      expect(
        reloadedState,
        `${TARGET_CATEGORY} should still be selected after reload - proves backend persistence`
      ).toBe("true");
    }
  });
});

// ---------------------------------------------------------------------------
// Rubric — category 5 (state persistence) applied to Settings.
//
// The strongest persistence test: open a SECOND browser context with no
// shared cookies/localStorage and verify the toggle is still set. If the
// app stored the value only in localStorage, the second context would
// see the default instead, and this test would fail.
// ---------------------------------------------------------------------------

const FRESH_CONTEXT_TARGET = "Hardware";

test.describe("rubric — Settings persistence (category 5)", () => {
  test("category 5 — saved category survives a fresh browser context (server-side, not localStorage)", async ({
    browser,
    request,
  }) => {
    test.setTimeout(60_000);

    const backendBase = process.env.BACKEND_URL || "http://127.0.0.1:8000";

    // Capture initial settings so we can restore them after the test, and
    // seed a baseline that GUARANTEES Hardware is NOT selected. Starting
    // from a known state lets us prove "click → check → save" works
    // regardless of what previous tests left behind.
    const initialSettings = await (async () => {
      try {
        const r = await request.get(`${backendBase}/api/settings`);
        if (!r.ok()) return null;
        const env = await r.json();
        return env?.data ?? env;
      } catch {
        return null;
      }
    })();

    await request.put(`${backendBase}/api/settings`, {
      data: {
        // Seed a non-empty baseline that does NOT include Hardware so the
        // test can flip it to checked and the Save button is reachable.
        categories: ["AI/ML"],
        view_mode: "detailed",
        show_trending_only: false,
      },
    });

    try {
      // ---- Stage 1: in context A, check Hardware and save --------------
      const ctxA = await browser.newContext();
      const pageA = await ctxA.newPage();
      await pageA.goto("/");
      await expect(pageA.getByRole("heading", { name: /TechPulse AI/i })).toBeVisible();
      await pageA.getByRole("tab", { name: /Settings/i }).click();
      await expect(pageA.getByText(/Topic Preferences/i)).toBeVisible({
        timeout: 10_000,
      });

      const rowA = pageA.locator("label").filter({ hasText: FRESH_CONTEXT_TARGET });
      await expect(rowA).toBeVisible({ timeout: 10_000 });
      const checkboxA = rowA.locator('button[role="checkbox"]');

      // We seeded Hardware as NOT selected. Confirm and then check it.
      await expect(checkboxA).toHaveAttribute("aria-checked", "false");
      await checkboxA.click();
      await expect(checkboxA).toHaveAttribute("aria-checked", "true");

      await pageA.getByRole("button", { name: /Save Preferences/i }).click();
      await expect(pageA.getByText(/Preferences saved successfully/i)).toBeVisible({
        timeout: 15_000,
      });
      const endStateInA = "true";

      await ctxA.close();

      // ---- Stage 2: in context B (fresh storage), reload and verify ----
      const ctxB = await browser.newContext();
      const pageB = await ctxB.newPage();

      // Sanity check: localStorage should be empty in this context. If the
      // app is reading from localStorage, the toggle will revert to the
      // default — which is what category 5 requires us to detect.
      const lsLength = await pageB.evaluate(() => {
        try {
          return window.localStorage.length;
        } catch {
          return -1;
        }
      });
      expect(
        lsLength,
        "Fresh browser context unexpectedly has localStorage entries — test setup wrong"
      ).toBeLessThanOrEqual(0);

      await pageB.goto("/");
      await expect(pageB.getByRole("heading", { name: /TechPulse AI/i })).toBeVisible();
      await pageB.getByRole("tab", { name: /Settings/i }).click();
      await expect(pageB.getByText(/Topic Preferences/i)).toBeVisible({
        timeout: 10_000,
      });

      const rowB = pageB.locator("label").filter({ hasText: FRESH_CONTEXT_TARGET });
      await expect(rowB).toBeVisible({ timeout: 10_000 });
      const checkboxB = rowB.locator('button[role="checkbox"]');
      const stateInB = await checkboxB.getAttribute("aria-checked");

      expect(
        stateInB,
        `${FRESH_CONTEXT_TARGET} state did NOT persist across a fresh browser context. ` +
          `Saved "${endStateInA}" in context A, but context B (no cookies, no localStorage) ` +
          `sees "${stateInB}". This means the value lives in localStorage, not on the server — ` +
          `category 5 violation.`
      ).toBe(endStateInA);

      await ctxB.close();
    } finally {
      // Restore the original settings so the next test run sees the same
      // initial state the user expected. Best-effort.
      if (initialSettings && Array.isArray(initialSettings.categories)) {
        try {
          await request.put(`${backendBase}/api/settings`, {
            data: {
              categories: initialSettings.categories,
              view_mode: initialSettings.view_mode || "detailed",
              show_trending_only: !!initialSettings.show_trending_only,
            },
          });
        } catch {
          // ignore
        }
      }
    }
  });
});

// ---------------------------------------------------------------------------
// M3.M4 � Theme toggle in Settings flips the <html class="dark"> attribute.
// Asserts:
//   1. Settings tab renders Appearance card with Dark / Light radios.
//   2. Clicking Light removes the `dark` class from <html>.
//   3. Clicking Dark adds it back. Both writes persist to localStorage.
// ---------------------------------------------------------------------------

test.describe("M3.M4 � Settings theme toggle", () => {
  test("dark/light radios in Appearance card flip <html class='dark'> and persist", async ({
    page,
  }) => {
    test.setTimeout(45_000);

    await page.goto("/");
    await expect(page.getByRole("heading", { name: /TechPulse AI/i })).toBeVisible();

    // Switch to the Settings tab.
    await page.getByRole("tab", { name: /Settings/i }).click();

    // Appearance card should be visible.
    await expect(page.getByText(/^Appearance$/i)).toBeVisible({ timeout: 10_000 });

    // Force a known starting state � pick Dark explicitly.
    await page.getByTestId("settings-theme-dark").click();
    await expect
      .poll(async () =>
        page.evaluate(() => document.documentElement.classList.contains("dark"))
      )
      .toBe(true);

    // Pick Light � html should drop the dark class.
    await page.getByTestId("settings-theme-light").click();
    await expect
      .poll(async () =>
        page.evaluate(() => document.documentElement.classList.contains("dark"))
      )
      .toBe(false);

    // Reload � light should persist via localStorage.
    await page.reload();
    await expect(page.getByRole("heading", { name: /TechPulse AI/i })).toBeVisible();
    const stillLight = await page.evaluate(() =>
      document.documentElement.classList.contains("dark")
    );
    expect(stillLight, "Theme should have persisted as light after reload").toBe(false);

    // Restore to dark so other tests start in the standard state.
    await page.getByRole("tab", { name: /Settings/i }).click();
    await page.getByTestId("settings-theme-dark").click();
    await expect
      .poll(async () =>
        page.evaluate(() => document.documentElement.classList.contains("dark"))
      )
      .toBe(true);
  });

  test("density radio writes localStorage.techpulse-density but does not change html attrs", async ({
    page,
  }) => {
    test.setTimeout(30_000);

    await page.goto("/");
    await expect(page.getByRole("heading", { name: /TechPulse AI/i })).toBeVisible();
    await page.getByRole("tab", { name: /Settings/i }).click();
    await expect(page.getByText(/^Appearance$/i)).toBeVisible({ timeout: 10_000 });

    await page.getByTestId("settings-density-compact").click();
    const stored = await page.evaluate(() =>
      localStorage.getItem("techpulse-density")
    );
    expect(stored).toBe("compact");

    await page.getByTestId("settings-density-comfortable").click();
    const stored2 = await page.evaluate(() =>
      localStorage.getItem("techpulse-density")
    );
    expect(stored2).toBe("comfortable");

    // Density is now live (read by UnifiedFeedView.tsx), so it is also
    // written to the newer preference key alongside the legacy one.
    const preference = await page.evaluate(() =>
      localStorage.getItem("techpulse-density-preference")
    );
    expect(preference).toBe("comfortable");
  });
});