/**
 * The arranged 2D board (MTG Arena's battlefield, on Fyodor's mats): each battlefield lays itself out in rows, creatures
 * in front (toward the table's middle), other permanents behind them, lands at the back by their player's edge.
 * Identical lands and identical tokens stack into one slot with ×N, Auras and Equipment tuck under what they're
 * attached to, and attackers and blockers step forward. The cards size themselves to fill the mat: big when there are
 * few, smaller then overlapping when it's crowded.
 *
 * Display only, and only on this screen: the server's positions are untouched (the 3D table, free placement and saves
 * use them), and dragging a card along its row only changes this screen's order (kept for the tab, like "my order" in
 * the hand).
 */
import { isVisible, type CardStats, type GameCard } from "../types/game";
import type { CardData } from "../types/cards";

/** A board tile is a little shorter than a card: the art, a name bar and the P/T, with no rules text. */
export const TILE_RATIO = 1.12;

export type RowKind = "creature" | "other" | "land";

/** What the layout needs to know about one card on the board. */
export interface ArrangeCard {
  id: string;
  row: RowKind;
  /** Cards with the same non-null key stack into one slot (identical lands, identical tokens). */
  key: string | null;
  /** How many it stands for (a token stack's quantity). */
  n: number;
  /** Tapped (or turned a quarter): it lies sideways. */
  turned: boolean;
  /** Attacking or blocking: it steps toward the middle. */
  forward: boolean;
  /** Tucked under this card (an Aura or Equipment attached to a card on the same board). */
  host: string | null;
}

export interface Placement { left: number; top: number; z: number; pile?: number }

export interface BoardRow { kind: RowKind; top: number; height: number; left: number; right: number; slots: string[][] }

export interface BoardLayout {
  /** Tile width and height in px. */
  w: number;
  h: number;
  place: Map<string, Placement>;
  rows: BoardRow[];
}

export interface ArrangeOptions {
  width: number;
  height: number;
  /** An opponent's mat: their front (creatures) is at the bottom, toward the middle of the table. */
  mirrored: boolean;
  /** Space kept clear along the back edge (my mat: the top of the hand, which overlaps it). */
  backInset?: number;
  /** A corner kept clear (the turn dial over my mat): rows reaching below `top` stop short of `left`. */
  keepOut?: { top: number; left: number } | null;
  /** Largest tile width. */
  maxW?: number;
  /** Rows don't shrink their cards below this width for room: they overlap instead (a short mat still shrinks them). */
  minW?: number;
}

const PILE_STEP = 0.1; // each extra card in a stack peeks out this much (tile widths)
const PILE_SHOWN = 4; // a stack shows at most this many edges
const ATT_DX = 0.12; // an attachment peeks out to the right …
const ATT_DY = 0.17; // … and toward the middle of the table
const ATT_SHOWN = 3;
const FORWARD = 0.14; // attackers and blockers step forward (tile widths)
const GAP = 0.03; // between slots (tile widths), besides the room each slot keeps for turning its card
const ROW_GAP = 0.1; // between rows, at the least (tile widths)
const PAD = 8; // px around the mat's edge

/** Front to back. */
const ROW_ORDER: RowKind[] = ["creature", "other", "land"];

interface Slot { ids: string[]; n: number; turned: boolean; forward: boolean; attach: string[]; merged?: boolean }

/** Slot footprint in tile widths: [width, height]. */
function slotSize(s: Slot): [number, number] {
  const shown = Math.min(s.ids.length, PILE_SHOWN);
  const att = Math.min(s.attach.length, ATT_SHOWN);
  // every slot has room for its card turned sideways: tapping or untapping never moves the rest of the row
  const w = TILE_RATIO + (shown - 1) * PILE_STEP + att * ATT_DX;
  const h = TILE_RATIO + att * ATT_DY + (s.forward ? FORWARD : 0); // (a turned card's line keeps its height too)
  return [w, h];
}

