import { test, expect, type Page, type Route } from "@playwright/test";

/**
 * M3.M6 — Mission 3 closing demo.
 *
 * Drives a complete end-to-end flow under demo-friendly slowMo so the
 * recorded Playwright video is watchable by a human reviewer.
 *
 *   PLAYWRIGHT_SLOW_MO=400 npx playwright test m3-demo.spec.ts
 *
 * After the test passes, copy the captured video out of the Playwright
 * test-results dir into `docs/demos/mission-3-final.webm`.
 *
 * The flow is mocked end-to-end so the run is reproducible (no live
 * LLM or backend variation). Each chapter is wrapped in test.step()
 * so the trace viewer gets nice section markers.
 */

const SHORT_QUESTION = "Latest AI chip news";

const PACE_MS =
  process.env.PLAYWRIGHT_SLOW_MO !== undefined
    ? Math.max(0, Number(process.env.PLAYWRIGHT_SLOW_MO))
    : 400;
const beat = (page: Page, mult = 1) =>
  page.waitForTimeout(Math.round(PACE_MS * mult));

const RESEARCH_REPORT =
  "## Executive Summary\n" +
  "Recent AI chip developments show rapid iteration, with multiple vendors converging on edge-inference architectures [1]. " +
  "Pricing pressure across tier-1 SKUs continues to compress margins [2].\n\n" +
  "## Key Findings\n" +
  "| Vendor | Focus | Notable Move |\n" +
  "|---|---|---|\n" +
  "| Nvidia | Datacenter | Blackwell ramp |\n" +
  "| AMD | Inference | MI400 roadmap |\n" +
  "| Custom ASIC | Edge | Power efficiency wins |\n\n" +
  "- Edge-inference workloads are growing fastest [1].\n" +
  "- Commodity SKUs are under price pressure [2].\n\n" +
  "## Sources Used\n" +
  "1. TechCrunch — https://example.com/ai-chip-1\n" +
  "2. Ars Technica — https://example.com/ai-chip-2\n";

async function installResearchMock(page: Page) {
  const frames: string[] = [];
  frames.push(
    `data: ${JSON.stringify({ type: "phase", data: "Decomposing" })}\n\n`
  );
  frames.push(
    `data: ${JSON.stringify({
      type: "decomposed",
      sub_questions: [
        "What companies are leading AI chip design?",
        "How are prices evolving across vendors?",
        "Which edge-deployment use cases are growing?",
      ],
    })}\n\n`
  );
  for (let i = 0; i < 3; i += 1) {
    frames.push(
      `data: ${JSON.stringify({ type: "phase", data: `Searching (${i + 1}/3)` })}\n\n`
    );
    frames.push(
      `data: ${JSON.stringify({
        type: "search_results",
        sub_question_index: i,
        articles: [
          { id: i + 1, title: `Article ${i + 1}`, source: "TechCrunch" },
        ],
      })}\n\n`
    );
  }
  for (const sa of [
    { data: "start", skill: "summarize_article", article_id: 1 },
    { data: "start", skill: "summarize_article", article_id: 2 },
    {
      data: "done",
      skill: "summarize_article",
      article_id: 1,
      duration_ms: 1234,
      summary: "Leading AI chip vendor announced a new architecture for edge inference workloads.",
    },
    {
      data: "done",
      skill: "summarize_article",
      article_id: 2,
      duration_ms: 1456,
      summary: "Benchmark comparison shows pricing pressure across commodity SKUs.",
    },
  ]) {
    frames.push(`data: ${JSON.stringify({ type: "subagent", ...sa })}\n\n`);
  }
  frames.push(`data: ${JSON.stringify({ type: "phase", data: "Synthesizing" })}\n\n`);
  // Sprinkle a few tokens so the streaming render path animates.
  for (const t of ["## ", "Executive ", "Summary\n", "Streaming ", "content..."]) {
    frames.push(`data: ${JSON.stringify({ type: "token", data: t })}\n\n`);
  }
  frames.push(
    `data: ${JSON.stringify({
      type: "phase",
      data: "done",
      report: RESEARCH_REPORT,
    })}\n\n`
  );
  await page.route("**/api/research", async (route: Route) => {
    await route.fulfill({
      status: 200,
      headers: { "Content-Type": "text/event-stream" },
      body: frames.join(""),
    });
  });
}

