"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { streamUrl } from "@/lib/api";
import { cn } from "@/lib/utils";

export type FeedStatus = "connecting" | "live" | "unavailable" | "paused";

const BACKOFF_MS = [1000, 2000, 4000, 8000, 15000];

/** True while the browser tab is visible. The stream is dropped when it is not. */
function usePageVisible() {
  const [visible, setVisible] = useState(true);
  useEffect(() => {
    const update = () => setVisible(document.visibilityState !== "hidden");
    update();
    document.addEventListener("visibilitychange", update);
    return () => document.removeEventListener("visibilitychange", update);
  }, []);
  return visible;
}

/**
 * The live MJPEG feed as a plain <img>. Only mounted while the session is live.
 * - The <img> is removed (and its src cleared) on unmount and while the tab is hidden, so an
 *   idle tab never keeps a screencast running on the controller.
 * - A failed connection is retried with backoff; `fallbackSrc` is shown meanwhile.
 * - An <img> cannot send an Authorization header, so a token-protected controller answers
 *   401 and this stays in the "unavailable" state (captures keep working the same way).
 */
export function LiveFeed(props: {
  sessionId: string;
  fallbackSrc: string | null;
  onStatus?: (s: FeedStatus) => void;
}) {
  const visible = usePageVisible();
  // Remount on session or visibility change: all connection state starts fresh.
  return <Feed key={`${props.sessionId}:${visible}`} visible={visible} {...props} />;
}

function Feed({
  sessionId,
  fallbackSrc,
  onStatus,
  visible,
}: {
  sessionId: string;
  fallbackSrc: string | null;
  onStatus?: (s: FeedStatus) => void;
  visible: boolean;
}) {
  const [attempt, setAttempt] = useState(0);
  const [loaded, setLoaded] = useState(false);
  const [failed, setFailed] = useState(false);
  const failures = useRef(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );

  const status: FeedStatus = !visible ? "paused" : loaded ? "live" : failed ? "unavailable" : "connecting";
  useEffect(() => {
    onStatus?.(status);
  }, [status, onStatus]);

  const onLoad = useCallback(() => {
    failures.current = 0;
    setLoaded(true);
    setFailed(false);
  }, []);

  const onError = useCallback(() => {
    setLoaded(false);
    setFailed(true);
    if (timer.current) clearTimeout(timer.current);
    const delay = BACKOFF_MS[Math.min(failures.current, BACKOFF_MS.length - 1)];
    failures.current += 1;
    timer.current = setTimeout(() => setAttempt((a) => a + 1), delay); // new URL, new request
  }, []);

  // React 19 ref cleanup: clearing src aborts the multipart request even if the node lingers.
  const streamRef = useCallback((el: HTMLImageElement | null) => {
    if (!el) return;
    return () => el.removeAttribute("src");
  }, []);

  const showStream = status === "live";
  return (
    <div className="relative" data-testid="live-feed" data-status={status}>
      {visible && (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          ref={streamRef}
          key={attempt}
          src={streamUrl(sessionId, attempt)}
          alt="Live browser feed"
          onLoad={onLoad}
          onError={onError}
          className={cn("w-full rounded-md border bg-muted/30", !showStream && "hidden")}
        />
      )}
      {!showStream &&
        (fallbackSrc ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={fallbackSrc} alt="Latest capture" className="w-full rounded-md border bg-muted/30" />
        ) : (
          <div className="flex aspect-[16/10] w-full items-center justify-center rounded-md border border-dashed text-muted-foreground">
            {status === "paused" ? "Feed paused while this tab is hidden." : "Waiting for the live feed."}
          </div>
        ))}
    </div>
  );
}

export function FeedChip({ status }: { status: FeedStatus }) {
  const label =
    status === "live"
      ? "Live feed"
      : status === "connecting"
        ? "Connecting"
        : status === "paused"
          ? "Feed paused"
          : "Feed unavailable, showing last capture";
  return (
    <span className="inline-flex items-center gap-1.5 text-xs" data-testid="feed-chip">
      <span
        className={cn(
          "size-1.5 rounded-full",
          status === "live" && "bg-[var(--live)]",
          status === "connecting" && "animate-pulse bg-muted-foreground",
          status === "paused" && "bg-muted-foreground/50",
          status === "unavailable" && "border border-destructive bg-transparent",
        )}
      />
      <span className={cn(status === "live" ? "text-foreground" : "text-muted-foreground")}>{label}</span>
    </span>
  );
}
