import { describe, expect, it } from "vitest";
import { loadTimeline } from "./api";
import { countCaptures, countGuard, countPhases, initialTimeline, summarizeArgs, timelineReducer } from "./timeline";
import type { AnyEvent } from "./types";

const base = { session_id: "s1", ts: "2026-01-01T00:00:00Z" };
const start = (seq: number, call_id: string, extra: object = {}): AnyEvent => ({
  ...base, type: "tool", event: "start", seq, call_id, tool: "browser.observe", phase: "screenshot", args: { a: 1 }, ...extra,
});
const end = (seq: number, call_id: string, extra: object = {}): AnyEvent => ({
  ...base, type: "tool", event: "end", seq, call_id, tool: "browser.observe", phase: "screenshot",
  status: "ok", duration_ms: 42, result_summary: "done", ...extra,
});
const ingest = (s = initialTimeline, events: AnyEvent[]) => timelineReducer(s, { type: "ingest", events });

describe("timelineReducer", () => {
  it("orders rows by seq even when events arrive out of order", () => {
    const s = ingest(initialTimeline, [start(5, "c"), start(1, "a"), start(3, "b")]);
    expect(s.rows.map((r) => r.call_id)).toEqual(["a", "b", "c"]);
    expect(s.lastSeq).toBe(5);
  });

  it("dedupes repeated events by seq (timeline then SSE overlap)", () => {
    let s = ingest(initialTimeline, [start(1, "a"), end(2, "a")]);
    const again = ingest(s, [start(1, "a"), end(2, "a")]);
    expect(again).toBe(s); // no change, same reference
    s = ingest(s, [end(2, "a"), start(3, "b")]);
    expect(s.rows).toHaveLength(2);
  });

  it("pairs start and end by call_id; start alone is running", () => {
    let s = ingest(initialTimeline, [start(1, "a")]);
    expect(s.rows[0].status).toBe("running");
    s = ingest(s, [end(2, "a", { screenshot_url: "/x.png" })]);
    expect(s.rows).toHaveLength(1);
    expect(s.rows[0]).toMatchObject({ status: "ok", duration_ms: 42, screenshot_url: "/x.png", args: { a: 1 }, sortSeq: 1 });
  });

  it("renders an end with no start, and pairs a late start", () => {
    let s = ingest(initialTimeline, [end(4, "z", { status: "error", result_summary: "boom" })]);
    expect(s.rows).toHaveLength(1);
    expect(s.rows[0]).toMatchObject({ status: "error", result_summary: "boom" });
    s = ingest(s, [start(3, "z")]);
    expect(s.rows).toHaveLength(1);
    expect(s.rows[0].args).toEqual({ a: 1 });
    expect(s.rows[0].sortSeq).toBe(3);
  });

  it("fills gaps when a later timeline fetch delivers missing events", () => {
    let s = ingest(initialTimeline, [start(1, "a"), end(2, "a"), start(5, "c")]);
    s = ingest(s, [start(3, "b"), end(4, "b"), start(5, "c"), end(6, "c")]);
    expect(s.rows.map((r) => [r.call_id, r.status])).toEqual([["a", "ok"], ["b", "ok"], ["c", "ok"]]);
    expect(s.lastSeq).toBe(6);
  });

  it("ignores unknown event types but tracks seq; session closed sets closed", () => {
    let s = ingest(initialTimeline, [{ ...base, type: "observe", seq: 7 }, { ...base, type: "weird", seq: 8 }]);
    expect(s.rows).toHaveLength(0);
    expect(s.lastSeq).toBe(8);
    expect(s.closed).toBe(false);
    s = ingest(s, [{ ...base, type: "session", seq: 9, state: "closed" }]);
    expect(s.closed).toBe(true);
  });

  it("uses lastSeq from the timeline response and resets", () => {
    const s = timelineReducer(initialTimeline, { type: "ingest", events: [], lastSeq: 12 });
    expect(s.lastSeq).toBe(12);
    expect(timelineReducer(s, { type: "reset" })).toEqual(initialTimeline);
  });
});

describe("helpers", () => {
  it("counts phases", () => {
    const s = ingest(initialTimeline, [start(1, "a"), start(2, "b", { phase: "act" })]);
    expect(countPhases(s.rows)).toMatchObject({ screenshot: 1, act: 1, read: 0 });
  });
  it("summarizes args", () => {
    expect(summarizeArgs({ session_id: "x", action: { action: "click", element_id: "op-1", reason: "go" } })).toBe('click op-1 "go"');
    expect(summarizeArgs({ session_id: "x", preset: "text" })).toBe("preset=text");
    expect(summarizeArgs(undefined)).toBe("");
  });
});

describe("legacy and malformed events", () => {
  it("ignores events without numeric seq or type", () => {
    const legacy = [
      { event: "observe", timestamp: "t", status: "ok" },
      { type: "tool", event: "start", call_id: "x" },
      { seq: 3, ts: "t" },
      null,
    ] as unknown as AnyEvent[];
    const s = ingest(initialTimeline, [...legacy, start(2, "a")]);
    expect(s.rows).toHaveLength(1);
    expect(s.lastSeq).toBe(2);
  });
});