/** The board's rows of slots, in display order (cards in `cards` order; stacks sit where their first card is). */
export function boardSlots(cards: ArrangeCard[]): Record<RowKind, Slot[]> {
  const byId = new Map(cards.map((c) => [c.id, c]));
  const rows: Record<RowKind, Slot[]> = { creature: [], other: [], land: [] };
  const keyed = new Map<string, Slot>();
  const hostSlot = new Map<string, Slot>();
  // tucked under a card on this board (and not itself tucked under something: no chains, no loops)
  const tucked = (c: ArrangeCard) => !!c.host && c.host !== c.id && byId.has(c.host) && !byId.get(c.host)!.host;
  const hosts = new Set(cards.filter(tucked).map((a) => a.host!));
  for (const c of cards) {
    if (tucked(c)) continue;
    const key = c.key && !hosts.has(c.id) ? `${c.row}|${c.key}` : null;
    const same = key ? keyed.get(key) : undefined;
    if (same) {
      same.ids.push(c.id);
      same.n += c.n;
      continue;
    }
    const slot: Slot = { ids: [c.id], n: c.n, turned: c.turned, forward: c.forward, attach: [] };
    if (key) keyed.set(key, slot);
    hostSlot.set(c.id, slot);
    rows[c.row].push(slot);
  }
  for (const c of cards) if (tucked(c)) hostSlot.get(c.host!)?.attach.push(c.id);
  return rows;
}

interface Line { kind: RowKind; slots: Slot[] }

/** `list` in `n` lines of about the same length, front to back. */
function wrap(kind: RowKind, list: Slot[], n: number): Line[] {
  const per = Math.ceil(list.length / n);
  const out: Line[] = [];
  for (let i = 0; i < list.length; i += per) out.push({ kind, slots: list.slice(i, i + per) });
  return out;
}

/**
 * The ways this board could be laid out: each row in one line or wrapped in two or three, and the other permanents
 * either in their own row or beside the lands (MTG Arena's back row) when that leaves room for bigger cards.
 */
function layouts(slots: Record<RowKind, Slot[]>): Line[][] {
  const c = slots.creature;
  const o = slots.other;
  const l = slots.land;
  const out: Line[][] = [];
  const counts = (n: number, most: number) => [1, 2, 3].filter((k) => k <= most && (k === 1 || n >= k * 2));
  for (const lc of counts(c.length, 3)) {
    const front = c.length ? wrap("creature", c, lc) : [];
    for (const lo of counts(o.length, 2)) {
      for (const ll of counts(l.length, 2)) {
        out.push([...front, ...(o.length ? wrap("other", o, lo) : []), ...(l.length ? wrap("land", l, ll) : [])]);
      }
    }
    if (o.length && l.length) {
      const beside = o.map((sl) => ({ ...sl, merged: true }));
      for (const lb of counts(o.length + l.length, 2)) out.push([...front, ...wrap("land", [...l, ...beside], lb)]);
    }
  }
  return out;
}

