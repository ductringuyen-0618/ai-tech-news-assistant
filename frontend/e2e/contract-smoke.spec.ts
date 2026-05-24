import { test, expect } from "@playwright/test";
import {
  installConsoleErrorListener,
  assertConsoleClean,
} from "./_lib/rubric";

/**
 * Contract smoke — the bare-minimum end-to-end checks that pin the
 * documented frontend public surface.
 *
 * Source of truth for what this test asserts:
 *   - docs/designs/frontend-overhaul.md §5 line 222 enumerates the
 *     six navigation labels that MUST resolve via
 *     `getByRole("tab", { name })`:
 *       News Feed, Research, Knowledge, Digest, Saved, Settings
 *   - The same doc, §5 step 1, pins the masthead heading whose
 *     accessible name matches /TechPulse AI/i (`aria-label` trick).
 *   - The user-testing rubric (e2e/_lib/rubric.ts category 6) defines
 *     "console hygiene": no `console.error` / `pageerror` during the
 *     first paint of the application shell.
 *
 * Why a separate smoke spec when sidebar.spec.ts already covers some
 * of this:
 *   - sidebar.spec.ts is a milestone-tied behavior spec (theme toggle,
 *     palette, arrow-key navigation) — when M1 ships a chrome
 *     rewrite, a small subset of its assertions becomes legitimately
 *     at-risk. THIS file is the un-killable contract floor: if any
 *     assertion here fails, the documented public surface of the app
 *     is broken, full stop.
 *   - The file lives outside any `describe` group so a failure shows
 *     up at the very top of the report.
 */

// Mirrors §5 line 222 of the design doc. The order is the documented
// reading order in the design doc's test-pinning list. "Saved" is
// passed as an exact string because "Saved" is a substring of the
// Settings tab's "Unsaved changes" badge — same disambiguation as
// sidebar.spec.ts.
const DOCUMENTED_NAV_LABELS: Array<{
  matcher: RegExp | string;
  exact?: boolean;
}> = [
  { matcher: /News Feed/i },
  { matcher: /Research/i },
  { matcher: /Knowledge/i },
  { matcher: /Digest/i },
  { matcher: "Saved", exact: true },
  { matcher: /Settings/i },
];

test.describe("Contract smoke — documented public surface", () => {
  test("app shell loads at base URL with TechPulse masthead", async ({
    page,
  }) => {
    // Install BEFORE goto so console errors emitted during initial
    // render are captured. Per rubric.ts contract.
    const errors = installConsoleErrorListener(page, [
      // Ignore favicon 404s — not application errors. Many dev setups
      // 404 the favicon and that has nothing to do with the contract.
      /favicon/i,
    ]);

    await page.goto("/");

    // The masthead heading is the documented "this is TechPulse"
    // oracle (frontend-overhaul.md §5 step 1 — aria-label trick on
    // the editorial <h1>).
    await expect(
      page.getByRole("heading", { name: /TechPulse AI/i })
    ).toBeVisible({ timeout: 15_000 });

    // Console must be clean on first paint.
    assertConsoleClean(errors);
  });

  test("all six documented nav items are present in the tablist", async ({
    page,
  }) => {
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: /TechPulse AI/i })
    ).toBeVisible({ timeout: 15_000 });

    // The Radix Tabs primitive renders one role="tablist" container.
    // Design doc §5 explicitly commits to keeping this primitive.
    const tablist = page.getByRole("tablist");
    await expect(tablist).toBeVisible();

    // Each documented nav label MUST resolve as a tab by accessible
    // name — this is the universal contract every existing test relies
    // on (sidebar.spec.ts:43-57 and 34 others).
    for (const { matcher, exact } of DOCUMENTED_NAV_LABELS) {
      const tab = page.getByRole("tab", {
        name: matcher as RegExp,
        exact,
      });
      await expect(
        tab,
        `Documented nav tab "${matcher}" must be a reachable role="tab"`
      ).toBeVisible();
    }

    // Frontend-overhaul.md §11 question 1 (resolved) keeps the count
    // at six. A new tab would be a feature decision worth surfacing,
    // not a silent drift, so we pin the floor.
    const tabCount = await page.getByRole("tab").count();
    expect(
      tabCount,
      "App should expose at least the six documented nav tabs"
    ).toBeGreaterThanOrEqual(6);
  });

  test("theme-toggle affordance is present in the sidebar chrome", async ({
    page,
  }) => {
    // Design doc §5 step 2 (bottom of sidebar): the theme toggle
    // keeps `data-testid="theme-toggle"`. Pinning it here means a
    // chrome refactor that drops the testid trips this contract
    // BEFORE we lose the user's ability to switch theme.
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: /TechPulse AI/i })
    ).toBeVisible({ timeout: 15_000 });

    const toggle = page.getByTestId("theme-toggle");
    await expect(
      toggle,
      'data-testid="theme-toggle" must be present in the sidebar'
    ).toBeVisible();
  });
});
