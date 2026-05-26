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

test.describe("mode toggle", () => {
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
