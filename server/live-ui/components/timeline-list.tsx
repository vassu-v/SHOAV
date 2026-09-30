"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { ArrowDown, Check, ChevronRight, ImageIcon, X } from "lucide-react";
import type { CallRow, Phase } from "@/lib/types";
import { countGuard, countPhases, summarizeArgs } from "@/lib/timeline";
import { fmtDuration, fmtTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { CopyButton, GuardBadge, PhaseChip, Spinner } from "@/components/ui-bits";

type Filter = "all" | Exclude<Phase, "other"> | "guard";
const FILTERS: Filter[] = ["all", "read", "screenshot", "act", "session", "guard"];

function Json({ label, value }: { label: string; value: unknown }) {
  const text = JSON.stringify(value, null, 2) ?? "undefined";
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-xs text-muted-foreground">
        <span>{label}</span>
        <CopyButton value={text} label={`Copy ${label}`} />
      </div>
      <pre className="max-h-64 overflow-auto rounded border bg-muted/40 p-2 font-mono text-xs leading-relaxed whitespace-pre-wrap break-all">{text}</pre>
    </div>
  );
}

function Row({ row, open, selected, onToggle }: { row: CallRow; open: boolean; selected: boolean; onToggle: () => void }) {
  const short = row.tool.replace(/^browser\./, "");
  const args = summarizeArgs(row.args);
  return (
    <div className={cn("border-b last:border-0", selected && "bg-muted/60")}>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="grid w-full grid-cols-[14px_56px_72px_minmax(0,1fr)_16px_56px] items-center gap-x-2 px-2 py-1.5 text-left hover:bg-muted/50 focus-visible:bg-muted/50 focus-visible:outline-none"
      >
        <ChevronRight className={cn("size-3 text-muted-foreground transition-transform", open && "rotate-90")} />
        <span className="tnum font-mono text-xs text-muted-foreground">{fmtTime(row.start_ts ?? row.end_ts)}</span>
        <PhaseChip phase={row.phase} />
        <span className="flex min-w-0 items-center gap-1.5">
          <span className="min-w-0 flex-1 truncate">
            <span className="font-mono text-xs">{short}</span>
            {args && <span className="ml-2 font-mono text-xs text-muted-foreground">{args}</span>}
          </span>
          {row.guard_verdict && <GuardBadge verdict={row.guard_verdict} />}
        </span>
        <span className="flex justify-center">
          {row.status === "running" ? (
            <Spinner />
          ) : row.status === "ok" ? (
            <Check className="size-3.5 text-muted-foreground" aria-label="ok" />
          ) : (
            <X className="size-3.5 text-destructive" aria-label="error" />
          )}
        </span>
        <span className="tnum text-right font-mono text-xs text-muted-foreground">{fmtDuration(row.duration_ms)}</span>
      </button>
      {open && (
        <div className="space-y-3 border-t bg-background px-3 py-3">
          <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
            <span className="text-muted-foreground">tool</span>
            <span className="font-mono">{row.tool}</span>
            {row.call_id && (
              <>
                <span className="text-muted-foreground">call</span>
                <span className="font-mono break-all">{row.call_id}</span>
              </>
            )}
            <span className="text-muted-foreground">seq</span>
            <span className="tnum font-mono">
              {row.start_seq ?? "-"} / {row.end_seq ?? "-"}
            </span>
            {row.client && (
              <>
                <span className="text-muted-foreground">client</span>
                <span className="font-mono">{row.client}</span>
              </>
            )}
            {row.result_summary && (
              <>
                <span className="text-muted-foreground">summary</span>
                <span className={cn(row.status === "error" && "text-destructive")}>{row.result_summary}</span>
              </>
            )}
            {row.screenshot_url && (
              <>
                <span className="text-muted-foreground">shot</span>
                <span className="inline-flex items-center gap-1 text-muted-foreground">
                  <ImageIcon className="size-3" /> shown in preview
                </span>
              </>
            )}
          </div>
          {row.guard_verdict && (
            <div className="space-y-1.5 rounded border px-2.5 py-2 text-xs" data-testid="guard-detail">
              <div className="flex flex-wrap items-center gap-2">
                <GuardBadge verdict={row.guard_verdict} />
                <span className="text-muted-foreground">guard verdict</span>
                {row.guard_stage && <span className="font-mono">stage: {row.guard_stage}</span>}
                {row.guard_mode && <span className="font-mono">mode: {row.guard_mode}</span>}
                {row.guard_enforced !== undefined && (
                  <span className="font-mono">enforced: {row.guard_enforced ? "yes" : "no"}</span>
                )}
              </div>
              {row.guard_reason && (
                <div>
                  <span className="text-muted-foreground">reason </span>
                  <span>{row.guard_reason}</span>
                </div>
              )}
              {row.guard_target_element && (
                <div>
                  <span className="text-muted-foreground">target </span>
                  <span className="font-mono">{row.guard_target_element}</span>
                </div>
              )}
              {row.guard_findings && row.guard_findings.length > 0 && (
                <ul className="space-y-0.5">
                  {row.guard_findings.map((f, i) => (
                    <li key={i} className="font-mono break-all">
                      <span>{f.kind}</span>
                      {f.detail && <span className="text-muted-foreground">: {f.detail}</span>}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
          {row.args !== undefined && <Json label="args (redacted)" value={row.args} />}
          {row.status === "running" ? (
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Spinner /> waiting for result
            </div>
          ) : (
            row.result !== undefined && <Json label="result" value={row.result} />
          )}
        </div>
      )}
    </div>
  );
}

export function TimelineList({
  rows,
  selectedKey,
  onSelect,
  live,
}: {
  rows: CallRow[];
  selectedKey: string | null;
  onSelect: (row: CallRow | null) => void;
  live: boolean;
}) {
  const [filter, setFilter] = useState<Filter>("all");
  const [open, setOpen] = useState<Set<string>>(new Set());
  const [stick, setStick] = useState(true);
  const box = useRef<HTMLDivElement>(null);
  const stickRef = useRef(true);
  const counts = countPhases(rows);
  const guard = countGuard(rows);
  const visible = filter === "all" ? rows : filter === "guard" ? rows.filter((r) => r.guard_verdict && r.guard_verdict !== "ALLOW") : rows.filter((r) => r.phase === filter);

  const onScroll = useCallback(() => {
    const el = box.current;
    if (!el) return;
    const near = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
    stickRef.current = near;
    setStick(near);
  }, []);

  // follow the newest row unless the user scrolled up
  useLayoutEffect(() => {
    const el = box.current;
    if (el && stick) el.scrollTop = el.scrollHeight;
  }, [rows, open, filter, stick]);

  useEffect(() => {
    if (!live) return;
    const el = box.current;
    if (!el) return;
    // a layout resize must not count as the user scrolling up
    const ro = new ResizeObserver(() => {
      if (stickRef.current) el.scrollTop = el.scrollHeight;
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [live]);

  const jump = () => {
    const el = box.current;
    if (el) el.scrollTo({ top: el.scrollHeight });
    stickRef.current = true;
    setStick(true);
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="mb-2 flex flex-wrap items-center gap-1" role="group" aria-label="Filter by phase">
        {FILTERS.map((f) => (
          <button
            key={f}
            type="button"
            onClick={() => setFilter(f)}
            aria-pressed={filter === f}
            className={cn(
              "h-6 rounded px-2 font-mono text-xs",
              filter === f ? "bg-foreground text-background" : "text-muted-foreground hover:bg-muted hover:text-foreground",
            )}
          >
            {f}
            <span className="tnum ml-1 opacity-70">{f === "all" ? rows.length : f === "guard" ? guard.intervened : counts[f as Exclude<Phase, "other">]}</span>
          </button>
        ))}
      </div>
      <div className="relative min-h-0 flex-1 rounded-md border">
        <div ref={box} onScroll={onScroll} className="absolute inset-0 overflow-y-auto" data-testid="timeline-scroll">
          {visible.length === 0 ? (
            <div className="px-3 py-8 text-muted-foreground">
              {rows.length === 0 ? (live ? "Waiting for the agent to call a tool..." : "No tool calls were recorded.") : `No ${filter} calls.`}
            </div>
          ) : (
            visible.map((r) => (
              <Row
                key={r.key}
                row={r}
                open={open.has(r.key)}
                selected={selectedKey === r.key}
                onToggle={() => {
                  setOpen((prev) => {
                    const n = new Set(prev);
                    if (n.has(r.key)) n.delete(r.key);
                    else n.add(r.key);
                    return n;
                  });
                  if (r.screenshot_url) onSelect(r);
                }}
              />
            ))
          )}
        </div>
        {!stick && visible.length > 0 && (
          <button
            type="button"
            onClick={jump}
            className="absolute bottom-3 left-1/2 inline-flex h-7 -translate-x-1/2 items-center gap-1 rounded-full border bg-background px-3 text-xs shadow-sm hover:bg-muted"
          >
            <ArrowDown className="size-3" /> Jump to latest
          </button>
        )}
      </div>
    </div>
  );
}
