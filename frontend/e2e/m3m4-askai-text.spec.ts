import { test, expect } from "@playwright/test";

test("Capture assistant text", async ({ page }) => {
  test.setTimeout(420_000);
  page.on("console", () => {});
  await page.goto("/");
  await page.getByRole("tab", { name: /Ask AI/i }).click();
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(1500);
  const chatInput = page.locator("textarea, input[placeholder*='Ask' i]").first();
  await chatInput.fill("Tell me about recent AI chip news. Use citation markers like [1] and [2] referring to the relevant articles.");
  await chatInput.press("Enter");

  // Wait for response (poll for assistant message text)
  let lastText = "";
  for (let i = 0; i < 80; i++) {
    const msgs = await page.locator("[data-role='assistant']").all();
    if (msgs.length > 0) {
      const t = (await msgs[msgs.length - 1].textContent()) || "";
      if (t.length > 50 && t === lastText) break;
      lastText = t;
    }
    await page.waitForTimeout(3000);
  }
  console.log("ASSISTANT_TEXT_LENGTH:", lastText.length);
  console.log("ASSISTANT_TEXT:", JSON.stringify(lastText.slice(0, 2500)));
  console.log("CITATION_BRACKET_COUNT:", (lastText.match(/\[\d+\]/g) || []).length);
  console.log("CITATION_ANCHORS:", await page.locator("a.citation").count());
  console.log("ANY_CITATION_CLASS:", await page.locator(".citation").count());

  // If we have citation anchors, hover the first
  const anchors = page.locator("a.citation");
  const c = await anchors.count();
  console.log("ANCHOR_COUNT:", c);
  if (c > 0) {
    await anchors.first().hover();
    await page.waitForTimeout(600);
    const hc = page.getByTestId("citation-hover-card");
    const visible = await hc.isVisible().catch(() => false);
    console.log("HOVER_VISIBLE:", visible);
    if (visible) {
      console.log("HOVER_BOX:", JSON.stringify(await hc.boundingBox()));
      console.log("HOVER_TEXT:", JSON.stringify((await hc.textContent() || "").slice(0, 280)));
      console.log("HOVER_STYLE:", JSON.stringify(await hc.evaluate(el => {
        const cs = getComputedStyle(el);
        return { pe: cs.pointerEvents, w: cs.width, pos: cs.position };
      })));
      await page.screenshot({ path: "test-results/m3m4-askai-hover.png", fullPage: true });
    }
    // cache check
    const requests: Record<string, number> = {};
    page.on("request", r => {
      const m = r.url().match(/\/api\/news\/(\d+)$/);
      if (m) requests[m[1]] = (requests[m[1]] || 0) + 1;
    });
    await page.mouse.move(10, 10);
    await page.waitForTimeout(500);
    await anchors.first().hover();
    await page.waitForTimeout(500);
    console.log("CACHE_FETCHES_AFTER_REHOVER:", JSON.stringify(requests));
  }
});