describe("loadTimeline pagination", () => {
  it("follows has_more across 3 pages and stops", async () => {
    const all = [1, 2, 3, 4, 5, 6].map((n) => start(n, `c${n}`));
    const calls: number[] = [];
    const fetchPage = async (_id: string, after: number) => {
      calls.push(after);
      const events = all.filter((e) => e.seq > after).slice(0, 2);
      const last = events.length ? events[events.length - 1].seq : after;
      return { session: { id: "s1" } as never, events, last_seq: last, has_more: last < 6 };
    };
    let state = initialTimeline;
    await loadTimeline("s1", 0, (t) => { state = timelineReducer(state, { type: "ingest", events: t.events, lastSeq: t.last_seq }); }, fetchPage);
    expect(calls).toEqual([0, 2, 4]);
    expect(state.rows).toHaveLength(6);
    expect(state.lastSeq).toBe(6);
  });
});

describe("countCaptures", () => {
  it("counts screenshot-phase rows and rows carrying a screenshot_url once each", () => {
    const s = ingest(initialTimeline, [
      start(1, "a"), end(2, "a", { screenshot_url: "/artifacts/s1/x-manual.png" }), // screenshot call with a file
      start(3, "b"), end(4, "b", { status: "error", screenshot_url: undefined }), // screenshot call, no file yet
      start(5, "c", { tool: "browser.execute_action", phase: "act" }),
      end(6, "c", { tool: "browser.execute_action", phase: "act", screenshot_url: "/artifacts/s1/x-after-click.png" }), // automatic capture
      start(7, "d", { tool: "browser.get_html", phase: "read" }), end(8, "d", { tool: "browser.get_html", phase: "read" }),
    ]);
    expect(countCaptures(s.rows)).toBe(3);
    expect(countPhases(s.rows).screenshot).toBe(2);
  });
});

describe("guard events", () => {
  const guard = (seq: number, call_id: string, extra: object = {}): AnyEvent => ({
    ...base,
    type: "guard",
    event: "verdict",
    seq,
    call_id,
    tool: "browser.observe",
    stage: "ingress",
    verdict: "REWRITE",
    mode: "enforce",
    enforced: true,
    reason: "removed hidden text",
    findings: [{ kind: "hidden_text", detail: "div.hidden" }],
    ...extra,
  });

  it("attaches a verdict to the matching call_id", () => {
    let s = ingest(initialTimeline, [start(1, "a"), end(2, "a")]);
    s = ingest(s, [guard(3, "a")]);
    expect(s.rows).toHaveLength(1);
    expect(s.rows[0]).toMatchObject({
      call_id: "a",
      guard_verdict: "REWRITE",
      guard_stage: "ingress",
      guard_mode: "enforce",
      guard_enforced: true,
      guard_reason: "removed hidden text",
    });
    expect(s.lastSeq).toBe(3);
  });

  it("creates a stub row when the guard event arrives before any tool event", () => {
    let s = ingest(initialTimeline, [guard(2, "g1", { verdict: "BLOCK", stage: "egress", tool: "browser.execute_action", target: { element_id: "op-s4" } })]);
    expect(s.rows).toHaveLength(1);
    expect(s.rows[0]).toMatchObject({
      call_id: "g1",
      tool: "browser.execute_action",
      status: "running",
      guard_verdict: "BLOCK",
      guard_target_element: "op-s4",
    });
    // a late tool start pairs into the same stub row and defines its position
    s = ingest(s, [start(1, "g1", { tool: "browser.execute_action", phase: "act" })]);
    expect(s.rows).toHaveLength(1);
    expect(s.rows[0].sortSeq).toBe(1);
    expect(s.rows[0].phase).toBe("act");
    expect(s.rows[0].guard_verdict).toBe("BLOCK");
  });

  it("dedupes repeated guard events and lets the last verdict win", () => {
    let s = ingest(initialTimeline, [start(1, "a"), guard(3, "a")]);
    const same = ingest(s, [guard(3, "a")]);
    expect(same).toBe(s);
    s = ingest(s, [guard(4, "a", { verdict: "ALLOW", reason: "clean on recheck" })]);
    expect(s.rows[0].guard_verdict).toBe("ALLOW");
    expect(s.rows[0].guard_seq).toBe(4);
  });

  it("ignores guard events with an unknown verdict but still tracks seq", () => {
    const s = ingest(initialTimeline, [{ ...base, type: "guard", event: "verdict", seq: 5, call_id: "x", verdict: "QUARANTINE" }]);
    expect(s.rows).toHaveLength(0);
    expect(s.lastSeq).toBe(5);
  });

  it("counts guard verdicts", () => {
    const s = ingest(initialTimeline, [
      start(1, "a"), guard(2, "a", { verdict: "ALLOW", mode: "observe" }),
      start(3, "b"), guard(4, "b", { verdict: "REWRITE", mode: "enforce" }),
      guard(5, "c", { verdict: "BLOCK", mode: "enforce", tool: "browser.execute_action" }),
      guard(6, "d", { verdict: "ESCALATE", mode: "enforce", tool: "browser.execute_action" }),
    ]);
    expect(countGuard(s.rows)).toMatchObject({
      total: 4, allow: 1, rewrite: 1, block: 1, escalate: 1, intervened: 3, mode: "enforce",
    });
    expect(countGuard([])).toMatchObject({ total: 0, intervened: 0 });
  });
});
