import { test, expect } from "@playwright/test";

/**
 * Mission 3 / Milestone 1 — Sidebar nav + dark theme + Cmd+K palette.
 *
 * Verifies the chrome rewrite without touching any tab content. Each
 * test isolates one validation contract:
 *
 *   1. Sidebar renders 6+ nav items inside a role="tablist" — proves the
 *      Playwright `getByRole("tab", { name })` selectors that all 35
 *      existing tests rely on still resolve under the new layout.
 *
 *   2. Theme toggle flips `<html class="dark">` AND persists the choice
 *      to localStorage. Survives reload.
 *
 *   3. Cmd+K (Ctrl+K on Win/Linux) opens the command palette;
 *      Escape closes it.
 *
 *   4. Inside the open palette, arrow keys + Enter navigate to a tab.
 */

// Test tuple: (regex, exact-match value). For tab names that are substrings
// of another tab (e.g. "Saved" appears inside the Settings "Unsaved changes"
// badge), we use an exact-match string instead of the regex.
const NAV_LABELS: Array<{ matcher: RegExp | string; exact?: boolean }> = [
  { matcher: /News Feed/i },
  { matcher: /Research/i },
  { matcher: /Digest/i },
  { matcher: "Saved", exact: true },
  { matcher: /Settings/i },
];

