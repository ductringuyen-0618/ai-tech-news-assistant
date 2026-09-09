import { test, expect } from "@playwright/test";

test("Ask AI hover card focused", async ({ page }) => {
  test.setTimeout(360_000);
  const errors: string[] = [];
  const newsApiHits: Record<string, number> = {};
  page.on("console", msg => { if (msg.type() === "error") errors.push(msg.text()); });
  page.on("request", req => {
    const u = req.url();
    const m = u.match(/\/api\/news\/(\d+)$/);
    if (m) newsApiHits[m[1]] = (newsApiHits[m[1]] || 0) + 1;
  });

  await page.goto("/");
  await expect(page.getByRole("heading", { name: /TechPulse AI/i })).toBeVisible();
  await page.getByRole("tab", { name: /Ask AI/i }).click();
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(1500);

  // Inspect DOM around chat
  const askAiHTML = await page.evaluate(() => {
    const main = document.querySelector("main") || document.body;
    return main.outerHTML.slice(0, 4000);
  });
  console.log("ASK_AI_HTML_SNIPPET:", askAiHTML);

  const chatInput = page.locator("textarea, input[placeholder*='Ask' i], input[placeholder*='question' i]").first();
  if (await chatInput.count()) {
    await chatInput.fill("Tell me about recent AI chip news");
    const submitBtn = page.getByRole("button", { name: /send|ask/i }).first();
    if (await submitBtn.count()) {
      await submitBtn.click();
    } else {
      await chatInput.press("Enter");
    }
    console.log("SUBMITTED");

    // Wait long enough for Ollama RAG
    await page.waitForTimeout(5000);

    // Poll for the response to finish - look for any rendered citation or stable text
    let citationCount = 0;
    for (let i = 0; i < 60; i++) {
      citationCount = await page.locator("a.citation").count();
      const anyCitation = await page.locator("[class*=citation]").count();
      const supTags = await page.locator("sup").count();
      const allLinks = await page.locator("a").count();
      if (i % 5 === 0) console.log(`tick=${i}s citationCount=${citationCount} anyCitation=${anyCitation} supTags=${supTags} links=${allLinks}`);
      if (citationCount > 0) break;
      await page.waitForTimeout(3000);
    }

    console.log("FINAL_CITATION_COUNT:", citationCount);

    // Look for source markers in text - they could be [1] inline
    const responseText = await page.evaluate(() => {
      const msgs = document.querySelectorAll("[class*=message], [data-role], article, p");
      let last = "";
      msgs.forEach(m => { if (m.textContent && m.textContent.length > last.length) last = m.textContent; });
      return last.slice(0, 1500);
    });
    console.log("RESPONSE_TEXT_SNIPPET:", responseText);

    // Dump rendered citation-related markup
    const citationsHtml = await page.evaluate(() => {
      const sel = document.querySelectorAll("a.citation, [class*='citation'], sup, a[href^='#source']");
      return Array.from(sel).slice(0, 8).map(n => (n as HTMLElement).outerHTML).join("\n");
    });
    console.log("CITATION_DOM:", citationsHtml);

    await page.screenshot({ path: "test-results/m3m4-askai-response-v2.png", fullPage: true });

    const firstCitation = page.locator("a.citation").first();
    if (await firstCitation.count()) {
      const href = await firstCitation.getAttribute("href");
      console.log("FIRST_CITATION_HREF:", href);
      await firstCitation.hover();
      await page.waitForTimeout(500);
      const hoverCard = page.getByTestId("citation-hover-card");
      const cardVisible = await hoverCard.isVisible().catch(() => false);
      console.log("HOVER_CARD_VISIBLE:", cardVisible);
      if (cardVisible) {
        const cardBox = await hoverCard.boundingBox();
        console.log("HOVER_CARD_BOX:", JSON.stringify(cardBox));
        const cardText = (await hoverCard.textContent() ?? "").slice(0, 280);
        console.log("HOVER_CARD_TEXT:", JSON.stringify(cardText));
        const cardStyle = await hoverCard.evaluate((el) => {
          const cs = getComputedStyle(el);
          return { pointerEvents: cs.pointerEvents, width: cs.width, position: cs.position };
        });
        console.log("HOVER_CARD_STYLE:", JSON.stringify(cardStyle));
        await page.screenshot({ path: "test-results/m3m4-askai-hover.png", fullPage: true });
      } else {
        // Try data-testid alternative names
        const alt1 = await page.locator("[data-testid*='hover']").count();
        const alt2 = await page.locator("[role='tooltip']").count();
        const alt3 = await page.locator("[class*='hover-card']").count();
        console.log("ALT_HOVER_NODES:", alt1, alt2, alt3);
        const allTestIds = await page.evaluate(() => Array.from(document.querySelectorAll("[data-testid]")).map(el => el.getAttribute("data-testid")));
        console.log("ALL_TESTIDS:", JSON.stringify(allTestIds));
      }

      // Map cache check
      await page.mouse.move(10, 10);
      await page.waitForTimeout(400);
      await firstCitation.hover();
      await page.waitForTimeout(500);
      const articleId = (href || "#source-1").replace("#source-", "");
      console.log("ARTICLE_ID:", articleId);
      console.log("ARTICLE_ID_FETCH_COUNT:", newsApiHits[articleId] ?? 0);
      console.log("ALL_FETCHES:", JSON.stringify(newsApiHits));
    }
  }

  console.log("CONSOLE_ERRORS:", JSON.stringify(errors));
});
