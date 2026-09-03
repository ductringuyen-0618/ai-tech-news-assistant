import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright config for the TechPulse AI behavior-test suite.
 *
 * Tests run against the already-running dev stack:
 *   - frontend at http://localhost:3000
 *   - backend at http://127.0.0.1:8000
 *   - Ollama at http://localhost:11434 (only used by `*.live.spec.ts`)
 *
 * Default `npx playwright test` runs the deterministic suite.
 *
 * To make the recorded videos *watchable by a human*, every user action
 * is throttled by SLOW_MO (default 600ms). Override per-run:
 *   PLAYWRIGHT_SLOW_MO=0    — fast CI mode
 *   PLAYWRIGHT_SLOW_MO=1200 — slow demo mode
 *
 * Live integration spec (Ollama-dependent):
 *   npx playwright test research.live.spec.ts --grep @live
 */
const SLOW_MO = process.env.PLAYWRIGHT_SLOW_MO !== undefined
  ? Number(process.env.PLAYWRIGHT_SLOW_MO)
  : 600;

// Write artifacts outside OneDrive so the sync client doesn't churn on every
// video/screenshot/trace. The project lives under ~/OneDrive/... and Playwright
// can write ~5 files/sec during a run.
const ARTIFACT_ROOT = "C:/temp/playwright-tech-news";

export default defineConfig({
  testDir: "./e2e",
  testIgnore: ["**/*.live.spec.ts"],
  // Watching a video is the verification — bump per-test budget so the
  // pacing pauses don't blow the default 60s.
  timeout: 120_000,
  fullyParallel: false,
  workers: 1,
  outputDir: `${ARTIFACT_ROOT}/test-results`,
  reporter: [["list"], ["html", { open: "never", outputFolder: `${ARTIFACT_ROOT}/playwright-report` }]],
  use: {
    // Overridable so verify.ps1 can point the suite at a non-default
    // frontend port (e.g. when 3000 is already taken by something outside
    // this repo) without touching this file.
    baseURL: process.env.PLAYWRIGHT_BASE_URL || "http://localhost:3000",
    headless: false,
    video: "on",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
    viewport: { width: 1440, height: 900 },
    actionTimeout: 20_000,
    launchOptions: {
      slowMo: SLOW_MO,
    },
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
});
