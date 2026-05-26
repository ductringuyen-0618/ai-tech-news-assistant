/**
 * Single-shot capture for the light-mode masthead chip review
 * (design-review #8). Toggles the theme to light via the
 * ``[ LIGHT ]`` pill in the sidebar then crops the masthead row.
 */
import { test } from "@playwright/test";
import * as path from "path";

const FRONTEND = "https://techpulse-ai-phi.vercel.app";

test("light-mode masthead chips at 1280px", async ({ page }) => {
  test.setTimeout(60_000);
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto(`${FRONTEND}/feed`, { waitUntil: "domcontentloaded", timeout: 30_000 });
  await page.waitForLoadState("networkidle", { timeout: 10_000 }).catch(() => {});
  await page.waitForTimeout(1500);

  // Toggle to light mode.
  await page
    .getByTestId("theme-toggle")
    .click({ timeout: 5_000 })
    .catch(() => {});
  await page.waitForTimeout(500);

  const outPath = path.resolve(
    process.cwd(),
    "..",
    ".design",
    "techpulse-frontend",
    "screenshots",
    "review-light-masthead-1280.png"
  );
  await page.screenshot({
    path: outPath,
    clip: { x: 0, y: 0, width: 1280, height: 180 },
  });
  console.log(`Saved ${outPath}`);
});
