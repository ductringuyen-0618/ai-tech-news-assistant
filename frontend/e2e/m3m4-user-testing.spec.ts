import { test, expect } from "@playwright/test";

test("M3.M4 user-testing - KG + Ask AI + Settings live", async ({ page }) => {
  test.setTimeout(240_000);
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

  // ---- KNOWLEDGE GRAPH ----
  await page.getByRole("tab", { name: /Knowledge/i }).click();
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(2500);
  await page.screenshot({ path: "test-results/m3m4-kg-dark.png", fullPage: true });

  const canvas = page.locator("canvas").first();
  const hasCanvas = await canvas.count();
  console.log("KG_HAS_CANVAS:", hasCanvas);
  if (hasCanvas) {
    const box = await canvas.boundingBox();
    console.log("KG_CANVAS_BOX:", JSON.stringify(box));
  }
  const htmlClassDark = await page.evaluate(() => document.documentElement.className);
  console.log("HTML_CLASS_IN_DARK:", htmlClassDark);
  const kgBg = await page.evaluate(() => window.getComputedStyle(document.body).backgroundColor);
  console.log("KG_BODY_BG_DARK:", kgBg);

  // ---- ASK AI ----
  await page.getByRole("tab", { name: /Ask AI/i }).click();
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(1000);

  const chatInput = page.locator("textarea, input[placeholder*='Ask' i], input[placeholder*='question' i]").first();
  if (await chatInput.count()) {
    await chatInput.fill("Tell me about recent AI chip news");
    const submitBtn = page.getByRole("button", { name: /send|ask/i }).first();
    if (await submitBtn.count()) {
      await submitBtn.click();
    } else {
      await chatInput.press("Enter");
    }
    console.log("ASK_AI_SUBMITTED");

    try {
      await expect(page.locator("a.citation").first()).toBeVisible({ timeout: 90_000 });
      console.log("ASK_AI_CITATION_VISIBLE: true");
    } catch {
      console.log("ASK_AI_CITATION_VISIBLE: false (timeout)");
    }

    await page.screenshot({ path: "test-results/m3m4-askai-response.png", fullPage: true });

    const firstCitation = page.locator("a.citation").first();
    if (await firstCitation.count()) {
      await firstCitation.hover();
      await page.waitForTimeout(400);
      const hoverCard = page.getByTestId("citation-hover-card");
      const cardVisible = await hoverCard.isVisible().catch(() => false);
      console.log("HOVER_CARD_VISIBLE:", cardVisible);
      if (cardVisible) {
        const cardBox = await hoverCard.boundingBox();
        console.log("HOVER_CARD_BOX:", JSON.stringify(cardBox));
        const cardText = (await hoverCard.textContent() ?? "").slice(0, 240);
        console.log("HOVER_CARD_TEXT:", JSON.stringify(cardText));
        await page.screenshot({ path: "test-results/m3m4-askai-hover.png", fullPage: true });
      }

      await page.mouse.move(10, 10);
      await page.waitForTimeout(300);
      await firstCitation.hover();
      await page.waitForTimeout(400);
      const articleId = (await firstCitation.getAttribute("href") || "#source-1").replace("#source-", "");
      console.log("ARTICLE_ID_FETCH_COUNT:", newsApiHits[articleId] ?? "none");
    }
  } else {
    console.log("ASK_AI_INPUT_NOT_FOUND");
  }

  // ---- SETTINGS ----
  await page.getByRole("tab", { name: /Settings/i }).click();
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(800);
  await page.screenshot({ path: "test-results/m3m4-settings-dark.png", fullPage: true });

  const lightRadio = page.getByRole("radio", { name: /light/i }).first();
  const darkRadio = page.getByRole("radio", { name: /dark/i }).first();
  console.log("THEME_RADIOS_FOUND:", await lightRadio.count(), await darkRadio.count());

  if (await lightRadio.count()) {
    await lightRadio.click();
    await page.waitForTimeout(500);
    const htmlClassLight = await page.evaluate(() => document.documentElement.className);
    const lightBg = await page.evaluate(() => window.getComputedStyle(document.body).backgroundColor);
    console.log("HTML_CLASS_AFTER_LIGHT:", htmlClassLight);
    console.log("BODY_BG_AFTER_LIGHT:", lightBg);
    await page.screenshot({ path: "test-results/m3m4-settings-light.png", fullPage: true });

    await page.reload();
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(800);
    const htmlClassAfterReload = await page.evaluate(() => document.documentElement.className);
    const bgAfterReload = await page.evaluate(() => window.getComputedStyle(document.body).backgroundColor);
    console.log("HTML_CLASS_AFTER_RELOAD:", htmlClassAfterReload);
    console.log("BG_AFTER_RELOAD:", bgAfterReload);

    await page.getByRole("tab", { name: /Settings/i }).click();
    await page.waitForTimeout(500);
    await page.getByRole("radio", { name: /dark/i }).first().click();
  }

  const compactRadio = page.getByRole("radio", { name: /compact/i }).first();
  if (await compactRadio.count()) {
    await compactRadio.click();
    await page.waitForTimeout(300);
    const densityStored = await page.evaluate(() => localStorage.getItem("techpulse-density"));
    console.log("DENSITY_STORED:", densityStored);
  }

  console.log("CONSOLE_ERRORS:", JSON.stringify(errors));
  console.log("HORIZONTAL_OVERFLOW:", await page.evaluate(() => document.body.scrollWidth - document.body.clientWidth));
});
