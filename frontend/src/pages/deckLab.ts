/**
 * Deck lab statistics (no React, tested directly): colour pips against the lands that make each colour, the type breakdown,
 * the odds of land drops (hypergeometric) and sample opening hands from a seed. Computed from the card cache; the library is
 * the main deck (the commander waits in the command zone). A modal DFC with a land back counts as a land for land drops.
 */
import { seededRandom } from "../game/seededRandom";
import { TYPE_GROUP_ORDER, typeGroup } from "../state/deckEdit";
import type { CardData } from "../types/cards";
import type { DeckEntry } from "../types/decks";

export const COLORS = ["W", "U", "B", "R", "G"] as const;
export type Color = (typeof COLORS)[number];
const BASIC: Record<string, Color> = { Plains: "W", Island: "U", Swamp: "B", Mountain: "R", Forest: "G" };

type Cards = Record<string, CardData | undefined>;

const frontType = (c: CardData) => (c.faces[0]?.type_line ?? c.type_line ?? "").split("//")[0]!;
export const isLand = (c: CardData) => frontType(c).includes("Land");
/** A modal DFC whose back is a land (Shatterskull Smashing): a spell that can be played as a land drop. */
export const landBack = (c: CardData) => !isLand(c) && c.layout === "modal_dfc" && (c.faces[1]?.type_line ?? "").includes("Land");

/** Colour symbols in a mana cost: hybrid counts each half, Phyrexian its colour. */
export function pips(cost: string | null | undefined): Record<Color, number> {
  const out = { W: 0, U: 0, B: 0, R: 0, G: 0 };
  for (const [, sym] of (cost ?? "").matchAll(/\{([^}]+)\}/g)) for (const c of COLORS) if (sym!.includes(c)) out[c] += 1;
  return out;
}

/**
 * The colours a land face can make: its basic land types, the coloured symbols in its text, and every colour for "any color"
 * or a fetch of any basic land.
 * ponytail: text heuristic (an activated ability's {W} cost reads as a source too); use Scryfall's produced_mana if it's stored.
 */
export function landColors(typeLine: string | null | undefined, text: string | null | undefined): Color[] {
  const t = `${typeLine ?? ""}\n${text ?? ""}`;
  if (/any colou?r|basic land card/i.test(t)) return [...COLORS];
  const out = new Set<Color>();
  for (const [word, c] of Object.entries(BASIC)) if (new RegExp(`\\b${word}\\b`).test(t)) out.add(c);
  for (const [, c] of t.matchAll(/\{([WUBRG])\}/g)) out.add(c as Color);
  return COLORS.filter((c) => out.has(c));
}

export interface DeckStats {
  /** cards in the library (main deck) */
  library: number;
  /** main deck cards whose card data isn't loaded (left out of every number) */
  missing: number;
  lands: number;
  /** of `lands`: modal DFCs with a land back */
  mdfc: number;
  pips: Record<Color, number>;
  sources: Record<Color, number>;
  types: { label: string; count: number }[];
}

export function deckStats(entries: DeckEntry[], cards: Cards): DeckStats {
  const s: DeckStats = { library: 0, missing: 0, lands: 0, mdfc: 0, pips: { W: 0, U: 0, B: 0, R: 0, G: 0 }, sources: { W: 0, U: 0, B: 0, R: 0, G: 0 }, types: [] };
  const types = new Map<string, number>();
  for (const e of entries) {
    if (e.section !== "main" && e.section !== "commander") continue;
    const c = e.printing_id ? cards[e.printing_id] : undefined;
    if (e.section === "main") s.library += e.quantity;
    if (!c) {
      if (e.section === "main") s.missing += e.quantity;
      continue;
    }
    const land = isLand(c);
    if (!land) {
      const p = pips(c.faces[0]?.mana_cost ?? c.mana_cost);
      for (const k of COLORS) s.pips[k] += p[k] * e.quantity;
    }
    if (e.section !== "main") continue;
    const back = landBack(c);
    if (land || back) {
      s.lands += e.quantity;
      if (back) s.mdfc += e.quantity;
      const face = back ? c.faces[1]! : land && c.faces.length ? c.faces[0]! : c;
      for (const k of landColors(face.type_line, face.oracle_text)) s.sources[k] += e.quantity;
    }
    const g = typeGroup(c.type_line);
    types.set(g, (types.get(g) ?? 0) + e.quantity);
  }
  s.types = TYPE_GROUP_ORDER.filter((g) => types.has(g)).map((label) => ({ label, count: types.get(label)! }));
  return s;
}

function choose(n: number, k: number): number {
  if (k < 0 || k > n) return 0;
  const m = Math.min(k, n - k);
  let r = 1;
  for (let i = 1; i <= m; i++) r = (r * (n - m + i)) / i;
  return r;
}

/** P(exactly k successes in n draws from N cards holding K successes). */
export function hypergeometric(N: number, K: number, n: number, k: number): number {
  const total = choose(N, n);
  return total ? (choose(K, k) * choose(N - K, n - k)) / total : 0;
}

/** P(at least k successes in n draws). */
export function atLeast(N: number, K: number, n: number, k: number): number {
  let miss = 0;
  for (let i = 0; i < k; i++) miss += hypergeometric(N, K, Math.min(n, N), i);
  return Math.max(0, Math.min(1, 1 - miss));
}

/** Hitting every land drop up to turns 2, 3 and 4: on the play you've seen 6 + turn cards, on the draw 7 + turn. */
export function landDrops(N: number, K: number): { turn: number; play: number; draw: number }[] {
  return [2, 3, 4].map((turn) => ({ turn, play: atLeast(N, K, 6 + turn, turn), draw: atLeast(N, K, 7 + turn, turn) }));
}

export interface PoolCard { id: string; name: string; land: boolean }

/** The library card by card (main deck, loaded cards only), for sample hands. */
export function libraryPool(entries: DeckEntry[], cards: Cards): PoolCard[] {
  const out: PoolCard[] = [];
  for (const e of entries) {
    const c = e.section === "main" && e.printing_id ? cards[e.printing_id] : undefined;
    if (!c) continue;
    for (let i = 0; i < e.quantity; i++) out.push({ id: c.id, name: c.name, land: isLand(c) || landBack(c) });
  }
  return out;
}

/** Hand number `n` from `seed`: the same seed and number always deal the same seven. */
export function sampleHand(pool: PoolCard[], seed: number, n: number, size = 7): PoolCard[] {
  const rnd = seededRandom(`${seed}:${n}`);
  const deck = [...pool];
  for (let i = deck.length - 1; i > 0; i--) {
    const j = Math.floor(rnd() * (i + 1));
    [deck[i], deck[j]] = [deck[j]!, deck[i]!];
  }
  return deck.slice(0, size);
}

/** The simple keep rule: two to five lands. */
export const keeps = (hand: PoolCard[]) => {
  const lands = hand.filter((c) => c.land).length;
  return lands >= 2 && lands <= 5;
};

/** Of `count` hands from `seed`, how many the keep rule keeps. */
export function keepRate(pool: PoolCard[], seed: number, count = 100): number {
  let kept = 0;
  for (let n = 0; n < count; n++) if (keeps(sampleHand(pool, seed, n))) kept++;
  return kept;
}
