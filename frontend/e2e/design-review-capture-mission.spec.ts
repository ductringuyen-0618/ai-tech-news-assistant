/**
 * Mission-mode counterpart of design-review-capture.spec.ts.
 *
 * Captures full-page screenshots of every key route with Mission
 * Control as the active surface, so the design-review screenshot set
 * covers both modes. Screenshots land in
 * `.design/techpulse-frontend/screenshots/` with a `review-mission-`
 * prefix so they sit alongside the Atelier set without overwriting it.
 *
 * Mode is forced via `localStorage.techpulse_mode = "mission"` set in
 * an `addInitScript`, which runs BEFORE any page script. The inline
 * bootstrap in `index.html` reads that key and sets
 * `<html data-mode="mission">` synchronously, so the first paint is
 * already in Mission mode — no toggle click and no flash of Atelier.
 *
 * Run examples (from `frontend/`):
 *
 *   # All routes, all breakpoints
 *   npx playwright test e2e/design-review-capture-mission.spec.ts
 *
 *   # Desktop only (the canonical design-review target)
 *   npx playwright test e2e/design-review-capture-mission.spec.ts --grep "desktop-1280"
 *
 *   # Both modes back-to-back
 *   npx playwright test e2e/design-review-capture.spec.ts e2e/design-review-capture-mission.spec.ts --grep "desktop-1280"
 *
 * Closes the "A `--mode=mission` capture spec to round out the
 * screenshot set" follow-up in DESIGN_REVIEW.md §8.
 */
import { test } from "@playwright/test";
import * as path from "path";

const FRONTEND = "https://techpulse-ai-phi.vercel.app";

const SHOT_DIR = path.resolve(
  process.cwd(),
  "..",
  ".design",
  "techpulse-frontend",
  "screenshots"
);

const PAGES = [
  { slug: "welcome", path: "/" },
  { slug: "feed", path: "/feed" },
  { slug: "research", path: "/research" },
  { slug: "knowledge", path: "/knowledge" },
  { slug: "digest", path: "/digest" },
  { slug: "saved", path: "/saved" },
];

const BREAKPOINTS = [
  { label: "mobile-375", width: 375, height: 812 },
  { label: "tablet-768", width: 768, height: 1024 },
  { label: "desktop-1280", width: 1280, height: 800 },
];

test.describe.configure({ mode: "serial" });

test.describe("design review capture — mission mode", () => {
  // Seed localStorage so the inline bootstrap in index.html picks up
  // "mission" on first paint. Runs in every new page context before
  // any document scripts. The origin must match the page we'll visit.
  test.beforeEach(async ({ context }) => {
    await context.addInitScript(() => {
      try {
        window.localStorage.setItem("techpulse_mode", "mission");
      } catch {
        /* privacy mode — fall through; the spec will still navigate */
      }
    });
  });

  for (const page of PAGES) {
    for (const bp of BREAKPOINTS) {
      test(`${page.slug} @ ${bp.label}`, async ({ page: pw }) => {
        test.setTimeout(60_000);
        await pw.setViewportSize({ width: bp.width, height: bp.height });
        await pw.goto(`${FRONTEND}${page.path}`, {
          waitUntil: "domcontentloaded",
          timeout: 30_000,
        });
        await pw.waitForLoadState("networkidle", { timeout: 10_000 }).catch(() => {});
        // Defense-in-depth — if for any reason the bootstrap didn't pick
        // up the localStorage value (e.g. the host wipes storage between
        // the init script and document load), force the attribute now.
        // This is a no-op in the happy path.
        await pw.evaluate(() => {
          if (document.documentElement.getAttribute("data-mode") !== "mission") {
            document.documentElement.setAttribute("data-mode", "mission");
          }
        });
        await pw.waitForTimeout(1500);
        const outPath = path.join(
          SHOT_DIR,
          `review-mission-${page.slug}-${bp.label}.png`
        );
        await pw.screenshot({ path: outPath, fullPage: true });
        console.log(`Saved ${outPath}`);
      });
    }
  }
});
