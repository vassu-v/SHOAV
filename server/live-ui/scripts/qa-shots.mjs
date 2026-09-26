// Throwaway QA driver: screenshots into qa/. Needs mock (18450) + UI (3110) running.
// Usage: node scripts/qa-shots.mjs [--kill-mock=<pid>]
import { chromium } from "playwright-core";
import { mkdirSync } from "node:fs";

const UI = "http://127.0.0.1:3110";
const killPid = (process.argv.find((a) => a.startsWith("--kill-mock=")) || "").split("=")[1];
mkdirSync("qa", { recursive: true });
const browser = await chromium.launch({ channel: "chrome" });
const out = [];
const log = (m) => { out.push(m); console.log(m); };

for (const scheme of killPid ? ["light"] : ["light", "dark"]) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: scheme });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));

  await page.goto(UI + "/");
  await page.waitForSelector("table");
  await page.screenshot({ path: `qa/01-list-${scheme}.png` });
  log(`[${scheme}] list rows: ${await page.locator("tbody tr").count()}`);

  await page.goto(UI + "/s/a5af842a89e1");
  await page.waitForSelector("text=Live");
  await page.waitForTimeout(9000);
  await page.screenshot({ path: `qa/02-live-${scheme}.png` });
  log(`[${scheme}] timeline rows: ${await page.locator("[data-testid=timeline-scroll] > div").count()}`);

  if (scheme === "light") {
    // expand a row
    await page.locator("[data-testid=timeline-scroll] button").nth(1).click();
    await page.waitForTimeout(300);
    await page.screenshot({ path: "qa/03-expanded.png" });
    // scroll up -> jump to latest
    await page.locator("[data-testid=timeline-scroll]").evaluate((el) => (el.scrollTop = 0));
    await page.waitForTimeout(3500);
    log(`jump button visible after scroll up: ${await page.getByText("Jump to latest").isVisible()}`);
    await page.getByText("Jump to latest").click();
    // tools tab
    await page.getByRole("tab", { name: "Tools" }).click();
    await page.waitForSelector("text=Instructions the agent receives");
    await page.screenshot({ path: "qa/04-tools.png" });
    await page.getByRole("tab", { name: "Timeline" }).click();

    // archived + restart
    await page.goto(UI + "/s/3c81d0e2b7f4");
    await page.waitForSelector("[data-testid=archived-banner]");
    await page.waitForTimeout(500);
    await page.screenshot({ path: "qa/05-archived.png" });
    await page.locator("[data-testid=timeline-scroll] button").nth(1).click();
    await page.waitForTimeout(300);
    await page.screenshot({ path: "qa/05b-archived-row-preview.png" });
    await page.getByRole("button", { name: "Restart session" }).click();
    await page.waitForURL(/\/s\/(?!3c81d0e2b7f4)/);
    log(`restart navigated to ${page.url()}`);
    await page.waitForTimeout(2500);
    await page.screenshot({ path: "qa/06-restarted.png" });

    // 404
    await page.goto(UI + "/s/doesnotexist");
    await page.waitForSelector("text=Session not found");
    await page.screenshot({ path: "qa/07-notfound.png" });

    // mobile
    const m = await browser.newContext({ viewport: { width: 390, height: 844 }, colorScheme: "light" });
    const mp = await m.newPage();
    await mp.goto(UI + "/s/a5af842a89e1");
    await mp.waitForSelector("text=Live");
    await mp.waitForTimeout(6000);
    await mp.screenshot({ path: "qa/08-mobile.png", fullPage: true });
    const overflow = await mp.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    log(`mobile horizontal overflow px: ${overflow}`);
    await mp.goto(UI + "/");
    await mp.waitForSelector("table");
    await mp.screenshot({ path: "qa/08b-mobile-list.png" });
    await m.close();

    if (killPid) {
      await page.goto(UI + "/s/a5af842a89e1");
      await page.waitForSelector("text=Live");
      await page.waitForTimeout(3000);
      process.kill(Number(killPid));
      await page.waitForSelector("text=Reconnecting", { timeout: 15000 });
      await page.waitForTimeout(1500);
      await page.screenshot({ path: "qa/09-reconnecting.png" });
      log("reconnecting state observed after mock kill");
    }
  }
  log(`[${scheme}] console/page errors: ${errors.length} ${errors.slice(0, 3).join(" | ")}`);
  await ctx.close();
}
await browser.close();
