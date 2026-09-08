/**
 * mode-toggle.spec.ts — REDESIGN Phase F.
 *
 * Covers the Atelier ↔ Mission Control toggle contract added in Phase B.
 *
 * Acceptance:
 *   - Toggle is visible on every route inside the masthead.
 *   - Default state is "atelier" on a fresh browser context.
 *   - Clicking "Mission" sets <html data-mode="mission"> and writes
 *     localStorage.techpulse_mode = "mission".
 *   - The choice survives a reload.
 *   - Clicking "Atelier" flips back.
 *   - aria-pressed reflects the active pill.
 */
import { test, expect } from "@playwright/test";

// FOLLOW-UP (2026-09-07, updated): the Atelier/Mission merge into
// UnifiedFeedView's `density` prop already landed (App.tsx now derives
// feed density from `viewMode`, not from this toggle's `mode` state).
// An earlier pass here skipped this spec expecting that merge as a
// future event and assumed the underlying <ModeToggle/> component
// itself would need updated selectors -- in fact ModeToggle/ModeProvider
// were entirely unchanged and would have kept passing this exact spec,
// they just became orphaned: still rendered in the masthead, still
// writing `<html data-mode>` / `localStorage.techpulse_mode`, but
// nothing read either anymore. That's now fixed by removing
// `<ModeToggle />` (and the now-unused `<ModeProvider>` wrapper) from
// App.tsx rather than leaving dead, clickable-but-inert UI in
// production. This spec covers a masthead control that no longer
// exists, so it stays skipped (not un-skipped, not deleted -- keeping
// the coverage intent documented in case a similar toggle returns).
// Real coverage for the density toggle lives in settings.spec.ts.
test.describe.skip("mode toggle", () => {
  test("defaults to atelier on a fresh context", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    const html = page.locator("html");
    await expect(html).toHaveAttribute("data-mode", "atelier");

    const toggle = page.getByTestId("mode-toggle");
    await expect(toggle).toBeVisible();

    const atelier = page.getByTestId("mode-toggle-atelier");
    const mission = page.getByTestId("mode-toggle-mission");
    await expect(atelier).toHaveAttribute("aria-pressed", "true");
    await expect(mission).toHaveAttribute("aria-pressed", "false");
  });

  test("clicking Mission flips data-mode + persists to localStorage", async ({ page }) => {
    await page.goto("/feed", { waitUntil: "domcontentloaded" });
    await page.getByTestId("mode-toggle-mission").click();

    const html = page.locator("html");
    await expect(html).toHaveAttribute("data-mode", "mission");
    const stored = await page.evaluate(() => localStorage.getItem("techpulse_mode"));
    expect(stored).toBe("mission");
    await expect(page.getByTestId("mode-toggle-mission")).toHaveAttribute(
      "aria-pressed",
      "true"
    );
  });

  test("mission choice survives a reload", async ({ page }) => {
    await page.goto("/feed", { waitUntil: "domcontentloaded" });
    await page.getByTestId("mode-toggle-mission").click();
    await page.reload({ waitUntil: "domcontentloaded" });
    await expect(page.locator("html")).toHaveAttribute("data-mode", "mission");
  });

  test("clicking Atelier flips back", async ({ page }) => {
    await page.goto("/feed", { waitUntil: "domcontentloaded" });
    await page.getByTestId("mode-toggle-mission").click();
    await page.getByTestId("mode-toggle-atelier").click();
    await expect(page.locator("html")).toHaveAttribute("data-mode", "atelier");
    const stored = await page.evaluate(() => localStorage.getItem("techpulse_mode"));
    expect(stored).toBe("atelier");
  });
});
