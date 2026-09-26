import type { AnyEvent, CallRow, GuardEvent, GuardVerdict, ToolEvent } from "./types";

export type TimelineState = {
  rows: CallRow[]; // sorted by sortSeq ascending
  lastSeq: number; // highest seq seen across all event types
  closed: boolean; // a session event with state=closed was seen
};

export type TimelineAction =
  | { type: "reset" }
  | { type: "ingest"; events: AnyEvent[]; lastSeq?: number };

export const initialTimeline: TimelineState = { rows: [], lastSeq: 0, closed: false };

function isToolEvent(e: AnyEvent): e is ToolEvent {
  return (
    e.type === "tool" &&
    (e as ToolEvent).event !== undefined &&
    ((e as ToolEvent).event === "start" || (e as ToolEvent).event === "end") &&
    typeof e.seq === "number"
  );
}

const GUARD_VERDICTS: GuardVerdict[] = ["ALLOW", "REWRITE", "BLOCK", "ESCALATE"];

function isGuardEvent(e: AnyEvent): e is GuardEvent {
  return (
    e.type === "guard" &&
    typeof e.seq === "number" &&
    typeof (e as GuardEvent).call_id === "string" &&
    GUARD_VERDICTS.includes((e as GuardEvent).verdict)
  );
}

function guardTargetElement(e: GuardEvent): string | undefined {
  const t = e.target;
  if (t && typeof t === "object" && typeof (t as { element_id?: unknown }).element_id === "string") {
    return (t as { element_id: string }).element_id;
  }
  return undefined;
}

function applyGuard(row: CallRow, e: GuardEvent): CallRow {
  if (row.guard_seq === e.seq) return row; // duplicate
  // Last verdict wins when several guard events share a call_id (ingress + egress).
  return {
    ...row,
    tool: row.tool || (typeof e.tool === "string" && e.tool ? e.tool : row.tool),
    guard_verdict: e.verdict,
    guard_stage: e.stage === "ingress" || e.stage === "egress" ? e.stage : row.guard_stage,
    guard_mode: e.mode === "observe" || e.mode === "enforce" ? e.mode : row.guard_mode,
    guard_enforced: typeof e.enforced === "boolean" ? e.enforced : row.guard_enforced,
    guard_reason: typeof e.reason === "string" ? e.reason : row.guard_reason,
    guard_findings: Array.isArray(e.findings)
      ? (e.findings as GuardEvent["findings"])
      : row.guard_findings,
    guard_target_element: guardTargetElement(e) ?? row.guard_target_element,
    guard_seq: e.seq,
    guard_ts: e.ts,
  };
}

function newGuardStub(e: GuardEvent): CallRow {
  return {
    key: e.call_id,
    call_id: e.call_id,
    sortSeq: e.seq,
    tool: typeof e.tool === "string" && e.tool ? e.tool : "browser.unknown",
    phase: "other",
    status: "running",
    guard_verdict: e.verdict,
    guard_stage: e.stage === "ingress" || e.stage === "egress" ? e.stage : undefined,
    guard_mode: e.mode === "observe" || e.mode === "enforce" ? e.mode : undefined,
    guard_enforced: typeof e.enforced === "boolean" ? e.enforced : undefined,
    guard_reason: typeof e.reason === "string" ? e.reason : undefined,
    guard_findings: Array.isArray(e.findings) ? (e.findings as GuardEvent["findings"]) : undefined,
    guard_target_element: guardTargetElement(e),
    guard_seq: e.seq,
    guard_ts: e.ts,
  };
}

function newRow(e: ToolEvent): CallRow {
  return {
    key: e.call_id ?? `seq-${e.seq}`,
    call_id: e.call_id,
    sortSeq: e.seq,
    tool: e.tool,
    phase: e.phase ?? "other",
    client: e.client,
    status: "running",
  };
}

function applyEvent(row: CallRow, e: ToolEvent): CallRow {
  if (e.event === "start") {
    if (row.start_seq === e.seq) return row; // duplicate
    return {
      ...row,
      start_seq: e.seq,
      start_ts: e.ts,
      sortSeq: e.seq, // start defines position
      tool: e.tool,
      phase: e.phase ?? row.phase,
      args: e.args,
      client: e.client ?? row.client,
    };
  }
  if (row.end_seq === e.seq) return row; // duplicate
  return {
    ...row,
    end_seq: e.seq,
    end_ts: e.ts,
    sortSeq: row.start_seq !== undefined ? row.start_seq : e.seq,
    tool: row.tool || e.tool,
    phase: row.start_seq !== undefined ? row.phase : (e.phase ?? row.phase),
    status: e.status === "error" ? "error" : "ok",
    duration_ms: e.duration_ms,
    result_summary: e.result_summary,
    result: e.result,
    screenshot_url: e.screenshot_url,
    client: row.client ?? e.client,
  };
}

