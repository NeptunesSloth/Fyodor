/**
 * DICE & TOYS (docs/ELIMINATION_HUB.md): a dice tray, a just-for-fun random player and a tally, for a player who is out
 * or a spectator. All of it is local to this browser: results come from crypto.getRandomValues (never Math.random),
 * nothing is sent to the server, and nothing touches the live game's state, log, dice or sound for anyone else. The
 * random player only ever sees the seated players' public names.
 */
import type { GameView } from "../types/game";

export const DIE_KINDS = ["d4", "d6", "d8", "d10", "d12", "d20", "coin"] as const;
export type DieKind = (typeof DIE_KINDS)[number];
export type Pool = Record<DieKind, number>;

/** At most this many of one kind, and in all (the table's dice show twelve at most: game/dice.ts DICE_SHOWN). */
export const MAX_OF_KIND = 8;
export const MAX_DICE = 12;
/** Recent rolls kept in this browser. */
export const HISTORY_MAX = 10;

export const sidesOf = (k: DieKind): number => (k === "coin" ? 2 : Number(k.slice(1)));

/** A uniform whole number in [0, n) from the browser's cryptographic generator (rejection sampling: no modulo bias). */
export function secureInt(n: number): number {
  if (!Number.isInteger(n) || n < 1 || n > 2 ** 32) throw new RangeError(`secureInt: ${n}`);
  const limit = Math.floor(2 ** 32 / n) * n;
  const buf = new Uint32Array(1);
  for (;;) {
    crypto.getRandomValues(buf);
    if (buf[0]! < limit) return buf[0]! % n;
  }
}

export type RandomInt = (n: number) => number;

/** One kind of die in a roll. A coin's results are 1 (heads) or 0 (tails). */
export interface RollGroup { kind: DieKind; results: number[] }
export interface Roll { id: string; at: number; groups: RollGroup[] }

export const emptyPool = (): Pool => ({ d4: 0, d6: 0, d8: 0, d10: 0, d12: 0, d20: 0, coin: 0 });
export const poolSize = (p: Pool): number => DIE_KINDS.reduce((a, k) => a + p[k], 0);

/** Add (or take away) dice of one kind, within the limits. */
export function addDie(pool: Pool, kind: DieKind, delta: number): Pool {
  const room = MAX_DICE - poolSize(pool) + pool[kind];
  const n = Math.max(0, Math.min(MAX_OF_KIND, room, pool[kind] + delta));
  return n === pool[kind] ? pool : { ...pool, [kind]: n };
}

const countOf = (k: DieKind, n: number) => (k === "coin" ? (n === 1 ? "coin" : `${n} coins`) : `${n === 1 ? "" : n}${k}`);

/** "3d6 + d20 + coin". */
export function poolLabel(pool: Pool): string {
  return DIE_KINDS.filter((k) => pool[k] > 0).map((k) => countOf(k, pool[k])).join(" + ");
}

/** Roll every die in the pool. Null when the pool is empty. */
export function rollPool(pool: Pool, rnd: RandomInt = secureInt, now = Date.now()): Roll | null {
  const groups = DIE_KINDS.filter((k) => pool[k] > 0).map((kind) => ({
    kind,
    results: Array.from({ length: pool[kind] }, () => (kind === "coin" ? rnd(2) : 1 + rnd(sidesOf(kind)))),
  }));
  if (!groups.length) return null;
  return { id: `${now.toString(36)}-${++rolled}`, at: now, groups };
}
let rolled = 0;

export const poolOf = (roll: Roll): Pool =>
  roll.groups.reduce((p, g) => ({ ...p, [g.kind]: g.results.length }), emptyPool());

/** The dice added up (coins don't count). Null when only coins were flipped. */
export function rollTotal(roll: Roll): number | null {
  const dice = roll.groups.filter((g) => g.kind !== "coin");
  return dice.length ? dice.reduce((a, g) => a + g.results.reduce((x, y) => x + y, 0), 0) : null;
}

/** "heads", "tails", "2 heads, 1 tails". Null without coins. */
export function coinSummary(roll: Roll): string | null {
  const coins = roll.groups.find((g) => g.kind === "coin")?.results;
  if (!coins?.length) return null;
  if (coins.length === 1) return coins[0] ? "heads" : "tails";
  const heads = coins.filter(Boolean).length;
  return `${heads} heads, ${coins.length - heads} tails`;
}

/** The headline under the tray: the total, or the coins when only coins were flipped. */
export function rollHeadline(roll: Roll): string {
  const total = rollTotal(roll);
  return total === null ? coinSummary(roll) ?? "" : String(total);
}

