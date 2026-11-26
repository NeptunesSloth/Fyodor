import { useState } from "react";

/**
 * Cloudflare's quick tunnel answers a burst of image requests with HTTP 429 (no Retry-After, empty body); an <img> can't see
 * the status, so after a failed load ask once, and if it was a 429 wait a second and say "load it again".
 */
export async function retryAfter429(
  src: string,
  fetchImpl: typeof fetch = fetch,
  wait: (ms: number) => Promise<unknown> = (ms) => new Promise((r) => setTimeout(r, ms)),
): Promise<boolean> {
  try {
    const ctl = new AbortController();
    const res = await fetchImpl(src, { cache: "no-store", signal: ctl.signal });
    ctl.abort(); // (the headers are all that's wanted)
    if (res.status !== 429) return false;
  } catch {
    return false;
  }
  await wait(1000);
  return true;
}

/** An <img>'s failure handling: one retry after a 429, then the text card. `nonce` is the img's key (a new one reloads it). */
export function useImageRetry() {
  const [failed, setFailed] = useState<string | null>(null);
  const [retried, setRetried] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  const onError = (src: string) => {
    if (retried === src) return setFailed(src);
    setRetried(src);
    void retryAfter429(src).then((again) => (again ? setNonce((n) => n + 1) : setFailed(src)));
  };
  return { failed, nonce, onError };
}
