import { test, expect } from "@playwright/test";

test("Ask AI deep inspect", async ({ page }) => {
  test.setTimeout(420_000);
  const errors: string[] = [];
  const newsApiHits: Record<string, number> = {};
  const allBackendCalls: string[] = [];
  page.on("console", msg => { if (msg.type() === "error") errors.push(msg.text()); });
  page.on("request", req => {
    const u = req.url();
    if (u.includes("/api/")) allBackendCalls.push(`${req.method()} ${u}`);
    const m = u.match(/\/api\/news\/(\d+)$/);
    if (m) newsApiHits[m[1]] = (newsApiHits[m[1]] || 0) + 1;
  });

  await page.goto("/");
  await expect(page.getByRole("heading", { name: /TechPulse AI/i })).toBeVisible();
  await page.getByRole("tab", { name: /Ask AI/i }).click();
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(1500);

  const chatInput = page.locator("textarea, input[placeholder*='Ask' i], input[placeholder*='question' i]").first();
  await chatInput.fill("Tell me about recent AI chip news");
  await chatInput.press("Enter");
  console.log("SUBMITTED at", Date.now());

  // Wait up to 4 minutes for citations OR a stable response
  let citationCount = 0;
  let elapsed = 0;
  const start = Date.now();
  while (elapsed < 240_000) {
    citationCount = await page.locator("a.citation").count();
    const anyCite = await page.locator("[data-citation-index], sup.citation, a[href^='#source']").count();
    const responseDoneIcon = await page.locator("[data-testid='message-done'], svg.lucide-check").count();
    if (elapsed % 15000 === 0) {
      console.log(`elapsed=${(elapsed/1000)|0}s citationCount=${citationCount} anyCite=${anyCite} checkIcon=${responseDoneIcon}`);
    }
    if (citationCount > 0 || anyCite > 0) break;
    await page.waitForTimeout(3000);
    elapsed = Date.now() - start;
  }

  console.log("FINAL_CITATION_COUNT:", citationCount);
  console.log("ALL_API_CALLS:", JSON.stringify(allBackendCalls.slice(0, 30)));

  // Dump full response HTML
  const responseHTML = await page.evaluate(() => {
    const containers = document.querySelectorAll("[class*='message'], [class*='response'], article, [data-role='assistant']");
    let last: HTMLElement | null = null;
    containers.forEach((c) => { if (!last || (c as HTMLElement).offsetTop > last.offsetTop) last = c as HTMLElement; });
    return last ? (last as HTMLElement).outerHTML.slice(0, 6000) : "NO_CONTAINER";
  });
  console.log("RESPONSE_HTML:", responseHTML);

  // Dump rendered citation-related markup
  const allLinks = await page.evaluate(() => {
    return Array.from(document.querySelectorAll("a, sup, button")).slice(-20).map(n => ({
      tag: n.tagName,
      text: (n.textContent || "").slice(0, 30),
      cls: (n as HTMLElement).className?.toString().slice(0, 80),
      href: n.getAttribute("href"),
      testid: n.getAttribute("data-testid"),
    }));
  });
  console.log("LAST_INTERACTIVE:", JSON.stringify(allLinks));

  await page.screenshot({ path: "test-results/m3m4-askai-deep.png", fullPage: true });

  // Try hovering ANY citation-like element
  const candidates = page.locator("a.citation, a[href^='#source'], sup.citation, [data-citation-index]");
  const count = await candidates.count();
  console.log("CANDIDATE_COUNT:", count);
  if (count > 0) {
    const first = candidates.first();
    const before = JSON.stringify(newsApiHits);
    await first.hover();
    await page.waitForTimeout(600);
    const hoverCard = page.getByTestId("citation-hover-card");
    const cardVisible = await hoverCard.isVisible().catch(() => false);
    console.log("HOVER_CARD_VISIBLE:", cardVisible);
    if (cardVisible) {
      const cardBox = await hoverCard.boundingBox();
      console.log("HOVER_CARD_BOX:", JSON.stringify(cardBox));
      const cardText = (await hoverCard.textContent() ?? "").slice(0, 300);
      console.log("HOVER_CARD_TEXT:", JSON.stringify(cardText));
      const cardStyle = await hoverCard.evaluate((el) => {
        const cs = getComputedStyle(el);
        return { pointerEvents: cs.pointerEvents, width: cs.width, position: cs.position, zIndex: cs.zIndex };
      });
      console.log("HOVER_CARD_STYLE:", JSON.stringify(cardStyle));
      await page.screenshot({ path: "test-results/m3m4-askai-hover.png", fullPage: true });
    } else {
      const allTestIds = await page.evaluate(() => Array.from(document.querySelectorAll("[data-testid]")).map(el => el.getAttribute("data-testid")));
      console.log("ALL_TESTIDS:", JSON.stringify(allTestIds));
    }
    await page.mouse.move(10, 10);
    await page.waitForTimeout(500);
    await first.hover();
    await page.waitForTimeout(600);
    const href = await first.getAttribute("href");
    const articleId = (href || "#source-1").replace("#source-", "");
    console.log("ARTICLE_ID:", articleId);
    console.log("FETCH_BEFORE_HOVER:", before);
    console.log("FETCH_AFTER_BOTH_HOVERS:", JSON.stringify(newsApiHits));
    console.log("ARTICLE_FETCH_COUNT:", newsApiHits[articleId] ?? 0);
  }
  console.log("CONSOLE_ERRORS:", JSON.stringify(errors));
});
