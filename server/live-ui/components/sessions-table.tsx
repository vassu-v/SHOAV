"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { listSessions, CONTROLLER_URL } from "@/lib/api";
import type { SessionSummary } from "@/lib/types";
import { fmtAge } from "@/lib/format";
import { CopyButton, Message, StateBadge, useNow } from "@/components/ui-bits";
import { Skeleton } from "@/components/ui/skeleton";

export function SessionsTable() {
  const [sessions, setSessions] = useState<SessionSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const now = useNow(5000);
  const router = useRouter();

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const r = await listSessions();
        if (cancelled) return;
        setSessions(r.sessions);
        setError(null);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      }
    };
    load();
    const t = setInterval(load, 3000);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, []);

  const sorted = sessions
    ? [...sessions].sort((a, b) => Number(b.state === "live") - Number(a.state === "live") || b.created_at.localeCompare(a.created_at))
    : null;

  return (
    <div>
      <div className="mb-3 flex items-baseline justify-between">
        <h1 className="text-base font-medium">Sessions</h1>
        <span className="font-mono text-xs text-muted-foreground">{CONTROLLER_URL}</span>
      </div>

      {error && (
        <div role="alert" className="mb-3 rounded-md border border-destructive/40 px-3 py-2 text-destructive">
          {error}. {sorted ? "Showing last known data, retrying." : "Retrying every 3s."}
        </div>
      )}

      {!sorted && !error && (
        <div className="space-y-1">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-9 w-full" />
          ))}
        </div>
      )}

      {sorted && sorted.length === 0 && (
        <Message title="No sessions yet">When an agent calls browser.create_session, it appears here with a live link.</Message>
      )}

      {sorted && sorted.length > 0 && (
        <div className="overflow-x-auto rounded-md border">
          <table className="w-full min-w-[760px] border-collapse text-left">
            <thead>
              <tr className="border-b text-xs text-muted-foreground">
                <th className="h-8 px-3 font-normal">State</th>
                <th className="px-3 font-normal">Session</th>
                <th className="w-full px-3 font-normal">Page</th>
                <th className="px-3 text-right font-normal">Calls</th>
                <th className="px-3 text-right font-normal">Age</th>
                <th className="px-3 font-normal">Client</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((s) => (
                <tr
                  key={s.id}
                  tabIndex={0}
                  onClick={() => router.push(`/s/${s.id}`)}
                  onKeyDown={(e) => e.key === "Enter" && router.push(`/s/${s.id}`)}
                  className="cursor-pointer border-b last:border-0 hover:bg-muted/60 focus-visible:bg-muted/60 focus-visible:outline-none"
                >
                  <td className="h-9 px-3">
                    <StateBadge state={s.state} />
                  </td>
                  <td className="px-3">
                    <span className="inline-flex items-center gap-1 font-mono text-xs">
                      {s.id}
                      <CopyButton value={s.id} label="Copy session id" />
                    </span>
                  </td>
                  <td className="max-w-0 px-3">
                    <div className="truncate">{s.title || <span className="text-muted-foreground">untitled</span>}</div>
                    <div className="truncate font-mono text-xs text-muted-foreground">{s.current_url || s.start_url || ""}</div>
                  </td>
                  <td className="tnum px-3 text-right">{s.tool_calls}</td>
                  <td className="tnum px-3 text-right text-muted-foreground">{fmtAge(s.created_at, now)}</td>
                  <td className="px-3 font-mono text-xs whitespace-nowrap text-muted-foreground">{s.client || "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