/**
 * Pure reducer. Merges events by seq, dedupes, pairs start/end by call_id.
 * A start without an end stays "running"; an end without a start still renders.
 * Guard verdicts (`type: "guard"`) attach to the row with the same call_id,
 * creating a stub row when no tool start/end has been seen yet.
 * Events of unknown type only advance lastSeq (and `session` closed sets closed),
 * so an old UI without guard support stays safe.
 */
export function timelineReducer(state: TimelineState, action: TimelineAction): TimelineState {
  if (action.type === "reset") return initialTimeline;

  let rows = state.rows;
  let lastSeq = state.lastSeq;
  let closed = state.closed;
  let changed = false;
  const index = new Map<string, number>();
  rows.forEach((r, i) => index.set(r.key, i));

  const ordered = [...(action.events ?? [])].sort((a, b) => ((a?.seq as number) || 0) - ((b?.seq as number) || 0));
  for (const e of ordered) {
    if (!e || typeof e !== "object" || typeof e.seq !== "number" || typeof e.type !== "string") continue;
    if (e.seq > lastSeq) lastSeq = e.seq;
    if (e.type === "session" && e.state === "closed") closed = true;
    if (isGuardEvent(e)) {
      const key = e.call_id;
      const at = index.get(key);
      if (at === undefined) {
        if (!changed) {
          rows = rows.slice();
          changed = true;
        }
        const stub = newGuardStub(e);
        rows.push(stub);
        index.set(key, rows.length - 1);
      } else {
        const next = applyGuard(rows[at], e);
        if (next === rows[at]) continue;
        if (!changed) {
          rows = rows.slice();
          changed = true;
        }
        rows[at] = next;
      }
      continue;
    }
    if (!isToolEvent(e)) continue;

    const key = e.call_id ?? `seq-${e.seq}`;
    const at = index.get(key);
    const base = at === undefined ? newRow(e) : rows[at];
    const next = applyEvent(base, e);
    if (at !== undefined && next === base) continue;
    if (!changed) {
      rows = rows.slice();
      changed = true;
    }
    if (at === undefined) {
      rows.push(next);
      index.set(key, rows.length - 1);
    } else {
      rows[at] = next;
    }
  }

  if (changed) rows.sort((a, b) => a.sortSeq - b.sortSeq);
  if (action.lastSeq !== undefined && action.lastSeq > lastSeq) lastSeq = action.lastSeq;
  if (!changed && lastSeq === state.lastSeq && closed === state.closed) return state;
  return { rows, lastSeq, closed };
}

export function countPhases(rows: CallRow[]) {
  const c = { read: 0, screenshot: 0, act: 0, session: 0, other: 0 };
  for (const r of rows) c[r.phase] = (c[r.phase] ?? 0) + 1;
  return c;
}

/**
 * Rows that produced a screenshot file: explicit screenshot/observe calls plus any row
 * (typically actions) carrying a screenshot_url, which the controller attaches for its
 * automatic captures around actions. Each row counts once.
 */
export function countCaptures(rows: CallRow[]): number {
  let n = 0;
  for (const r of rows) if (r.phase === "screenshot" || r.screenshot_url) n++;
  return n;
}

export type GuardCounts = {
  total: number;
  allow: number;
  rewrite: number;
  block: number;
  escalate: number;
  /** Rows where the guard intervened (rewrite, block or escalate). */
  intervened: number;
  /** Mode of the most recent guard verdict, when any guard event was seen. */
  mode?: string;
};

/** Counts guard verdicts across rows. Stub rows from guard-only events count too. */
export function countGuard(rows: CallRow[]): GuardCounts {
  const c: GuardCounts = { total: 0, allow: 0, rewrite: 0, block: 0, escalate: 0, intervened: 0 };
  for (const r of rows) {
    if (!r.guard_verdict) continue;
    c.total++;
    if (r.guard_mode) c.mode = r.guard_mode;
    switch (r.guard_verdict) {
      case "ALLOW":
        c.allow++;
        break;
      case "REWRITE":
        c.rewrite++;
        c.intervened++;
        break;
      case "BLOCK":
        c.block++;
        c.intervened++;
        break;
      case "ESCALATE":
        c.escalate++;
        c.intervened++;
        break;
    }
  }
  return c;
}

/** One-line summary of args for the row. */
export function summarizeArgs(args: unknown): string {
  if (args === null || args === undefined) return "";
  if (typeof args !== "object") return String(args);
  const a = args as Record<string, unknown>;
  const act = a.action;
  if (act && typeof act === "object") {
    const x = act as Record<string, unknown>;
    const parts = [x.action, x.element_id ?? x.selector ?? x.url, x.reason && `"${String(x.reason)}"`].filter(Boolean);
    if (parts.length) return parts.join(" ");
  }
  const entries = Object.entries(a).filter(([k]) => k !== "session_id");
  if (!entries.length) return "";
  return entries
    .map(([k, v]) => `${k}=${typeof v === "string" ? v : JSON.stringify(v)}`)
    .join(" ");
}
