"use client";

import { useEffect, useState } from "react";
import { getTools } from "@/lib/api";
import { PHASES, type ToolsResponse } from "@/lib/types";
import { CopyButton, PhaseChip } from "@/components/ui-bits";
import { Skeleton } from "@/components/ui/skeleton";

export function ToolsPanel() {
  const [data, setData] = useState<ToolsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getTools().then(
      (d) => !cancelled && setData(d),
      (e) => !cancelled && setError(e instanceof Error ? e.message : String(e)),
    );
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) return <div role="alert" className="rounded-md border border-destructive/40 px-3 py-2 text-destructive">Could not load tools: {error}</div>;
  if (!data)
    return (
      <div className="space-y-2">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-9 w-full" />
      </div>
    );

  return (
    <div className="min-h-0 flex-1 space-y-5 overflow-y-auto pr-1">
      <section>
        <div className="mb-1 flex items-center justify-between text-xs text-muted-foreground">
          <span>Instructions the agent receives on connect</span>
          <CopyButton value={data.instructions} label="Copy instructions" />
        </div>
        <pre className="max-h-56 overflow-auto rounded border bg-muted/40 p-3 font-mono text-xs leading-relaxed whitespace-pre-wrap">{data.instructions}</pre>
      </section>
      {PHASES.map((phase) => {
        const tools = data.tools.filter((t) => t.phase === phase);
        if (!tools.length) return null;
        return (
          <section key={phase}>
            <div className="mb-1 flex items-center gap-2">
              <PhaseChip phase={phase} />
              <span className="tnum text-xs text-muted-foreground">{tools.length}</span>
            </div>
            <div className="rounded-md border">
              {tools.map((t) => (
                <div key={t.name} className="border-b px-3 py-2 last:border-0">
                  <div className="flex flex-wrap items-baseline gap-x-2">
                    <span className="font-mono text-xs font-medium">{t.name}</span>
                    {t.read_only && <span className="text-[11px] text-muted-foreground">read-only</span>}
                  </div>
                  <div className="mt-0.5 text-muted-foreground">{t.description}</div>
                  {t.required.length > 0 && (
                    <div className="mt-1 font-mono text-xs text-muted-foreground">
                      requires: {t.required.join(", ")}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}
