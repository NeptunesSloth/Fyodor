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
  const t = Math.max(0, Math.floor(seconds));
  const h = Math.floor(t / 3600);
  const m = Math.floor((t % 3600) / 60);
  const s = t % 60;
  const ss = String(s).padStart(2, "0");
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${ss}` : `${m}:${ss}`;
}