/** Lay out one battlefield. */
export function arrangeBoard(cards: ArrangeCard[], opts: ArrangeOptions): BoardLayout {
  const { width: W, height: H, mirrored } = opts;
  const back = opts.backInset ?? 0;
  const maxW = opts.maxW ?? 150;
  const slots = boardSlots(cards);
  const place = new Map<string, Placement>();
  if (!ROW_ORDER.some((k) => slots[k].length) || W <= 0 || H <= 0) return { w: 0, h: 0, place, rows: [] };
  const innerW = Math.max(40, W - PAD * 2);
  const innerH = Math.max(30, H - PAD * 2 - back);

  // the lines' vertical bands for a tile width, front to back (front: the top of my mat, the bottom of an opponent's)
  const bands = (lines: Line[], units: number[], w: number) => {
    const total = units.reduce((a, b) => a + b * w, 0);
    const spare = Math.max(0, innerH - total);
    // the spare room goes between the rows (a wrapped row's lines stay together); one row alone sits where it belongs
    const breaks = lines.reduce((n, ln, i) => n + (i > 0 && ln.kind !== lines[i - 1]!.kind ? 1 : 0), 0);
    const kindGap = breaks ? Math.max(ROW_GAP * w, (spare - (lines.length - 1 - breaks) * ROW_GAP * w) / breaks) : ROW_GAP * w;
    const lone = !breaks ? (lines[0]!.kind === "land" ? spare - (lines.length - 1) * ROW_GAP * w : lines[0]!.kind === "other" ? (spare - (lines.length - 1) * ROW_GAP * w) / 2 : 0) : 0;
    let at = PAD + Math.max(0, lone);
    const out = units.map((u, i) => {
      if (i > 0) at += lines[i]!.kind !== lines[i - 1]!.kind ? kindGap : ROW_GAP * w;
      const top = at;
      at += u * w;
      return { top, height: u * w };
    });
    // an opponent's front is the bottom of their mat (their back inset, if any, is at the top)
    return mirrored ? out.map((b) => ({ ...b, top: H - b.top - b.height })) : out;
  };
  const lineWidth = (band: { top: number; height: number }) => {
    const k = opts.keepOut;
    if (k && band.top + band.height > k.top && k.left < W - PAD) return Math.max(40, k.left - PAD - 6);
    return innerW;
  };

  /** A tile width for these lines, and how good it is (bigger is better; overlapping costs). */
  const fit = (lines: Line[]) => {
    const units = lines.map((ln) => Math.max(...ln.slots.map((s) => slotSize(s)[1])));
    const across = lines.map((ln) => ln.slots.reduce((sum, s) => sum + slotSize(s)[0], 0) + (ln.slots.length - 1) * GAP);
    const hFit = innerH / (units.reduce((a, b) => a + b, 0) + (lines.length - 1) * ROW_GAP);
    const minW = Math.min(hFit, opts.minW ?? 58);
    const solve = (avail: number[]) => {
      const wFit = Math.min(...across.map((u, i) => avail[i]! / u));
      // a line too crowded for readable cards overlaps them instead of shrinking them further
      return { w: Math.max(4, Math.min(maxW, hFit, Math.max(wFit, minW))), wFit };
    };
    let r = solve(lines.map(() => innerW));
    if (opts.keepOut) r = solve(bands(lines, units, r.w).map(lineWidth));
    // overlapping cards count as smaller than what shows of them: a line more is usually easier to read
    const score = r.wFit >= r.w ? r.w : r.wFit * (r.wFit / r.w);
    return { ...r, units, score };
  };
  // each line, and putting the other permanents beside the lands, has to earn its place with clearly bigger cards
  const cost = (option: Line[]) => 1.08 ** option.length * (option.some((ln) => ln.kind === "land" && ln.slots.some((sl) => sl.merged)) ? 1.15 : 1);
  let lines: Line[] = [];
  let best: (ReturnType<typeof fit> & { value: number }) | null = null;
  for (const option of layouts(slots)) {
    const f = fit(option);
    const value = f.score / cost(option);
    if (!best || value > best.value) {
      best = { ...f, value };
      lines = option;
    }
  }
  const w = best!.w;
  const h = w * TILE_RATIO;
  const at = bands(lines, best!.units, w);

  const rows: BoardRow[] = [];
  const frontDir = mirrored ? 1 : -1; // toward the middle of the table: up on my mat, down on an opponent's
  lines.forEach((line, r) => {
    const band = at[r]!;
    const list = line.slots;
    const sizes = list.map((s) => slotSize(s)[0] * w);
    const avail = lineWidth(band);
    const natural = sizes.reduce((a, b) => a + b, 0) + (list.length - 1) * GAP * w;
    // crowded: the slots overlap evenly, the last one whole
    const last = sizes[sizes.length - 1]!;
    const squeeze = natural > avail && list.length > 1 ? Math.max(0, (avail - last) / (natural - last)) : 1;
    let x = PAD + Math.max(0, (avail - Math.min(natural, avail)) / 2);
    const rowLeft = x;
    list.forEach((slot, si) => {
      const footW = TILE_RATIO * w;
      const att = Math.min(slot.attach.length, ATT_SHOWN);
      // the stack (card, its attachments peeking out, its forward step) is centred in the line's band
      const cy = band.top + band.height / 2 - frontDir * (att * ATT_DY * w) / 2 + (slot.forward ? frontDir * FORWARD * w / 2 : 0);
      const z0 = (lines.length - r) * 10000 + si * 100;
      // the card it stands on is at the slot's left; attachments peek out to the right and toward the middle
      slot.attach.forEach((aid, j) => {
        const k = Math.min(j + 1, ATT_SHOWN);
        place.set(aid, { left: x + footW / 2 + k * ATT_DX * w - w / 2, top: cy + frontDir * k * ATT_DY * w - h / 2, z: z0 + ATT_SHOWN - Math.min(j, ATT_SHOWN - 1) });
      });
      const shown = Math.min(slot.ids.length, PILE_SHOWN);
      slot.ids.forEach((id, m) => {
        const step = Math.max(0, shown - slot.ids.length + m); // the hidden ones sit under the first edge
        const cx = x + footW / 2 + step * PILE_STEP * w;
        const top = m === slot.ids.length - 1;
        place.set(id, { left: cx - w / 2, top: cy - h / 2, z: z0 + ATT_SHOWN + 1 + m, ...(top && slot.ids.length > 1 ? { pile: slot.n } : {}) });
      });
      x += (sizes[si]! + GAP * w) * squeeze;
    });
    rows.push({ kind: line.kind, top: band.top, height: band.height, left: rowLeft, right: Math.min(PAD + avail, rowLeft + natural), slots: list.map((s) => [...s.ids, ...s.attach]) });
  });
  return { w, h, place, rows };
}

