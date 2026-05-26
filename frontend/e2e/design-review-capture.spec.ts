/**
 * Capture full-page screenshots of every key route across mobile / tablet /
 * desktop breakpoints, for the design-review skill. Saves into
 * `.design/techpulse-frontend/screenshots/`.
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

test.describe("design review capture", () => {
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
        await pw.waitForTimeout(1500);
        const outPath = path.join(SHOT_DIR, `review-${page.slug}-${bp.label}.png`);
        await pw.screenshot({ path: outPath, fullPage: true });
        console.log(`Saved ${outPath}`);
      });
    }
  }
});