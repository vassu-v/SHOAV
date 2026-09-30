"use client";

import { useEffect, useState } from "react";
import { Check, Copy } from "lucide-react";
import { cn } from "@/lib/utils";
import type { GuardVerdict, Phase } from "@/lib/types";

export function CopyButton({ value, label = "Copy", className }: { value: string; label?: string; className?: string }) {
  const [done, setDone] = useState(false);
  useEffect(() => {
    if (!done) return;
    const t = setTimeout(() => setDone(false), 1200);
    return () => clearTimeout(t);
  }, [done]);
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={async (e) => {
        e.stopPropagation();
        try {
          await navigator.clipboard.writeText(value);
          setDone(true);
        } catch {
          // clipboard can be blocked on non-secure origins
        }
      }}
      className={cn("inline-flex size-5 items-center justify-center rounded text-muted-foreground hover:bg-muted hover:text-foreground", className)}
    >
      {done ? <Check className="size-3" /> : <Copy className="size-3" />}
    </button>
  );
}

const PHASE_STYLE: Record<Phase, string> = {
  read: "text-[var(--phase-read)] bg-[var(--phase-read-bg)]",
  screenshot: "text-[var(--phase-screenshot)] bg-[var(--phase-screenshot-bg)]",
  act: "text-[var(--phase-act)] bg-[var(--phase-act-bg)]",
  session: "text-[var(--phase-session)] bg-[var(--phase-session-bg)]",
  other: "text-[var(--phase-other)] bg-[var(--phase-other-bg)]",
};

export function PhaseChip({ phase, className }: { phase: Phase; className?: string }) {
  return (
    <span className={cn("inline-flex h-[18px] w-[72px] shrink-0 items-center justify-center rounded-sm font-mono text-[11px] leading-none", PHASE_STYLE[phase] ?? PHASE_STYLE.other, className)}>
      {phase}
    </span>
  );
}

const GUARD_STYLE: Record<GuardVerdict, string> = {
  ALLOW: "text-[var(--guard-allow)] bg-[var(--guard-allow-bg)]",
  REWRITE: "text-[var(--guard-rewrite)] bg-[var(--guard-rewrite-bg)]",
  ESCALATE: "text-[var(--guard-escalate)] bg-[var(--guard-escalate-bg)]",
  BLOCK: "text-[var(--guard-block)] bg-[var(--guard-block-bg)]",
};

/**
 * Guard verdict badge. ALLOW is quiet (muted), REWRITE amber,
 * ESCALATE orange, BLOCK red.
 */
export function GuardBadge({ verdict, className }: { verdict: GuardVerdict; className?: string }) {
  return (
    <span
      data-testid={`guard-badge-${verdict.toLowerCase()}`}
      title={`guard: ${verdict}`}
      className={cn(
        "inline-flex h-[18px] shrink-0 items-center justify-center rounded-sm px-1.5 font-mono text-[11px] leading-none",
        GUARD_STYLE[verdict],
        verdict === "ALLOW" && "opacity-60",
        className,
      )}
    >
      {verdict}
    </span>
  );
}

/** Header chip: Guard mode plus blocked and rewritten counts. Hidden when no guard event seen. */
export function GuardChip({ mode, blocked, rewritten, escalated }: { mode?: string; blocked: number; rewritten: number; escalated?: number }) {
  if (!mode && blocked === 0 && rewritten === 0 && !escalated) return null;
  const parts = [`Guard: ${mode ?? "off"}`, `${blocked} blocked`, `${rewritten} rewritten`];
  if (escalated) parts.push(`${escalated} escalated`);
  return (
    <span
      data-testid="guard-chip"
      title={escalated ? `${escalated} escalated` : undefined}
      className="inline-flex h-6 items-center gap-1.5 rounded border px-2 font-mono text-xs text-muted-foreground"
    >
      <span
        aria-hidden
        className={cn(
          "size-2 rounded-full",
          blocked > 0 ? "bg-[var(--guard-block)]" : rewritten > 0 || (escalated ?? 0) > 0 ? "bg-[var(--guard-rewrite)]" : "bg-[var(--guard-allow)]",
        )}
      />
      {parts.join(", ")}
    </span>
  );
}

export type ViewState = "live" | "archived" | "reconnecting";

export function StateBadge({ state }: { state: ViewState }) {
  const label = state === "live" ? "Live" : state === "archived" ? "Archived" : "Reconnecting";
  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-medium">
      <span
        className={cn(
          "size-2 rounded-full",
          state === "live" && "animate-pulse bg-[var(--live)]",
          state === "archived" && "bg-muted-foreground/50",
          state === "reconnecting" && "border border-destructive bg-transparent",
        )}
      />
      <span className={cn(state === "live" && "text-[var(--live)]", state !== "live" && "text-muted-foreground")}>{label}</span>
    </span>
  );
}

export function Spinner({ className }: { className?: string }) {
  return <span aria-label="running" className={cn("inline-block size-3 animate-spin rounded-full border-[1.5px] border-muted-foreground/40 border-t-foreground", className)} />;
}

export function useNow(intervalMs = 1000, enabled = true) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!enabled) return;
    const t = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(t);
  }, [intervalMs, enabled]);
  return now;
}

export function Message({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div className="rounded-md border border-dashed px-4 py-8">
      <div className="text-sm font-medium">{title}</div>
      {children && <div className="mt-1 text-muted-foreground">{children}</div>}
    </div>
  );
}