/** Which row a card goes in. Face-down permanents are creatures (2/2s); a card whose type hasn't loaded yet waits in the middle row. */
export function rowOf(card: GameCard, data: CardData | undefined, stats?: CardStats): RowKind {
  if (!isVisible(card) || card.face_down) return "creature";
  if (stats?.creature) return "creature";
  const line = typeLineOf(card, data);
  if (/\bCreature\b/.test(line)) return "creature";
  if (/\bLand\b/.test(line)) return "land";
  return "other";
}

/** The type line of the face it shows. */
export function typeLineOf(card: GameCard, data: CardData | undefined): string {
  if (!isVisible(card)) return "";
  if (card.token && !card.card_id) return card.token.type_line ?? "";
  const face = data?.faces?.length ? data.faces[Math.min(card.face ?? 0, data.faces.length - 1)] : undefined;
  return (face?.type_line ?? data?.type_line ?? card.token?.type_line ?? "").split("//")[0] ?? "";
}

/**
 * The stacking key: identical lands (same name, face, tapped or not, owner) and identical tokens (also the same P/T,
 * counters, damage, combat role) stack. Anything carrying its own state (a note, a marker, counters on a land, a
 * face-down card, an attachment) stays on its own.
 */
export function stackKey(card: GameCard, row: RowKind): string | null {
  if (!isVisible(card) || card.face_down || card.attached_to || card.attached_player) return null;
  if (card.note || card.effects?.length || card.locked || card.choices && Object.keys(card.choices).length) return null;
  if (card.merged && card.merged.length > 1) return null;
  const counters = card.counters && Object.keys(card.counters).length ? JSON.stringify(Object.entries(card.counters).sort()) : "";
  const common = `${card.name}|${card.card_id ?? ""}|${card.face ?? 0}|${card.tapped ? 1 : 0}|${card.owner}|${card.rotation ?? 0}|${card.flipped ? 1 : 0}`;
  if (card.is_token) {
    const t = card.token;
    const combat = `${card.attacking?.id ?? ""}|${card.attacking_without_target ?? ""}|${card.blocking ?? ""}|${card.blocking_without_attacker ? 1 : 0}`;
    return `T|${common}|${t?.power ?? ""}/${t?.toughness ?? ""}|${card.copy_of?.source_name ?? ""}|${counters}|${card.damage ?? 0}|${combat}|${card.token_source?.name ?? ""}`;
  }
  if (row === "land" && !counters && !card.damage && !card.copy_of && !card.commander_key) return `L|${common}`;
  return null;
}

