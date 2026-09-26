// Tiny mock of the controller /live-api + SSE, for UI development and tests.
// Usage: node scripts/mock-controller.mjs
// Env: MOCK_STREAM=off makes the stream answer 503 (fallback testing), MOCK_PORT (default 18450), MOCK_SPEED (default 1, higher = faster), LIVE_UI_BASE_URL.
import http from "node:http";
import { randomUUID } from "node:crypto";
import zlib from "node:zlib";

const PORT = Number(process.env.MOCK_PORT || 18450);
const SPEED = Number(process.env.MOCK_SPEED || 1);
const UI = process.env.LIVE_UI_BASE_URL || "http://127.0.0.1:3110";
const STREAM_OFF = process.env.MOCK_STREAM === "off";
const CRLF = String.fromCharCode(13, 10);
let streamViewers = 0; // open MJPEG connections, exposed at /mock/stats to check for leaks
const sessions = new Map(); // id -> { summary, events, seq, clients:Set, closed }
const now = () => new Date().toISOString();
const hex = (n = 12) => randomUUID().replace(/-/g, "").slice(0, n);

const TOOLS = [
  ["browser.create_session", "session", false, [], "Open a new browser session. Returns a session id and a live view link that must be shown to the user."],
  ["browser.close_session", "session", false, ["session_id"], "Close a session. The live view becomes a read-only archive."],
  ["browser.list_sessions", "session", true, [], "List active browser sessions."],
  ["browser.list_tabs", "session", true, ["session_id"], "List tabs of a session."],
  ["browser.screenshot", "screenshot", true, ["session_id"], "Capture a screenshot of the current page."],
  ["browser.observe", "screenshot", true, ["session_id"], "Observe the page: screenshot, interactable elements and text. preset=text skips the screenshot."],
  ["browser.get_html", "read", true, ["session_id"], "Return the page HTML."],
  ["browser.find_elements", "read", true, ["session_id", "query"], "Find elements matching a query."],
  ["browser.get_console", "read", true, ["session_id"], "Read console messages."],
  ["browser.execute_action", "act", false, ["session_id", "action"], "Perform a click, type, scroll or navigate action. Always give a reason."],
  ["browser.eval_js", "act", false, ["session_id", "expression"], "Evaluate JavaScript in the page."],
  ["browser.memory_get", "other", true, ["key"], "Read a stored memory entry."],
];
const INSTRUCTIONS =
  "Auto Browser lets you drive a real browser.\n\nWorkflow: browser.create_session -> browser.observe -> browser.execute_action (always with a reason) -> browser.close_session.\n\nWhen a tool result contains a `live_view` block, show its `banner` to the user verbatim before continuing.";