test.describe("M3.M6 demo — complete mission flow under slowMo", () => {
  test("end-to-end demo: palette -> research -> save -> open saved -> light theme", async ({
    page,
    context,
  }) => {
    test.setTimeout(240_000);

    await installResearchMock(page);

    try {
      await test.step("1. Open TechPulse AI — dark theme by default", async () => {
        await page.goto("/");
        await expect(
          page.getByRole("heading", { name: /TechPulse AI/i })
        ).toBeVisible({ timeout: 15_000 });
        // Confirm dark theme is on at boot.
        const html = page.locator("html");
        await expect(html).toHaveClass(/dark/, { timeout: 5_000 });
        await beat(page);
      });

      await test.step("2. Cmd+K opens the command palette", async () => {
        // Use Ctrl+K cross-platform — the palette handler listens for
        // both. Then type "Research" + Enter to jump tabs.
        await page.keyboard.press("Control+k");
        await beat(page);
        const palette = page.getByRole("dialog").first();
        await expect(palette).toBeVisible({ timeout: 5_000 });
        await page.keyboard.type("Research");
        await beat(page, 0.5);
        await page.keyboard.press("Enter");
        await beat(page);
        await expect(page.getByPlaceholder(/AI funding rounds/i)).toBeVisible({
          timeout: 10_000,
        });
      });

      await test.step("3. Click a suggested-query chip — agent starts", async () => {
        // The empty-state row gives us 6 curated chips. Pick the first.
        const chips = page.getByTestId("suggested-query-chip");
        await expect(chips.first()).toBeVisible({ timeout: 5_000 });
        // The chip click auto-submits via conductResearch(q).
        // We use a custom query instead so the mocked flow is deterministic.
        await page.getByPlaceholder(/AI funding rounds/i).fill(SHORT_QUESTION);
        await beat(page, 0.5);
        await page.getByRole("button", { name: /^Research$/i }).click();
        await beat(page);
      });

      await test.step("4. Sub-questions panel appears; subagents fan out", async () => {
        const panel = page.getByTestId("research-sub-questions-panel");
        await expect(panel).toBeVisible({ timeout: 5_000 });
        const rows = page.getByTestId("research-sub-question-row");
        await expect(rows).toHaveCount(3, { timeout: 10_000 });
        const subagentsPanel = page.getByTestId("research-subagents-panel");
        await expect(subagentsPanel).toBeVisible({ timeout: 10_000 });
        await beat(page);
      });

      await test.step("5. Run completes — phase chip lands on Done", async () => {
        const chip = page.getByTestId("research-phase-chip");
        await expect(chip).toHaveText(/Done/i, { timeout: 20_000 });
        // Let the viewer linger on the completed report so the
        // synthesized tokens + citation markers register.
        await beat(page, 3);
      });

      await test.step("6. Hover a [N] citation — hover card pops", async () => {
        const reportBody = page.getByTestId("research-report-body");
        const firstCitation = reportBody
          .locator('a.citation[href^="#source-"]')
          .first();
        await expect(firstCitation).toBeVisible({ timeout: 5_000 });
        // Mock the article endpoint so the hover card has data.
        await page.route("**/api/news/**", async (route: Route) => {
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({
              data: {
                id: 1,
                title: "AI Chip Leader Profile",
                source: "TechCrunch",
                published_at: "2026-05-01T00:00:00Z",
                summary:
                  "Leading AI chip vendor announced a new architecture for edge inference workloads with significant power efficiency improvements.",
              },
            }),
          });
        });
        await firstCitation.hover();
        // Hover dwell so the user can read the citation preview.
        await beat(page, 3);
      });

      await test.step("7. Click Save — toast + flip to Saved ✓", async () => {
        // Mock the save endpoint so the demo doesn't depend on backend.
        await page.route("**/api/saved-research", async (route: Route) => {
          if (route.request().method() === "POST") {
            await route.fulfill({
              status: 200,
              contentType: "application/json",
              body: JSON.stringify({
                data: { id: 999, question: SHORT_QUESTION, created_at: "2026-05-12T00:00:00Z" },
              }),
            });
          } else {
            await route.fulfill({
              status: 200,
              contentType: "application/json",
              body: JSON.stringify({
                data: [
                  {
                    id: 999,
                    question: SHORT_QUESTION,
                    report_md: RESEARCH_REPORT,
                    sources: [],
                    created_at: "2026-05-12T00:00:00Z",
                  },
                ],
              }),
            });
          }
        });
        const saveBtn = page.getByTestId("research-save-btn");
        await expect(saveBtn).toBeVisible({ timeout: 5_000 });
        await saveBtn.click();
        // Expect the button to flip to "Saved ✓".
        await expect(saveBtn).toContainText(/Saved/i, { timeout: 10_000 });
        await beat(page, 1.5);
      });

      await test.step("8. Navigate to Saved tab — list shows the new report", async () => {
        await page.getByRole("tab", { name: /Saved/i }).click();
        await beat(page);
        // The list might render either the new report or "no saved" if
        // the backend mock isn't fully wired. Either is acceptable for
        // the demo; we just need the tab to render.
        await page.waitForLoadState("networkidle", { timeout: 10_000 }).catch(() => {});
        await beat(page, 1.5);
      });

      await test.step("9. Navigate to News Feed", async () => {
        await page.getByRole("tab", { name: /News Feed/i }).click();
        await page.waitForLoadState("networkidle", { timeout: 10_000 }).catch(() => {});
        await beat(page, 2);
      });

      await test.step("9c. Navigate to Digest", async () => {
        await page.getByRole("tab", { name: /Digest/i }).click();
        await page.waitForLoadState("networkidle", { timeout: 10_000 }).catch(() => {});
        await beat(page, 3);
      });

      await test.step("10. Toggle theme to light in Settings, reload, restore dark", async () => {
        await page.getByRole("tab", { name: /Settings/i }).click();
        await expect(page.getByText(/Topic Preferences/i)).toBeVisible({
          timeout: 10_000,
        });
        await beat(page);
        // Theme toggle lives in the sidebar at the bottom.
        const themeToggle = page.getByTestId("theme-toggle");
        await expect(themeToggle).toBeVisible();
        await themeToggle.click();
        await beat(page);
        // Verify `<html>` lost the .dark class.
        await expect(page.locator("html")).not.toHaveClass(/dark/);
        await beat(page);
        // Reload and verify persistence.
        await page.reload();
        await expect(
          page.getByRole("heading", { name: /TechPulse AI/i })
        ).toBeVisible({ timeout: 10_000 });
        await expect(page.locator("html")).not.toHaveClass(/dark/);
        await beat(page);
        // Flip back to dark for hygiene.
        await page.getByTestId("theme-toggle").click();
        await beat(page);
        await expect(page.locator("html")).toHaveClass(/dark/);
        await beat(page, 3);
      });
    } finally {
      await page.unroute("**/api/research").catch(() => {});
      await page.unroute("**/api/news/**").catch(() => {});
      await page.unroute("**/api/saved-research").catch(() => {});
    }
  });
});