/** The facts for one card on the board. */
export function arrangeCard(card: GameCard, data: CardData | undefined, stats?: CardStats): ArrangeCard {
  const row = rowOf(card, data, stats);
  const turn = ((card.tapped ? 90 : 0) + (card.rotation ?? 0)) % 180;
  return {
    id: card.id,
    row,
    key: stackKey(card, row),
    n: card.quantity ?? 1,
    turned: Math.abs(turn) === 90,
    forward: !!(card.attacking || card.attacking_without_target || card.blocking || card.blocking_without_attacker),
    host: card.attached_to ?? null,
  };
}

// ------------------------------------------------------------------ my order (display only)

const ORDER_KEY = (gameId: string, zone: string) => `fyodor.boardOrder.${gameId}.${zone}`;

const orders = new Map<string, string[]>(); // read from session storage once per board

export function boardOrder(gameId: string, zone: string): string[] {
  const key = ORDER_KEY(gameId, zone);
  const known = orders.get(key);
  if (known) return known;
  const read = readOrder(key);
  orders.set(key, read);
  return read;
}

function readOrder(key: string): string[] {
  try {
    const raw = sessionStorage.getItem(key);
    const ids: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(ids) ? ids.filter((x): x is string => typeof x === "string") : [];
  } catch {
    return [];
  }
}

export function saveBoardOrder(gameId: string, zone: string, ids: string[]): void {
  orders.set(ORDER_KEY(gameId, zone), ids.slice(0, 400));
  try {
    sessionStorage.setItem(ORDER_KEY(gameId, zone), JSON.stringify(ids.slice(0, 400)));
  } catch {
    /* private mode: the order lasts until the next reload */
  }
}

/** The zone's cards in my order: the ones I placed first, as I placed them, then the rest as they came (new cards at the end). */
export function applyOrder(ids: string[], order: string[]): string[] {
  if (!order.length) return ids;
  const rank = new Map(order.map((id, i) => [id, i]));
  const placed = ids.filter((id) => rank.has(id)).sort((a, b) => rank.get(a)! - rank.get(b)!);
  return [...placed, ...ids.filter((id) => !rank.has(id))];
}

/**
 * Dropping `moving` on its own board with the dragged card's top-left at (x, y) px: the order with those cards moved to
 * that spot in their row (the line of that row nearest the drop, when it wraps), or null when they aren't on the board.
 */
export function reorderOnDrop(layout: BoardLayout, moving: string[], x: number, y?: number): string[] | null {
  const from = layout.rows.find((r) => r.slots.some((s) => s.some((id) => moving.includes(id))));
  if (!from) return null;
  const cy = y == null ? null : y + layout.h / 2;
  const row = cy == null ? from : layout.rows.filter((r) => r.kind === from.kind)
    .reduce((a, b) => (Math.abs(b.top + b.height / 2 - cy) < Math.abs(a.top + a.height / 2 - cy) ? b : a), from);
  const mine = layout.rows.flatMap((r) => r.slots.filter((s) => s.some((id) => moving.includes(id)) && r.kind === from.kind)).flat();
  const others = row.slots.filter((s) => !s.some((id) => moving.includes(id)));
  const centre = x + layout.w / 2;
  let at = others.length;
  for (let i = 0; i < others.length; i++) {
    const p = layout.place.get(others[i]![0]!);
    if (p && centre < p.left + layout.w / 2) {
      at = i;
      break;
    }
  }
  const newRow = [...others.slice(0, at), mine, ...others.slice(at)].flat();
  return layout.rows.flatMap((r) => (r === row ? newRow : r.slots.filter((s) => !(r.kind === from.kind && s.some((id) => moving.includes(id)))).flat()));
}
