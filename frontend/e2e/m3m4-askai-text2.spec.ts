import { test, expect } from "@playwright/test";

test("Capture assistant text v2", async ({ page }) => {
  test.setTimeout(420_000);
  page.on("console", () => {});
  const requests: Record<string, number> = {};
  page.on("request", r => {
    const m = r.url().match(/\/api\/news\/(\d+)$/);
    if (m) requests[m[1]] = (requests[m[1]] || 0) + 1;
  });
  await page.goto("/");
  await page.getByRole("tab", { name: /Ask AI/i }).click();
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(1500);
  const initialMsgCount = await page.locator("[data-role='assistant']").count();
  console.log("INITIAL_ASSISTANT_MSGS:", initialMsgCount);

  const chatInput = page.locator("textarea, input[placeholder*='Ask' i]").first();
  await chatInput.fill("Tell me about recent AI chip news");
  await chatInput.press("Enter");

  // Wait for a NEW assistant message
  let answer = "";
  let stableCount = 0;
  for (let i = 0; i < 100; i++) {
    const msgs = await page.locator("[data-role='assistant']").all();
    if (msgs.length > initialMsgCount) {
      const t = (await msgs[msgs.length - 1].textContent()) || "";
      if (t === answer && t.length > 60) {
        stableCount++;
        if (stableCount >= 3) break;
      } else {
        stableCount = 0;
      }
      answer = t;
    }
    await page.waitForTimeout(3000);
  }
  console.log("ANSWER_LEN:", answer.length);
  console.log("ANSWER_TEXT:", JSON.stringify(answer.slice(0, 2500)));
  console.log("CITATION_BRACKET_COUNT:", (answer.match(/\[\d+\]/g) || []).length);
  console.log("CITATION_ANCHORS:", await page.locator("a.citation").count());
  console.log("ANY_CITATION_CLASS:", await page.locator(".citation").count());

  await page.screenshot({ path: "test-results/m3m4-askai-text-v2.png", fullPage: true });

  const anchors = page.locator("a.citation");
  const c = await anchors.count();
  if (c > 0) {
    await anchors.first().hover();
    await page.waitForTimeout(700);
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
    await page.mouse.move(10, 10);
    await page.waitForTimeout(500);
    await anchors.first().hover();
    await page.waitForTimeout(500);
    console.log("FETCHES:", JSON.stringify(requests));
  }
});
