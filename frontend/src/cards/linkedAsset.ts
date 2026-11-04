/**
 * Something the host links from Scryfall and caches rather than ships (the card back, the mana symbols; see
 * backend/app/cards/linked.py): is it there yet? Each check sets a class on the page (`has-card-back`, `has-symbols`)
 * that the styles switch on, and tells its subscribers when the answer changes. A miss is asked again a little later,
 * then less and less often: the host fetches a missing one in the background as soon as it may go online, so a table
 * opened before that picks it up without a reload.
 */
const RETRY_MS = [15_000, 60_000, 300_000, 600_000];

export interface LinkedCheck {
  /** Ask the host (once; `force` asks again). Resolves to whether it has it. */
  (force?: boolean): Promise<boolean>;
  /** The last answer. */
  ready(): boolean;
  /** Called when the answer changes. Returns the unsubscribe. */
  subscribe(listener: () => void): () => void;
}

export function linkedCheck(className: string, probe: () => Promise<boolean>): LinkedCheck {
  let pending: Promise<boolean> | null = null;
  let ok = false;
  let misses = 0;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const listeners = new Set<() => void>();
  const check = (force = false): Promise<boolean> => {
    if (pending && !force) return pending;
    clearTimeout(timer);
    pending = probe()
      .catch(() => false)
      .then((now) => {
        const changed = now !== ok;
        ok = now;
        if (typeof document !== "undefined") document.documentElement.classList.toggle(className, now);
        if (now) misses = 0;
        else timer = setTimeout(() => void check(true), RETRY_MS[Math.min(misses++, RETRY_MS.length - 1)]);
        if (changed) for (const l of [...listeners]) l();
        return now;
      });
    return pending;
  };
  return Object.assign(check, {
    ready: () => ok,
    subscribe: (listener: () => void) => {
      listeners.add(listener);
      return () => void listeners.delete(listener);
    },
  });
}
