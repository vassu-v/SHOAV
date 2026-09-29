// QA driver for the live feed. Needs a real controller (CTL, default 18491), the UI built against it
// (UI, default 3111) and a page with motion served at PAGE (default http://127.0.0.1:18452/index.html).
// Usage: node scripts/qa-stream.mjs   (writes qa/11-*.png ... qa/15-*.png)
import { chromium } from "playwright-core";
import { mkdirSync } from "node:fs";

const CTL = process.env.CTL || "http://127.0.0.1:18491";
const UI = process.env.UI || "http://127.0.0.1:3111";
const PAGE = process.env.PAGE || "http://127.0.0.1:18452/index.html";
const H = { "content-type": "application/json", accept: "application/json, text/event-stream" };
mkdirSync("qa", { recursive: true });
const log = (m) => console.log(m);

let rpcId = 1;
async function rpc(sid, method, params) {
  const r = await fetch(CTL + "/mcp", { method: "POST", headers: sid ? { ...H, "mcp-session-id": sid } : H, body: JSON.stringify({ jsonrpc: "2.0", id: ++rpcId, method, params }) });
  return { sid: r.headers.get("mcp-session-id"), body: await r.json() };
}
const init = await rpc(null, "initialize", { protocolVersion: "2025-03-26", capabilities: {}, clientInfo: { name: "qa-stream", version: "1" } });
const mcp = init.sid;
await fetch(CTL + "/mcp", { method: "POST", headers: { ...H, "mcp-session-id": mcp }, body: JSON.stringify({ jsonrpc: "2.0", method: "notifications/initialized" }) });
const tool = async (name, args) => (await rpc(mcp, "tools/call", { name, arguments: args })).body.result;
const created = await tool("browser_create_session", { start_url: PAGE });
const sid = JSON.parse(created.content[0].text).live_view.session_id;
log("session " + sid);
await tool("browser_screenshot", { session_id: sid });
await tool("browser_execute_action", { session_id: sid, action: { action: "scroll", delta_y: 10, reason: "qa" } });
const viewers = async () => (await (await fetch(CTL + "/live-api/stream-stats")).json()).total_viewers;

const browser = await chromium.launch({ channel: "chrome" });
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await ctx.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
await page.goto(`${UI}/s/${sid}`);
await page.waitForSelector('[data-testid="live-feed"][data-status="live"]', { timeout: 20000 });
log("chip: " + (await page.getByTestId("feed-chip").innerText()));
const feed = page.locator('[data-testid="live-feed"] img').first();
const a = await feed.screenshot({ path: "qa/11-stream-live-a.png" });
await page.waitForTimeout(1000);
const b = await feed.screenshot({ path: "qa/11-stream-live-b.png" });
log("two shots a second apart differ: " + !a.equals(b));
await page.screenshot({ path: "qa/11-stream-live-page.png" });
log("viewers with tab open: " + (await viewers()));

// Tab hidden drops the stream, visible brings it back.
await page.evaluate(() => {
  Object.defineProperty(document, "visibilityState", { configurable: true, get: () => "hidden" });
  document.dispatchEvent(new Event("visibilitychange"));
});
await page.waitForTimeout(2000);
log("viewers while hidden: " + (await viewers()) + " chip: " + (await page.getByTestId("feed-chip").innerText()));
await page.evaluate(() => {
  Object.defineProperty(document, "visibilityState", { configurable: true, get: () => "visible" });
  document.dispatchEvent(new Event("visibilitychange"));
});
await page.waitForSelector('[data-testid="live-feed"][data-status="live"]', { timeout: 15000 });
log("viewers after visible again: " + (await viewers()));

// Counter label and tooltip.
await page.getByTestId("stat-captures").hover();
await page.waitForTimeout(400);
await page.screenshot({ path: "qa/14-counter-tooltip.png", clip: { x: 700, y: 0, width: 740, height: 200 } });
log("counter: " + (await page.getByTestId("stat-captures").innerText()).replace(/\n/g, " "));
await page.mouse.move(10, 400);

// Timeline row with a capture -> captures view, then back to live.
await page.locator("[data-testid=timeline-scroll] button").filter({ hasText: "screenshot" }).first().click();
log("after row click, Back to live visible: " + (await page.getByRole("button", { name: "Back to live" }).isVisible()));
await page.waitForTimeout(500);
await page.screenshot({ path: "qa/13-captures.png" });
await page.getByRole("button", { name: "Back to live" }).click();
await page.waitForSelector('[data-testid="live-feed"][data-status="live"]', { timeout: 15000 });

// Stream failure -> fallback to the last capture.
await page.route("**/live-api/sessions/*/stream*", (r) => r.abort());
await page.reload();
await page.waitForSelector('[data-testid="live-feed"][data-status="unavailable"]', { timeout: 20000 });
await page.waitForTimeout(500);
log("fallback chip: " + (await page.getByTestId("feed-chip").innerText()));
await page.screenshot({ path: "qa/12-stream-fallback.png" });
await page.unroute("**/live-api/sessions/*/stream*");
await page.waitForSelector('[data-testid="live-feed"][data-status="live"]', { timeout: 30000 });
log("recovered after backoff, viewers: " + (await viewers()));

// Leaving the page releases the connection.
await page.goto(`${UI}/`);
await page.waitForTimeout(2000);
log("viewers after leaving the session page: " + (await viewers()));

// Session closes -> archived view, no stream.
await page.goto(`${UI}/s/${sid}`);
await page.waitForSelector('[data-testid="live-feed"][data-status="live"]', { timeout: 20000 });
await tool("browser_close_session", { session_id: sid });
await page.waitForSelector("[data-testid=archived-banner]", { timeout: 20000 });
await page.waitForTimeout(800);
await page.screenshot({ path: "qa/15-archived.png" });
log("live feed present in archived view: " + (await page.getByTestId("live-feed").count()));
log("viewers after close: " + (await viewers()));
log("page errors: " + errors.length + " " + errors.slice(0, 3).join(" | "));
await browser.close();
