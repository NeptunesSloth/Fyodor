/**
 * Structural sharing for incoming game views.
 *
 * The server sends a complete view after every change. `reconcile(prev, next)` returns an
 * object equal to `next` in which every sub-object that did not change is the *same
 * reference* as in `prev`. Components that select a single card/zone/player therefore only
 * re-render when that piece actually changed, which keeps large boards smooth.
 */
export function reconcile<T>(prev: T, next: T): T {
  if (Object.is(prev, next)) return prev;
  if (typeof prev !== "object" || typeof next !== "object" || prev === null || next === null) return next;
  if (Array.isArray(prev) !== Array.isArray(next)) return next;

  if (Array.isArray(prev) && Array.isArray(next)) {
    let same = prev.length === next.length;
    const out = next.map((item, i) => {
      const merged = i < prev.length ? reconcile(prev[i], item) : item;
      if (merged !== prev[i]) same = false;
      return merged;
    });
    return (same ? prev : out) as T;
  }

  const p = prev as Record<string, unknown>;
  const n = next as Record<string, unknown>;
  const nextKeys = Object.keys(n);
  let same = nextKeys.length === Object.keys(p).length;
  const out: Record<string, unknown> = {};
  for (const key of nextKeys) {
    const merged = key in p ? reconcile(p[key], n[key]) : n[key];
    if (merged !== p[key]) same = false;
    out[key] = merged;
  }
  return (same ? prev : out) as T;
}
