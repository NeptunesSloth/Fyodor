/**
 * -- turn clock (internet-play Stage 3) -- the server owns the clock; this only draws it. The view carries each player's remaining
 * time as of `sent_at` (the server's wall clock). The client's own clock may be minutes off, so it never compares the two directly:
 * `skew` is the smallest (receive time - sent_at) seen, which is the offset plus the least network delay, and elapsed time is
 * measured against that.
 */
export interface ClockEntry { bank: number; buffer: number; running: boolean; away: boolean }

/** The least-delayed message wins: a later, slower one never makes the clock jump back. */
export function noteSkew(prev: number | null, sentAt: number, receivedAtMs: number): number {
  const s = receivedAtMs / 1000 - sentAt;
  return prev === null ? s : Math.min(prev, s);
}

/** How long a skew sample stays in the running minimum: a client clock stepped (NTP, sleep and resume) recovers once it is out. */
export const SKEW_WINDOW_MS = 5 * 60 * 1000;
export type SkewSamples = [receivedAtMs: number, skew: number][];

/**
 * The skew over the recent window: the least-delayed message within it wins, but a sample older than the window is forgotten,
 * so a stepped client clock stops reading low once the old samples age out. `skew` is the minimum of the kept samples.
 */
export function noteSkewWindow(samples: SkewSamples, sentAt: number, receivedAtMs: number, windowMs = SKEW_WINDOW_MS): { samples: SkewSamples; skew: number } {
  const kept = samples.filter(([t]) => receivedAtMs - t < windowMs && receivedAtMs >= t);
  kept.push([receivedAtMs, noteSkew(null, sentAt, receivedAtMs)]);
  return { samples: kept, skew: kept.reduce((m, [, s]) => Math.min(m, s), Infinity) };
}

/** What is left now: the buffer is spent first, then the bank; frozen unless running and not away. */
export function remainingNow(e: ClockEntry, sentAt: number, skew: number, nowMs: number): { buffer: number; bank: number } {
  const elapsed = e.running && !e.away ? Math.max(0, nowMs / 1000 - skew - sentAt) : 0;
  const fromBuffer = Math.min(e.buffer, elapsed);
  return {
    buffer: Math.max(0, Math.min(e.buffer, e.buffer - fromBuffer)),
    bank: Math.max(0, Math.min(e.bank, e.bank - (elapsed - fromBuffer))),
  };
}

/** "25:00", "0:07", "1:02:03". */
export function formatClock(seconds: number): string {
  const t = Number.isFinite(seconds) ? Math.max(0, Math.ceil(seconds)) : 0; // time left rounds up: 0.4 s left is still 0:01
  const h = Math.floor(t / 3600);
  const m = Math.floor((t % 3600) / 60);
  const s = t % 60;
  const ss = String(s).padStart(2, "0");
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${ss}` : `${m}:${ss}`;
}
