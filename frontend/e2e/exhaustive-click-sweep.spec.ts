import { test, expect, ConsoleMessage } from "@playwright/test";

/**
 * Exhaustive interactive-element sweep.
 *
 * Tagged `@exhaustive` and excluded from the default suite (see
 * verify.ps1's --grep-invert) -- it's slower and coarser than the
 * scenario specs and belongs to feature verification, not the fast loop.
 * Run it explicitly after a feature/UI change:
 *
 *   npx playwright test exhaustive-click-sweep --grep "@exhaustive"
 *
 * What it does: visits every top-level tab, discovered live from the
 * `role="tablist"` (not hardcoded, so a newly added tab gets covered
 * automatically), then within each tab enumerates every visible
 * interactive element -- button, link, [role=tab/button/switch/checkbox/
 * menuitem], input, select, textarea -- and clicks/toggles each one.
 *
 * A control PASSES if clicking it doesn't throw a client-side error and
 * doesn't leave the page blank/crashed. Escape is pressed after every
 * click so a dialog/menu one control opened doesn't swallow the next
 * control's click. Destructive-looking controls (delete/remove/clear/
 * sign out) are matched by DENYLIST below and skipped rather than
 * clicked -- extend that list when a feature adds a new destructive
 * action.
 *
 * Known limitation: the element list for a tab is captured once, before
 * any clicks in that tab happen. If an early click mutates the DOM (a
 * modal that adds/removes controls), a later element in the same tab can
 * go stale and throw on click. That's reported as a failure but is not
 * necessarily a real bug -- triage it by hand: re-run focused on just
 * that tab, or check whether the flow genuinely breaks with a normal
 * scenario spec (see e2e/news-feed.spec.ts etc. for the pattern) before
 * treating it as a regression.
 */

const DENYLIST =
  /delete|remove|clear all|sign ?out|log ?out|reset (password|account)/i;

const INTERACTIVE_SELECTOR = [
  "button",
  "a[href]",
  '[role="button"]',
  '[role="tab"]',
  '[role="switch"]',
  '[role="checkbox"]',
  '[role="menuitem"]',
  "input",
  "select",
  "textarea",
].join(", ");

interface TabReport {
  ok: string[];
  failed: string[];
}

test.describe("exhaustive UI click sweep @exhaustive", () => {
  test("every interactive element on every tab responds without erroring", async ({
    page,
  }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
    page.on("console", (msg: ConsoleMessage) => {
      if (msg.type() === "error") errors.push(`console.error: ${msg.text()}`);
    });

    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: /TechPulse AI/i })
    ).toBeVisible({ timeout: 15_000 });

    const tabNames = (
      await Promise.all(
        (await page.getByRole("tab").all()).map((t) =>
          t.getAttribute("aria-label")
        )
      )
    ).filter((n): n is string => Boolean(n));

    const report: Record<string, TabReport> = {};

    for (const name of tabNames) {
      report[name] = { ok: [], failed: [] };
      await page.getByRole("tab", { name, exact: true }).click();
      await page.waitForTimeout(500); // let the panel settle / data load

      const elements = await page.locator(INTERACTIVE_SELECTOR).all();

      for (const el of elements) {
        if (!(await el.isVisible().catch(() => false))) continue;

        // isVisible() is true for sr-only-until-focus elements (skip links,
        // visually-hidden labels) -- their computed style is "visible" even
        // though they're positioned off-screen. Those are keyboard-only
        // affordances, not something a mouse click can reach; a plain
        // .click() reliably times out on them ("element is outside of the
        // viewport"), which is a false positive, not a bug. Bounding box
        // catches what isVisible() misses here.
        const box = await el.boundingBox().catch(() => null);
        if (!box || box.x < 0 || box.y < 0) continue;

        const label =
          (await el.getAttribute("aria-label")) ||
          (await el.textContent().catch(() => null))?.trim() ||
          (await el.getAttribute("placeholder")) ||
          "(unlabeled)";

        if (DENYLIST.test(label)) {
          report[name].ok.push(`${label} (skipped: denylisted)`);
          continue;
        }

        const errsBefore = errors.length;
        try {
          await el.click({ timeout: 3_000 });
        } catch (e) {
          report[name].failed.push(
            `${label}: click threw -- ${(e as Error).message}`
          );
          continue;
        }
        await page.waitForTimeout(150);

        // Back out of whatever the click opened so the next element in
        // the loop isn't hidden behind a dialog/menu.
        await page.keyboard.press("Escape").catch(() => {});

        if (errors.length > errsBefore) {
          report[name].failed.push(
            `${label}: ${errors.slice(errsBefore).join("; ")}`
          );
        } else {
          report[name].ok.push(label);
        }

        // Re-anchor on the tab in case the click navigated away from it.
        const stillOnTab = await page
          .getByRole("tab", { name, exact: true })
          .getAttribute("aria-selected")
          .catch(() => null);
        if (stillOnTab !== "true") {
          await page
            .getByRole("tab", { name, exact: true })
            .click()
            .catch(() => {});
          await page.waitForTimeout(300);
        }
      }
    }

    console.log(JSON.stringify(report, null, 2));

    const allFailed = Object.entries(report).flatMap(([tab, r]) =>
      r.failed.map((f) => `[${tab}] ${f}`)
    );
    expect(
      allFailed,
      `Interactive elements that errored:\n${allFailed.join("\n")}`
    ).toHaveLength(0);
  });
});
