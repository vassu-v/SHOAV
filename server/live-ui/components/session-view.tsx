"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { RotateCcw } from "lucide-react";
import { useSessionStream } from "@/hooks/use-session-stream";
import { ApiError, resolveUrl, restartSession } from "@/lib/api";
import { countCaptures, countGuard, countPhases } from "@/lib/timeline";
import { fmtDateTime, fmtElapsed, fmtTime } from "@/lib/format";
import type { CallRow } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { FeedChip, LiveFeed, type FeedStatus } from "@/components/live-feed";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { CopyButton, GuardChip, Message, StateBadge, useNow, type ViewState } from "@/components/ui-bits";
import { TimelineList } from "@/components/timeline-list";
import { ToolsPanel } from "@/components/tools-panel";

function Stat({ label, value, hint }: { label: string; value: number; hint?: string }) {
  const body = (
    <span className="inline-flex items-baseline gap-1.5">
      <span className="tnum font-mono text-sm">{value}</span>
      <span className={hint ? "text-xs text-muted-foreground underline decoration-dotted underline-offset-2" : "text-xs text-muted-foreground"}>
        {label}
      </span>
    </span>
  );
  if (!hint) return body;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span tabIndex={0} className="cursor-default" data-testid={`stat-${label}`}>
          {body}
        </span>
      </TooltipTrigger>
      <TooltipContent className="max-w-64">{hint}</TooltipContent>
    </Tooltip>
  );
}

const CAPTURES_HINT =
  "Screenshot files for this session: screenshots the agent asked for (screenshot or observe calls) plus captures the controller takes automatically around actions. Each tool call counts once.";

