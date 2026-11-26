import { useEffect, useRef, useState } from "react";
import { useTunnel } from "../services/share";

/** Milliseconds before the one retry of a failed image: spread over 0.8-2 s so a burst's images don't come back in lockstep. */
export const retryDelay = (random: () => number = Math.random): number => 800 + random() * 1200;

/**
 * Cloudflare's quick tunnel refuses part of a burst of image requests (HTTP 429, no Retry-After); an <img> can't see the
 * status, so on the tunnel (and only there) each src is loaded once more after a jittered wait. Returns the cancel.
 */
export function scheduleRetry(
  again: () => void,
  random: () => number = Math.random,
  timers: { set: (fn: () => void, ms: number) => unknown; clear: (id: unknown) => void } = {
    set: (fn, ms) => setTimeout(fn, ms),
    clear: (id) => clearTimeout(id as ReturnType<typeof setTimeout>),
  },
): () => void {
  const id = timers.set(again, retryDelay(random));
  return () => timers.clear(id);
}

/** What a failed load does: try once more (tunnel, first failure of this src), or fall back to the text card. */
export const imageErrorPlan = (tunnel: boolean, retried: string | null, src: string): "retry" | "fail" => (tunnel && retried !== src ? "retry" : "fail");

/** An <img>'s failure handling. `nonce` is the img's key (a new one reloads it). */
export function useImageRetry() {
  const tunnel = useTunnel();
  const [failed, setFailed] = useState<string | null>(null);
  const [retried, setRetried] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  const cancel = useRef<(() => void) | null>(null);
  useEffect(() => () => cancel.current?.(), []);
  const onError = (src: string) => {
    if (imageErrorPlan(tunnel, retried, src) === "fail") return setFailed(src);
    setRetried(src);
    cancel.current?.();
    cancel.current = scheduleRetry(() => setNonce((n) => n + 1));
  };
  return { failed, nonce, onError };
}