/** One line per roll, for the history and screen readers: "3d6 + d20: 4 + 2 + 6 + 17 = 29 · coin: heads". */
export function rollLine(roll: Roll): string {
  const dice = roll.groups.filter((g) => g.kind !== "coin");
  const coins = coinSummary(roll);
  const parts: string[] = [];
  if (dice.length) {
    const label = poolLabel({ ...poolOf(roll), coin: 0 });
    const values = dice.flatMap((g) => g.results);
    parts.push(values.length === 1 ? `${label}: ${values[0]}` : `${label}: ${values.join(" + ")} = ${rollTotal(roll)}`);
  }
  if (coins) parts.push(`${countOf("coin", roll.groups.find((g) => g.kind === "coin")!.results.length)}: ${coins}`);
  return parts.join(" · ");
}

/** Newest first, a few kept. */
export const remember = (history: Roll[], roll: Roll): Roll[] => [roll, ...history.filter((r) => r.id !== roll.id)].slice(0, HISTORY_MAX);

/** What Roll and Reroll keep: the dice rolled become the pool, and the roll goes on top of the history. */
export const keepRoll = (s: ToysSaved, roll: Roll): ToysSaved => ({ ...s, pool: poolOf(roll), history: remember(s.history, roll) });

// -- the random player (just for fun: never the turn order) --------------------------------------------------------

/** The seated players still at the table, by their public names, alphabetically (so it never reads like seat order). */
export function spinPlayers(view: Pick<GameView, "players" | "seat_order">): { id: string; name: string }[] {
  return view.seat_order
    .map((id) => view.players.find((p) => p.id === id))
    .filter((p): p is GameView["players"][number] => !!p && !p.left)
    .map((p) => ({ id: p.id, name: p.name }))
    .sort((a, b) => a.name.localeCompare(b.name));
}

/** The names the highlight visits, a couple of laps round and then to the pick (the last index is the pick). */
export function spinPath(count: number, pick: number, minSteps = 12): number[] {
  if (count < 1) return [];
  const laps = Math.max(2, Math.ceil(minSteps / count));
  return [...Array.from({ length: laps * count }, (_, i) => i % count), ...Array.from({ length: pick + 1 }, (_, i) => i)];
}

// -- kept in this browser -------------------------------------------------------------------------------------------

export interface ToysSaved { pool: Pool; history: Roll[]; tally: { label: string; count: number } }

const KEY = "fyodor.toys";
export const TALLY_MIN = -999;
export const TALLY_MAX = 9999;
export const defaultToys = (): ToysSaved => ({ pool: { ...emptyPool(), d20: 1 }, history: [], tally: { label: "Tally", count: 0 } });

const isKind = (k: unknown): k is DieKind => typeof k === "string" && (DIE_KINDS as readonly string[]).includes(k);
const validResult = (k: DieKind, v: unknown) => Number.isInteger(v) && (v as number) >= (k === "coin" ? 0 : 1) && (v as number) <= (k === "coin" ? 1 : sidesOf(k));

/** Whatever was stored, made safe (anything odd falls back to the defaults). */
export function sanitizeToys(raw: unknown): ToysSaved {
  const base = defaultToys();
  if (!raw || typeof raw !== "object") return base;
  const r = raw as Partial<Record<keyof ToysSaved, unknown>>;
  let pool = emptyPool();
  if (r.pool && typeof r.pool === "object") {
    for (const k of DIE_KINDS) {
      const n = (r.pool as Record<string, unknown>)[k];
      if (Number.isInteger(n)) pool = addDie(pool, k, n as number);
    }
  }
  const history = (Array.isArray(r.history) ? r.history : []).flatMap((x): Roll[] => {
    const roll = x as Partial<Roll> | null;
    if (!roll || typeof roll.id !== "string" || typeof roll.at !== "number" || !Array.isArray(roll.groups) || !roll.groups.length) return [];
    const ok = roll.groups.every((g) => isKind(g?.kind) && Array.isArray(g.results) && g.results.length > 0
      && g.results.length <= MAX_OF_KIND && g.results.every((v) => validResult(g.kind, v)));
    return ok ? [{ id: roll.id.slice(0, 40), at: roll.at, groups: roll.groups.map((g) => ({ kind: g.kind, results: [...g.results] })) }] : [];
  }).slice(0, HISTORY_MAX);
  const t = (r.tally && typeof r.tally === "object" ? r.tally : {}) as { label?: unknown; count?: unknown };
  const tally = {
    label: typeof t.label === "string" ? t.label.slice(0, 40) : base.tally.label,
    count: Number.isInteger(t.count) ? Math.max(TALLY_MIN, Math.min(TALLY_MAX, t.count as number)) : 0,
  };
  return { pool: poolSize(pool) ? pool : base.pool, history, tally };
}

export function loadToys(): ToysSaved {
  try {
    const raw = localStorage.getItem(KEY);
    return sanitizeToys(raw ? JSON.parse(raw) : null);
  } catch {
    return defaultToys();
  }
}

export function saveToys(t: ToysSaved): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(t));
  } catch {
    /* private window or storage full: the toys still work, they just aren't remembered */
  }
}
