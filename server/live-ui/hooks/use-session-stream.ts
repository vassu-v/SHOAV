"use client";

import { useEffect, useReducer, useRef, useState } from "react";
import { ApiError, eventsUrl, getSession, loadTimeline } from "@/lib/api";
import { initialTimeline, timelineReducer } from "@/lib/timeline";
import type { AnyEvent, SessionSummary } from "@/lib/types";

export type StreamStatus = "loading" | "live" | "reconnecting" | "archived" | "notfound" | "error";

const BACKOFF_BASE = 1000;
const BACKOFF_CAP = 15000;
const SUMMARY_POLL_MS = 3000;

export function backoffDelay(attempt: number) {
  return Math.min(BACKOFF_CAP, BACKOFF_BASE * 2 ** attempt);
}

/** State is per sessionId: mount the consumer with `key={sessionId}` so it starts fresh. */
export function useSessionStream(sessionId: string) {
  const [state, dispatch] = useReducer(timelineReducer, initialTimeline);
  const [session, setSession] = useState<SessionSummary | null>(null);
  const [status, setStatus] = useState<StreamStatus>("loading");
  const [error, setError] = useState<string | null>(null);
  const lastSeqRef = useRef(0);
  useEffect(() => {
    lastSeqRef.current = state.lastSeq;
  }, [state.lastSeq]);

  useEffect(() => {
    let cancelled = false;
    let es: EventSource | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    let pollTimer: ReturnType<typeof setInterval> | undefined;
    let attempt = 0;
    let first = true;

    const stopAll = () => {
      es?.close();
      es = null;
      if (retryTimer) clearTimeout(retryTimer);
      if (pollTimer) clearInterval(pollTimer);
      retryTimer = pollTimer = undefined;
    };

    const archive = (s: SessionSummary) => {
      stopAll();
      setSession(s);
      setStatus("archived");
    };

    const scheduleRetry = () => {
      if (cancelled) return;
      setStatus("reconnecting");
      const delay = backoffDelay(attempt++);
      retryTimer = setTimeout(connect, delay);
    };

    const startPolling = () => {
      if (pollTimer) return;
      pollTimer = setInterval(async () => {
        try {
          const s = await getSession(sessionId);
          if (cancelled) return;
          if (s.state === "archived") {
            // pick up any trailing events, then freeze
            const sess = await loadTimeline(sessionId, lastSeqRef.current, (t) => {
              if (cancelled) return;
              lastSeqRef.current = Math.max(lastSeqRef.current, t.last_seq ?? 0);
              dispatch({ type: "ingest", events: t.events ?? [], lastSeq: t.last_seq });
            });
            if (cancelled) return;
            archive(sess);
          } else setSession(s);
        } catch {
          // the SSE handler owns the reconnecting state
        }
      }, SUMMARY_POLL_MS);
    };

    // race rule: timeline first (after last seen seq), then open SSE.
    async function connect() {
      if (cancelled) return;
      try {
        const sess = await loadTimeline(sessionId, lastSeqRef.current, (t) => {
          if (cancelled) return;
          lastSeqRef.current = Math.max(lastSeqRef.current, t.last_seq ?? 0);
          dispatch({ type: "ingest", events: t.events ?? [], lastSeq: t.last_seq });
        });
        if (cancelled) return;
        setSession(sess);
        setError(null);
        if (sess.state === "archived") return archive(sess);
        first = false;
        openStream();
      } catch (e) {
        if (cancelled) return;
        if (e instanceof ApiError && e.status === 404) {
          stopAll();
          setStatus("notfound");
          return;
        }
        if (first) {
          setError(e instanceof Error ? e.message : String(e));
          first = false;
          setStatus("error");
          // keep trying quietly so the page recovers if the controller comes up
          retryTimer = setTimeout(connect, backoffDelay(attempt++));
          return;
        }
        scheduleRetry();
      }
    }

    function openStream() {
      es?.close();
      const source = new EventSource(eventsUrl(sessionId));
      es = source;
      source.onopen = () => {
        if (cancelled || es !== source) return;
        attempt = 0;
        setStatus("live");
        startPolling();
      };
      source.onmessage = (m) => {
        if (cancelled || es !== source) return;
        try {
          const ev = JSON.parse(m.data) as AnyEvent;
          dispatch({ type: "ingest", events: [ev] });
          if (ev.type === "session" && ev.state === "closed") {
            getSession(sessionId).then((s) => !cancelled && archive(s), () => {});
          }
        } catch {
          // ignore malformed frames
        }
      };
      source.onerror = () => {
        if (cancelled || es !== source) return;
        source.close();
        es = null;
        scheduleRetry();
      };
    }

    connect();
    return () => {
      cancelled = true;
      stopAll();
    };
  }, [sessionId]);

  return { state, session, status, error };
}
