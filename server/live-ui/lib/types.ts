export type Phase = "read" | "screenshot" | "act" | "session" | "other";
export const PHASES: Phase[] = ["read", "screenshot", "act", "session", "other"];

export type SessionSummary = {
  id: string;
  name: string | null;
  state: "live" | "archived";
  start_url: string | null;
  current_url: string | null;
  title: string | null;
  created_at: string;
  closed_at: string | null;
  tool_calls: number;
  last_screenshot_url: string | null;
  live_url: string;
  client: string | null;
};

export type ToolEvent = {
  type: "tool";
  event: "start" | "end";
  call_id?: string;
  seq: number;
  ts: string;
  session_id: string;
  tool: string;
  phase: Phase;
  args?: unknown;
  client?: string;
  status?: "ok" | "error";
  duration_ms?: number;
  result_summary?: string;
  result?: unknown;
  screenshot_url?: string;
};

/** Guard verdict for a tool call, emitted as a separate `type: "guard"` event. */
export type GuardVerdict = "ALLOW" | "REWRITE" | "BLOCK" | "ESCALATE";

export type GuardStage = "ingress" | "egress";

export type GuardMode = "observe" | "enforce";

export type GuardFinding = {
  kind: string;
  detail?: string;
};

export type GuardEvent = {
  type: "guard";
  event: "verdict";
  call_id: string;
  seq: number;
  ts: string;
  session_id?: string;
  stage?: GuardStage;
  tool?: string;
  verdict: GuardVerdict;
  mode?: GuardMode;
  enforced?: boolean;
  reason?: string;
  findings?: GuardFinding[];
  target?: { element_id?: string; [k: string]: unknown } | null;
};

/** Any event. Unknown types are tolerated and ignored by the reducer. */
export type AnyEvent = { type: string; seq: number; ts: string; session_id?: string; [k: string]: unknown };

export type TimelineResponse = { session: SessionSummary; events: AnyEvent[]; last_seq: number; has_more?: boolean };

export type ToolDef = { name: string; description: string; phase: Phase; read_only: boolean; required: string[] };
export type ToolsResponse = { tools: ToolDef[]; instructions: string };

export type CallStatus = "running" | "ok" | "error";

/** One start/end pair rendered as a single row. */
export type CallRow = {
  key: string;
  call_id?: string;
  sortSeq: number;
  start_seq?: number;
  end_seq?: number;
  start_ts?: string;
  end_ts?: string;
  tool: string;
  phase: Phase;
  args?: unknown;
  client?: string;
  status: CallStatus;
  duration_ms?: number;
  result_summary?: string;
  result?: unknown;
  screenshot_url?: string;
  // Guard verdict attached by call_id. Set when a `type: "guard"` event arrives.
  guard_verdict?: GuardVerdict;
  guard_stage?: GuardStage;
  guard_mode?: GuardMode;
  guard_enforced?: boolean;
  guard_reason?: string;
  guard_findings?: GuardFinding[];
  guard_target_element?: string;
  guard_seq?: number;
  guard_ts?: string;
};