function shotSvg(id, n) {
  const hue = (n * 37) % 360;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="800" viewBox="0 0 1280 800">
<rect width="1280" height="800" fill="#fafafa"/><rect width="1280" height="64" fill="#e7e7e7"/>
<rect x="24" y="18" width="620" height="28" rx="6" fill="#fff" stroke="#ccc"/>
<text x="40" y="38" font-family="monospace" font-size="16" fill="#444">https://example.test/page-${n}</text>
<rect x="80" y="130" width="520" height="40" fill="hsl(${hue},25%,35%)"/>
<rect x="80" y="200" width="1100" height="14" fill="#ccc"/><rect x="80" y="230" width="980" height="14" fill="#ddd"/>
<rect x="80" y="260" width="1040" height="14" fill="#ddd"/><rect x="80" y="330" width="220" height="44" rx="6" fill="hsl(${hue},30%,45%)"/>
<text x="80" y="760" font-family="monospace" font-size="20" fill="#777">session ${id}  screenshot ${n}</text></svg>`;
}

// Fake live feed: multipart/x-mixed-replace of PNG frames (a moving block and a frame counter bar).
// Real controller sends image/jpeg parts; browsers accept any decodable type per part.
const crcTable = Array.from({ length: 256 }, (_, n) => {
  let c = n;
  for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
  return c >>> 0;
});
const crc32 = (buf) => {
  let c = 0xffffffff;
  for (const b of buf) c = crcTable[(c ^ b) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
};
function pngChunk(type, data) {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length);
  const body = Buffer.concat([Buffer.from(type), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(body));
  return Buffer.concat([len, body, crc]);
}
function framePng(n, W = 640, H = 400) {
  const raw = Buffer.alloc((W * 3 + 1) * H, 0xfa);
  const x0 = (n * 9) % (W - 80);
  for (let y = 0; y < H; y++) {
    const row = y * (W * 3 + 1);
    raw[row] = 0;
    for (let x = 0; x < W; x++) {
      const o = row + 1 + x * 3;
      let rgb = null;
      if (y < 32) rgb = [0xe7, 0xe7, 0xe7];
      else if (y >= 140 && y < 220 && x >= x0 && x < x0 + 80) rgb = [0xc8, 0x32, 0x32];
      else if (y >= 60 && y < 90 && x >= 20 && x < 20 + (n % 60) * 9) rgb = [0x33, 0x33, 0x33];
      if (rgb) { raw[o] = rgb[0]; raw[o + 1] = rgb[1]; raw[o + 2] = rgb[2]; }
    }
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(W, 0); ihdr.writeUInt32BE(H, 4); ihdr[8] = 8; ihdr[9] = 2;
  return Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), pngChunk("IHDR", ihdr), pngChunk("IDAT", zlib.deflateSync(raw)), pngChunk("IEND", Buffer.alloc(0))]);
}

function summaryFor(s) {
  const calls = s.events.filter((e) => e.type === "tool" && e.event === "start").length;
  const lastShot = [...s.events].reverse().find((e) => e.screenshot_url);
  return { ...s.summary, tool_calls: calls, last_screenshot_url: lastShot ? lastShot.screenshot_url : null };
}

function emit(s, ev) {
  ev.seq = ++s.seq;
  ev.ts = now();
  ev.session_id = s.summary.id;
  s.events.push(ev);
  const frame = `id: ${ev.seq}\ndata: ${JSON.stringify(ev)}\n\n`;
  for (const c of s.clients) c.write(frame);
  return ev;
}

let shotN = 0;
function call(s, tool, phase, args, ms, result, summary, { error = false, shot = false } = {}) {
  const call_id = hex(16);
  const base = { type: "tool", call_id, tool, phase, client: s.summary.client || undefined };
  emit(s, { ...base, event: "start", args });
  return new Promise((res) =>
    setTimeout(() => {
      if (s.closed) return res();
      const url = shot ? `/artifacts/${s.summary.id}/shot-${++shotN}.svg` : undefined;
      emit(s, { ...base, event: "end", status: error ? "error" : "ok", duration_ms: ms, result_summary: summary, result, screenshot_url: url });
      res();
    }, ms / SPEED),
  );
}
const wait = (ms) => new Promise((r) => setTimeout(r, ms / SPEED));

async function script(s) {
  const sid = s.summary.id;
  await wait(600);
  while (!s.closed) {
    await call(s, "browser.observe", "screenshot", { session_id: sid, preset: "fast" }, 640, { elements: 14, title: "Example Domain" }, "observed 14 elements", { shot: true });
    await wait(700);
    s.summary.current_url = "https://www.iana.org/help/example-domains";
    s.summary.title = "Example Domains";
    await call(s, "browser.execute_action", "act", { session_id: sid, action: { action: "click", element_id: "op-1", reason: "open link", text: "[redacted]", api_key: "[redacted]" } }, 812, { ok: true, url: s.summary.current_url }, "click ok, now at https://www.iana.org/help/example-domains");
    emit(s, { type: "observe", note: "unknown-to-ui event, must be ignored" });
    await wait(500);
    await call(s, "browser.observe", "read", { session_id: sid, preset: "text" }, 210, { text: "Example Domains. As described in RFC 2606 and RFC 6761..." }, "text 1.2k chars");
    await wait(600);
    await call(s, "browser.get_html", "read", { session_id: sid }, 95, { html: "<html><head>...[truncated]" }, "html 48kb");
    await wait(500);
    await call(s, "browser.execute_action", "act", { session_id: sid, action: { action: "scroll", delta_y: 600, reason: "read more" } }, 300, { ok: true }, "scroll ok");
    await wait(400);
    await call(s, "browser.screenshot", "screenshot", { session_id: sid }, 420, { width: 1280, height: 800 }, "screenshot 1280x800", { shot: true });
    await wait(500);
    await call(s, "browser.execute_action", "act", { session_id: sid, action: { action: "click", element_id: "op-99", reason: "missing element" } }, 1500, { error: "element op-99 not found" }, "element op-99 not found", { error: true });
    await wait(500);
    await call(s, "browser.list_tabs", "session", { session_id: sid }, 40, { tabs: [{ id: 0, url: s.summary.current_url }] }, "1 tab");
    await wait(900);
  }
}

function makeSession({ id = hex(), start_url = "https://example.com", live = true, client = "claude-code" } = {}) {
  const s = {
    summary: { id, name: null, state: live ? "live" : "archived", start_url, current_url: start_url, title: "Example Domain", created_at: now(), closed_at: null, live_url: `${UI}/s/${id}`, client },
    events: [], seq: 0, clients: new Set(), closed: !live,
  };
  sessions.set(id, s);
  return s;
}

function seedArchived() {
  const s = makeSession({ id: "3c81d0e2b7f4", live: false, client: "agy" });
  const t0 = Date.now() - 3600e3;
  s.summary.created_at = new Date(t0).toISOString();
  const mk = (i, ev) => s.events.push({ ...ev, seq: ++s.seq, ts: new Date(t0 + i * 2500).toISOString(), session_id: s.summary.id });
  const items = [
    ["browser.create_session", "session", {}, "session created", 320, false],
    ["browser.observe", "screenshot", { preset: "fast" }, "observed 9 elements", 700, true],
    ["browser.execute_action", "act", { action: { action: "click", element_id: "op-2", reason: "follow link" } }, "click ok", 640, false],
    ["browser.get_html", "read", {}, "html 32kb", 88, false],
    ["browser.close_session", "session", {}, "closed", 50, false],
  ];
  items.forEach(([tool, phase, args, sum, ms, shot], i) => {
    const call_id = hex(16);
    mk(i * 2, { type: "tool", event: "start", call_id, tool, phase, args, client: "agy" });
    mk(i * 2 + 1, { type: "tool", event: "end", call_id, tool, phase, status: "ok", duration_ms: ms, result_summary: sum, result: { ok: true }, screenshot_url: shot ? `/artifacts/${s.summary.id}/shot-a.svg` : undefined });
  });
  mk(20, { type: "session", state: "closed" });
  s.summary.closed_at = new Date(t0 + 60e3).toISOString();
}

function startLive(opts) {
  const s = makeSession(opts);
  script(s);
  return s;
}

const send = (res, code, body) => {
  res.writeHead(code, {
    "content-type": "application/json",
    "access-control-allow-origin": "*",
    "access-control-allow-headers": "*",
    "access-control-allow-methods": "GET,POST,OPTIONS",
  });
  res.end(code === 204 ? undefined : JSON.stringify(body));
};

const server = http.createServer((req, res) => {
  const u = new URL(req.url, `http://127.0.0.1:${PORT}`);
  const p = u.pathname;
  if (req.method === "OPTIONS") return send(res, 204, {});
  if (p === "/live-api/sessions" && req.method === "GET") {
    const list = [...sessions.values()].map(summaryFor).sort((a, b) => b.created_at.localeCompare(a.created_at));
    return send(res, 200, { sessions: list });
  }
  let m;
  if ((m = p.match(/^\/live-api\/sessions\/([^/]+)$/)) && req.method === "GET") {
    const s = sessions.get(m[1]);
    return s ? send(res, 200, summaryFor(s)) : send(res, 404, { detail: "not found" });
  }
  if (p === "/mock/stats") return send(res, 200, { stream_viewers: streamViewers });
  if ((m = p.match(/^\/live-api\/sessions\/([^/]+)\/stream$/))) {
    const s = sessions.get(m[1]);
    if (!s) return send(res, 404, { detail: "not found" });
    if (STREAM_OFF) return send(res, 503, { detail: "Live stream is disabled", state: "disabled" });
    if (s.closed) return send(res, 409, { detail: "archived; no live feed", state: "archived" });
    res.writeHead(200, { "content-type": "multipart/x-mixed-replace; boundary=frame", "cache-control": "no-store", "access-control-allow-origin": "*" });
    streamViewers++;
    let n = 0;
    const tick = setInterval(() => {
      const png = framePng(n++);
      res.write(["--frame", "Content-Type: image/png", `Content-Length: ${png.length}`, "", ""].join(CRLF));
      res.write(png);
      res.write(CRLF);
    }, 160);
    req.on("close", () => {
      clearInterval(tick);
      streamViewers--;
    });
    return;
  }
  if ((m = p.match(/^\/live-api\/sessions\/([^/]+)\/timeline$/))) {
    const s = sessions.get(m[1]);
    if (!s) return send(res, 404, { detail: "not found" });
    const after = Number(u.searchParams.get("after_seq") || 0);
    const limit = Math.min(2000, Number(u.searchParams.get("limit") || 500));
    const rest = s.events.filter((e) => e.seq > after);
    const events = rest.slice(0, limit);
    const last_seq = events.length ? events[events.length - 1].seq : after;
    return send(res, 200, { session: summaryFor(s), events, last_seq, has_more: rest.length > events.length });
  }
  if ((m = p.match(/^\/live-api\/sessions\/([^/]+)\/restart$/)) && req.method === "POST") {
    const s = sessions.get(m[1]);
    if (!s) return send(res, 404, { detail: "not found" });
    if (s.summary.state === "live") return send(res, 409, { detail: "session is still live" });
    const n = startLive({ start_url: s.summary.start_url, client: s.summary.client });
    return send(res, 200, { session: summaryFor(n) });
  }
  if (p === "/live-api/tools") {
    return send(res, 200, {
      tools: TOOLS.map(([name, phase, ro, required, description]) => ({ name, phase, read_only: ro, required, description })),
      instructions: INSTRUCTIONS,
    });
  }
  if ((m = p.match(/^\/sessions\/([^/]+)\/events$/))) {
    const s = sessions.get(m[1]);
    if (!s) return send(res, 404, { detail: "not found" });
    res.writeHead(200, { "content-type": "text/event-stream", "cache-control": "no-cache", connection: "keep-alive", "access-control-allow-origin": "*" });
    res.write(": ok\n\n");
    s.clients.add(res);
    const hb = setInterval(() => res.write(": hb\n\n"), 15000);
    req.on("close", () => {
      clearInterval(hb);
      s.clients.delete(res);
    });
    return;
  }
  if ((m = p.match(/^\/artifacts\/([^/]+)\/shot-([^.]+)\.svg$/))) {
    res.writeHead(200, { "content-type": "image/svg+xml", "access-control-allow-origin": "*" });
    return res.end(shotSvg(m[1], m[2] === "a" ? 7 : Number(m[2])));
  }
  send(res, 404, { detail: "no such route" });
});

