import type { SessionSummary, TimelineResponse, ToolsResponse } from "./types";

export const CONTROLLER_URL = (process.env.NEXT_PUBLIC_CONTROLLER_URL || "http://127.0.0.1:18500").trim().replace(/\/+$/, "");

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export function resolveUrl(path: string | null | undefined): string | null {
  if (!path) return null;
  if (/^https?:\/\//i.test(path) || path.startsWith("data:")) return path;
  return CONTROLLER_URL + (path.startsWith("/") ? path : "/" + path);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(CONTROLLER_URL + path, { cache: "no-store", ...init });
  } catch {
    throw new ApiError(0, `Cannot reach controller at ${CONTROLLER_URL}`);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const j = await res.json();
      detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j);
    } catch {}
    throw new ApiError(res.status, detail || `HTTP ${res.status}`);
  }
  return (await res.json()) as T;
}

export const listSessions = () => request<{ sessions: SessionSummary[] }>("/live-api/sessions");
export const getSession = (id: string) => request<SessionSummary>(`/live-api/sessions/${encodeURIComponent(id)}`);
export const getTimeline = (id: string, afterSeq = 0, limit = 500) =>
  request<TimelineResponse>(`/live-api/sessions/${encodeURIComponent(id)}/timeline?after_seq=${afterSeq}&limit=${limit}`);
export const getTools = () => request<ToolsResponse>("/live-api/tools");
export type GuardStatus = {
  mode: string;
  version: string;
  counters: { allow: number; rewrite: number; block: number; escalate: number };
};
export const getGuard = () => request<GuardStatus>("/live-api/guard");
export const restartSession = (id: string) =>
  request<{ session: SessionSummary }>(`/live-api/sessions/${encodeURIComponent(id)}/restart`, { method: "POST" });
/** MJPEG feed for an <img>. `n` changes on reconnect so the browser opens a new request. */
export const streamUrl = (id: string, n = 0) => `${CONTROLLER_URL}/live-api/sessions/${encodeURIComponent(id)}/stream?n=${n}`;
export const eventsUrl = (id: string) => `${CONTROLLER_URL}/sessions/${encodeURIComponent(id)}/events`;

/** Follows has_more pages (oldest first). onPage is called per page; returns the last page's session. */
export async function loadTimeline(
  id: string,
  afterSeq: number,
  onPage: (t: TimelineResponse) => void,
  fetchPage: (id: string, after: number) => Promise<TimelineResponse> = getTimeline,
): Promise<TimelineResponse["session"]> {
  let after = afterSeq;
  for (let guard = 0; guard < 1000; guard++) {
    const t = await fetchPage(id, after);
    onPage(t);
    const next = typeof t.last_seq === "number" ? t.last_seq : after;
    if (!t.has_more || next <= after) return t.session;
    after = next;
  }
  throw new ApiError(0, "timeline pagination did not terminate");
}