export function SessionView({ sessionId }: { sessionId: string }) {
  const { state, session, status, error } = useSessionStream(sessionId);
  const router = useRouter();
  const [previewRow, setPreviewRow] = useState<CallRow | null>(null);
  const [mode, setMode] = useState<"live" | "captures">("live");
  const [feedStatus, setFeedStatus] = useState<FeedStatus>("connecting");
  const [restarting, setRestarting] = useState(false);
  const [restartError, setRestartError] = useState<string | null>(null);
  const isLive = status === "live" || status === "reconnecting";
  const now = useNow(1000, isLive);

  const counts = useMemo(() => countPhases(state.rows), [state.rows]);
  const captures = useMemo(() => countCaptures(state.rows), [state.rows]);
  const guard = useMemo(() => countGuard(state.rows), [state.rows]);
  const latest = useMemo(() => {
    for (let i = state.rows.length - 1; i >= 0; i--) if (state.rows[i].screenshot_url) return state.rows[i];
    return null;
  }, [state.rows]);

  if (status === "notfound")
    return (
      <div className="max-w-md">
        <Message title="Session not found">
          <span className="font-mono">{sessionId}</span> does not exist on this controller.{" "}
          <Link href="/" className="underline underline-offset-2">Back to sessions</Link>
        </Message>
      </div>
    );

  if (status === "error" && !session)
    return (
      <div className="max-w-xl space-y-2">
        <div role="alert" className="rounded-md border border-destructive/40 px-3 py-2 text-destructive">
          Could not load session: {error}. Retrying.
        </div>
        <Link href="/" className="text-muted-foreground underline underline-offset-2">Back to sessions</Link>
      </div>
    );

  if (!session)
    return (
      <div className="space-y-3">
        <Skeleton className="h-16 w-full" />
        <div className="grid gap-4 lg:grid-cols-[3fr_2fr]">
          <Skeleton className="aspect-[16/10] w-full" />
          <Skeleton className="h-96 w-full" />
        </div>
      </div>
    );

  const viewState: ViewState = status === "reconnecting" ? "reconnecting" : session.state === "live" ? "live" : "archived";
  const archived = session.state === "archived";
  const endMs = archived && session.closed_at ? new Date(session.closed_at).getTime() : now;
  const shotPath = previewRow?.screenshot_url ?? latest?.screenshot_url ?? session.last_screenshot_url;
  const showLive = !archived && mode === "live" && !previewRow;
  const shotSrc = resolveUrl(shotPath);
  const shotTs = previewRow ? previewRow.end_ts : latest?.end_ts;

  const restart = async () => {
    setRestarting(true);
    setRestartError(null);
    try {
      const r = await restartSession(session.id);
      router.push(`/s/${r.session.id}`);
    } catch (e) {
      setRestartError(
        e instanceof ApiError && e.status === 409
          ? "This session is still live, so it cannot be restarted."
          : `Restart failed: ${e instanceof Error ? e.message : String(e)}`,
      );
      setRestarting(false);
    }
  };

  return (
    <div className="flex flex-col gap-3 lg:h-[calc(100vh-5.5rem)]">
      <div className="space-y-1.5">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
          <span className="inline-flex items-center gap-1 font-mono text-sm font-medium">
            {session.id}
            <CopyButton value={session.id} label="Copy session id" />
          </span>
          <StateBadge state={viewState} />
          {(guard.total > 0 || guard.mode) && (
            <GuardChip mode={guard.mode} blocked={guard.block} rewritten={guard.rewrite} escalated={guard.escalate} />
          )}
          <span className="tnum font-mono text-xs text-muted-foreground" title="elapsed">
            {fmtElapsed(session.created_at, endMs)}
          </span>
          {session.client && <span className="font-mono text-xs text-muted-foreground">{session.client}</span>}
          <span className="ml-auto flex items-center gap-4">
            <Stat label="reads" value={counts.read} />
            <TooltipProvider>
              <Stat label="captures" value={captures} hint={CAPTURES_HINT} />
            </TooltipProvider>
            <Stat label="acts" value={counts.act} />
          </span>
        </div>
        <div className="grid gap-x-6 gap-y-0.5 text-xs sm:grid-cols-[auto_1fr]">
          <div className="min-w-0 sm:col-span-2">
            <span className="text-muted-foreground">now </span>
            <span className="font-mono break-all">{session.current_url || "-"}</span>
            {session.title && <span className="text-muted-foreground"> · {session.title}</span>}
          </div>
          <div className="min-w-0 sm:col-span-2">
            <span className="text-muted-foreground">start </span>
            <span className="font-mono break-all text-muted-foreground">{session.start_url || "-"}</span>
          </div>
        </div>
        {status === "reconnecting" && (
          <div role="status" className="rounded-md border border-destructive/40 px-3 py-1.5 text-destructive">
            Connection to the controller lost. Reconnecting, missed events will be filled in.
          </div>
        )}
      </div>

      {archived && (
        <div className="flex flex-wrap items-center gap-3 rounded-md border px-3 py-2" data-testid="archived-banner">
          <span>
            This session ended <span className="tnum font-mono">{fmtDateTime(session.closed_at)}</span>. Read-only.
          </span>
          <Button size="sm" variant="outline" onClick={restart} disabled={restarting} className="ml-auto">
            <RotateCcw className="size-3.5" /> {restarting ? "Restarting..." : "Restart session"}
          </Button>
          {restartError && (
            <div role="alert" className="w-full text-destructive">
              {restartError}
            </div>
          )}
        </div>
      )}

      <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <section className="min-w-0 space-y-2 lg:overflow-y-auto">
          <div className="flex h-6 items-center justify-between gap-2 text-xs text-muted-foreground">
            <span className="flex min-w-0 items-center gap-3">
              {!archived && (
                <span className="inline-flex shrink-0 rounded-md border p-px" role="group" aria-label="Preview source">
                  <Button
                    size="xs"
                    variant={showLive ? "secondary" : "ghost"}
                    aria-pressed={showLive}
                    onClick={() => {
                      setPreviewRow(null);
                      setMode("live");
                    }}
                  >
                    Live
                  </Button>
                  <Button
                    size="xs"
                    variant={!showLive ? "secondary" : "ghost"}
                    aria-pressed={!showLive}
                    onClick={() => setMode("captures")}
                  >
                    Captures
                  </Button>
                </span>
              )}
              {showLive ? (
                <FeedChip status={feedStatus} />
              ) : previewRow ? (
                <span className="truncate">
                  Capture from <span className="font-mono">{previewRow.tool.replace(/^browser\./, "")}</span> at{" "}
                  <span className="tnum font-mono">{fmtTime(previewRow.end_ts)}</span>
                </span>
              ) : shotSrc ? (
                <span className="truncate">
                  Latest capture{shotTs && (
                    <>
                      {" "}at <span className="tnum font-mono">{fmtTime(shotTs)}</span>
                    </>
                  )}
                </span>
              ) : (
                <span>Captures</span>
              )}
            </span>
            {previewRow && !archived && (
              <Button size="xs" variant="ghost" onClick={() => { setPreviewRow(null); setMode("live"); }}>
                Back to live
              </Button>
            )}
            {previewRow && archived && (
              <Button size="xs" variant="ghost" onClick={() => setPreviewRow(null)}>
                Latest capture
              </Button>
            )}
          </div>
          {showLive ? (
            <LiveFeed sessionId={session.id} fallbackSrc={shotSrc} onStatus={setFeedStatus} />
          ) : shotSrc ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={shotSrc} alt="Browser capture" className="w-full rounded-md border bg-muted/30" />
          ) : (
            <div className="flex aspect-[16/10] w-full items-center justify-center rounded-md border border-dashed text-muted-foreground">
              No capture yet. The first observe or screenshot call will show up here.
            </div>
          )}
        </section>

        <section className="flex min-h-0 min-w-0 flex-col">
          <Tabs defaultValue="timeline" className="flex min-h-0 flex-1 flex-col gap-2">
            <TabsList variant="line" className="self-start">
              <TabsTrigger value="timeline">Timeline</TabsTrigger>
              <TabsTrigger value="tools">Tools</TabsTrigger>
            </TabsList>
            <TabsContent value="timeline" className="flex min-h-0 flex-1 flex-col max-lg:h-[70vh] max-lg:flex-none">
              <TimelineList rows={state.rows} live={isLive} selectedKey={previewRow?.key ?? null} onSelect={(r) => { setPreviewRow(r); setMode("captures"); }} />
            </TabsContent>
            <TabsContent value="tools" className="flex min-h-0 flex-1 flex-col max-lg:h-[70vh] max-lg:flex-none">
              <ToolsPanel />
            </TabsContent>
          </Tabs>
        </section>
      </div>
    </div>
  );
}