function seedPaged() {
  // 1200 events (600 calls) -> 3 pages at the default limit of 500; also legacy junk without seq/type
  const s = makeSession({ id: "9a9a9a9a9a9a", live: false, client: "agy" });
  const t0 = Date.now() - 7200e3;
  s.summary.created_at = new Date(t0).toISOString();
  for (let i = 0; i < 600; i++) {
    const call_id = hex(16);
    const phase = ["read", "screenshot", "act"][i % 3];
    const tool = ["browser.get_html", "browser.screenshot", "browser.execute_action"][i % 3];
    s.events.push({ type: "tool", event: "start", call_id, tool, phase, args: { n: i }, seq: ++s.seq, ts: new Date(t0 + i * 1000).toISOString(), session_id: s.summary.id });
    s.events.push({ type: "tool", event: "end", call_id, tool, phase, status: "ok", duration_ms: 50 + (i % 7) * 10, result_summary: "ok " + i, result: { i }, seq: ++s.seq, ts: new Date(t0 + i * 1000 + 500).toISOString(), session_id: s.summary.id });
    if (i % 100 === 0) s.events.push({ event: "observe", timestamp: "legacy", status: "ok" });
  }
  s.summary.closed_at = new Date(t0 + 700e3).toISOString();
}

seedArchived();
seedPaged();
startLive({ id: "a5af842a89e1", start_url: "https://example.com" });
server.listen(PORT, "127.0.0.1", () => console.log(`mock controller on http://127.0.0.1:${PORT}`));