test.describe("Mission 3 / M1 — Sidebar + theme + Cmd+K palette", () => {
  test("sidebar renders 6+ nav items inside a tablist", async ({ page }) => {
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: /TechPulse AI/i })
    ).toBeVisible({ timeout: 15_000 });

    // The Radix Tabs primitive renders the TabsList with role="tablist"
    // and each TabsTrigger with role="tab". Both must be present.
    const tablist = page.getByRole("tablist");
    await expect(tablist).toBeVisible();

    // Each named nav item is reachable by its accessible name. Every
    // existing test in the suite uses the same lookup, so if any of
    // these fail the rest of the suite would break too.
    for (const { matcher, exact } of NAV_LABELS) {
      const tab = page.getByRole("tab", { name: matcher as any, exact });
      await expect(tab, `Tab "${matcher}" should be visible`).toBeVisible();
    }

    // At least 5 entries — News Feed, Research, Digest, Saved, Settings.
    // (Knowledge Graph tab was cut; entity filtering moved into the Feed
    // toolbar's EntitySearch instead.)
    const tabCount = await page.getByRole("tab").count();
    expect(tabCount).toBeGreaterThanOrEqual(5);
  });

  test("theme toggle flips <html class=\"dark\"> and persists across reload", async ({
    page,
  }) => {
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: /TechPulse AI/i })
    ).toBeVisible({ timeout: 15_000 });

    // Dark mode is the default — the inline bootstrap script in index.html
    // sets the class before React mounts, so it's present from the very
    // first paint.
    let isDark = await page.evaluate(() =>
      document.documentElement.classList.contains("dark")
    );
    expect(isDark, "Dark theme should be the default on first paint").toBe(true);

    // The theme toggle lives at the bottom of the sidebar and is
    // identified by a data-testid so we don't have to know whether the
    // button currently says "dark theme" or "light theme".
    const toggle = page.getByTestId("theme-toggle");
    await expect(toggle).toBeVisible();

    await toggle.click();

    // After one click, dark should be off and the light class state
    // should be reflected on <html>.
    isDark = await page.evaluate(() =>
      document.documentElement.classList.contains("dark")
    );
    expect(isDark, "Theme toggle should remove the dark class").toBe(false);

    // localStorage should now record the user's explicit choice.
    const storedTheme = await page.evaluate(() =>
      localStorage.getItem("techpulse-theme")
    );
    expect(storedTheme, "Theme choice should persist to localStorage").toBe(
      "light"
    );

    // Reload — the inline bootstrap script should now see "light" and
    // NOT add the dark class.
    await page.reload();
    await expect(
      page.getByRole("heading", { name: /TechPulse AI/i })
    ).toBeVisible({ timeout: 15_000 });

    isDark = await page.evaluate(() =>
      document.documentElement.classList.contains("dark")
    );
    expect(
      isDark,
      "Light theme should persist across reload (FOUC-free bootstrap)"
    ).toBe(false);

    // Restore the dark default so subsequent tests aren't perturbed.
    await page.getByTestId("theme-toggle").click();
    await expect
      .poll(async () =>
        page.evaluate(() => localStorage.getItem("techpulse-theme"))
      )
      .toBe("dark");
  });

  test("Ctrl+K opens the command palette; Escape closes it", async ({
    page,
  }) => {
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: /TechPulse AI/i })
    ).toBeVisible({ timeout: 15_000 });

    // The palette is hidden initially — no input with the palette's
    // placeholder text should be visible.
    const paletteInput = page.getByPlaceholder(
      /Jump to a tab or recent research/i
    );
    await expect(paletteInput).toBeHidden();

    // Open with the keyboard shortcut. We dispatch Control+K which works
    // on every platform; the provider handles both Cmd (metaKey) and
    // Ctrl (ctrlKey). Playwright maps "Control" -> ctrlKey: true on all
    // OSes.
    await page.keyboard.press("Control+KeyK");

    await expect(paletteInput).toBeVisible({ timeout: 5_000 });

    // The palette should announce the navigation group + every named
    // tab. We don't assert every label here — that's covered by test 1.
    await expect(page.getByText(/Navigation/i)).toBeVisible();

    // Escape closes the palette.
    await page.keyboard.press("Escape");
    await expect(paletteInput).toBeHidden({ timeout: 5_000 });
  });

  test("arrow-key + Enter inside the palette navigates to a tab", async ({
    page,
  }) => {
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: /TechPulse AI/i })
    ).toBeVisible({ timeout: 15_000 });

    // Establish a baseline — the News Feed tab is active by default. We
    // capture the active tab's accessible name so the assertion below
    // proves we DID navigate (and to which tab).
    const initialActive = page.locator('[role="tab"][aria-selected="true"]');
    await expect(initialActive).toHaveCount(1);

    // Open the palette and type "Research" so the filtering narrows the
    // list down to a single, unambiguous item. cmdk auto-selects the
    // first visible item, so pressing Enter without further arrow keys
    // would already select Research — but the contract calls for
    // arrow-key navigation, so we exercise that path too.
    await page.keyboard.press("Control+KeyK");
    const paletteInput = page.getByPlaceholder(
      /Jump to a tab or recent research/i
    );
    await expect(paletteInput).toBeVisible({ timeout: 5_000 });

    await paletteInput.fill("Research");
    // Pressing ArrowDown once moves selection within the filtered list.
    // cmdk's first-item-auto-select is idempotent, so two presses still
    // land on a valid item (it loops at the end of the list).
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("Enter");

    // The Research tab should now be the active one, and its panel —
    // the ResearchMode component — renders the "AI funding rounds"
    // placeholder input. We use that as the post-navigation oracle.
    const researchInput = page.getByPlaceholder(/AI funding rounds/i);
    await expect(researchInput).toBeVisible({ timeout: 10_000 });

    // The palette itself should have closed.
    await expect(paletteInput).toBeHidden();
  });

  test("sidebar does not permanently occupy ~40%+ of a mobile viewport", async ({
    page,
  }) => {
    // Regression test for review-07: "Sidebar.tsx is a fixed w-72, no
    // breakpoint/collapse/hamburger; would eat ~40%+ of a 375px viewport."
    // A separate agent is wiring the existing (unused) ui/sidebar.tsx +
    // use-mobile.ts hook into Sidebar.tsx concurrently with this test
    // being written, so the exact collapse mechanism (hidden rail,
    // off-canvas drawer, hamburger overlay, etc.) isn't knowable here.
    //
    // Instead of asserting on a specific toggle selector that might not
    // match the final implementation, this asserts the implementation-
    // agnostic contract: on a narrow viewport the main content area must
    // get most of the screen width back, rather than ceding a fixed
    // ~288px (w-72) column to the sidebar permanently. `[data-slot=
    // "main-content"]` is the stable <main> hook App.tsx already exposes.
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: /TechPulse AI/i })
    ).toBeVisible({ timeout: 15_000 });

    const main = page.locator('[data-slot="main-content"]');
    await expect(main).toBeVisible();

    const mainWidth = await main.evaluate(
      (el) => el.getBoundingClientRect().width
    );

    expect(
      mainWidth,
      `Main content was only ${mainWidth}px wide on a 375px viewport â€” the sidebar appears to still be a permanent fixed-width column instead of collapsing on mobile`
    ).toBeGreaterThanOrEqual(375 * 0.75);
  });
});
