/**
 * TABLE MOTION: what happened between two views of the table, so both tables can show it (cards flying from where they were, attacks,
 * blocks, damage, draws, mills and shuffles). Display only: the server has already applied it all, and this reads nothing but the two views
 * this viewer was sent, so it can't show more than they do.
 *
 * A hidden card has no lasting id: a hand this viewer can't see is a list of anonymous placeholders, and a shuffle renames a library's cards.
 * So hidden traffic is read from zone sizes. Another player's library one card shorter and their hand one card longer is a draw; a library
 * two cards shorter and two new cards in that player's graveyard is a mill.
 */
import type { AttackTarget, GameView, LibraryView } from "../../types/game";

export type TableEvent =
  /** A card this viewer saw before and sees now changed zones. */
  | { kind: "move"; id: string; from: string; to: string }
  /** A card this viewer sees now and didn't before. ``from``: the zone it came out of, as far as the views tell (a library: a draw or a
   * mill; a hand: a cast, a land or a discard); null: it was made here (a token, a copy) or the views can't tell. ``source``: the permanent
   * an ability on the stack comes from. */
  | { kind: "arrive"; id: string; from: string | null; to: string; source?: string }
  /** A card this viewer saw went where they can't see it (another player's hand, a library); ``to`` null: it left the game (a token). */
  | { kind: "leave"; id: string; from: string; to: string | null }
  /** Cards moved between zones this viewer can't see into (another player's draw, a card put back on top). */
  | { kind: "hidden"; from: string; to: string; n: number }
  | { kind: "shuffle"; zone: string; times: number }
  /** A creature began attacking (``target``: the player, planeswalker or battle; null: no target recorded). */
  | { kind: "attack"; id: string; target: AttackTarget | null }
  | { kind: "block"; id: string; attacker: string }
  /** Damage marked on a permanent went up. */
  | { kind: "damage"; id: string; amount: number }
  | { kind: "life"; player: string; delta: number };

export const PLACEHOLDER = "hidden:";

/** The player a zone key belongs to ("p2:hand" → "p2"; the stack: null). */
export function zoneOwner(key: string): string | null {
  const at = key.indexOf(":");
  return at < 0 ? null : key.slice(0, at);
}

export function zoneName(key: string): string {
  const at = key.indexOf(":");
  return at < 0 ? key : key.slice(at + 1);
}

function size(view: GameView, key: string): number {
  const z = view.zones[key];
  if (!z) return 0;
  return Array.isArray(z) ? z.length : (z as LibraryView).count;
}

function shuffles(view: GameView, key: string): number {
  const z = view.zones[key];
  return z && !Array.isArray(z) ? ((z as LibraryView).shuffles ?? 0) : 0;
}

/** Where a card coming out of a hidden zone most likely came from, for a card arriving at ``to`` (the zones a player's cards leave unseen). */
function sourcesFor(to: string): string[] {
  const zone = zoneName(to);
  if (zone === "graveyard" || zone === "exile") return ["library", "hand"]; // mill, exile from the top; discard
  if (zone === "hand") return ["library"]; // a draw (the viewer's own hand)
  return ["hand", "library"]; // a cast or a land from the hand; a card put onto the battlefield from the library
}

/** Where a card leaving this viewer's sight most likely went. */
function destinationsFor(from: string): string[] {
  const zone = zoneName(from);
  return zone === "hand" || zone === "library" ? ["library"] : ["hand", "library"];
}

const tracked = (view: GameView): Map<string, string> => {
  const out = new Map<string, string>();
  for (const c of Object.values(view.cards)) if (!c.id.startsWith(PLACEHOLDER)) out.set(c.id, c.zone);
  return out;
};

/**
 * The events between ``prev`` and ``next`` (the same game), in this order: zone traffic, shuffles, combat, damage and life. Cards the viewer
 * moved by dragging (``dragged``, the store's pending positions) are left out of the zone traffic: they're already where the hand put them.
 */
export function tableEvents(prev: GameView, next: GameView, dragged: ReadonlySet<string> = new Set()): TableEvent[] {
  const out: TableEvent[] = [];
  const before = tracked(prev);
  const after = tracked(next);
  // what each zone gained or lost unseen: its change in size, less the seen cards that came in or went out
  const keys = new Set([...Object.keys(prev.zones), ...Object.keys(next.zones)]);
  const unseen = new Map<string, number>();
  for (const key of keys) unseen.set(key, size(next, key) - size(prev, key));
  const adjust = (key: string, by: number) => unseen.set(key, (unseen.get(key) ?? 0) + by);
  const arrived: string[] = [];
  const left: string[] = [];
  for (const [id, zone] of after) {
    const was = before.get(id);
    if (was === undefined) {
      arrived.push(id);
      adjust(zone, -1);
    } else if (was !== zone) {
      adjust(zone, -1);
      adjust(was, +1);
      if (!dragged.has(id)) out.push({ kind: "move", id, from: was, to: zone });
    }
  }
  for (const [id, zone] of before) {
    if (!after.has(id)) {
      left.push(id);
      adjust(zone, +1);
    }
  }
  // a seen card that arrived: from a zone of the same player that lost cards unseen
  const take = (owner: string | null, names: string[], sign: -1 | 1): string | null => {
    if (owner === null) return null;
    for (const name of names) {
      const key = `${owner}:${name}`;
      const n = unseen.get(key) ?? 0;
      if (sign < 0 ? n < 0 : n > 0) {
        adjust(key, -sign);
        return key;
      }
    }
    return null;
  };
  for (const id of arrived) {
    const card = next.cards[id]!;
    if ("ability" in card && card.ability) { // a triggered or activated ability: from its source, never out of a hidden zone
      if (!dragged.has(id)) out.push({ kind: "arrive", id, from: null, to: card.zone, ...(card.ability.source_id ? { source: card.ability.source_id } : {}) });
      continue;
    }
    const made = "is_token" in card && card.is_token;
    const from = made ? null : take(card.owner, sourcesFor(card.zone), -1);
    if (from === card.zone) continue; // (a shuffle renamed a card the viewer could see in that library: it didn't go anywhere)
    if (!dragged.has(id)) out.push({ kind: "arrive", id, from, to: card.zone });
  }
  for (const id of left) {
    const card = prev.cards[id]!;
    const made = ("is_token" in card && card.is_token) || ("ability" in card && !!card.ability);
    const to = made ? null : take(card.owner, destinationsFor(card.zone), 1);
    if (to === card.zone) continue;
    out.push({ kind: "leave", id, from: card.zone, to });
  }
  // what's left unseen: a player's zone that lost cards and another of theirs that gained them (a draw: library → hand)
  for (const [from, lost] of unseen) {
    if (lost >= 0 || zoneOwner(from) === null) continue;
    let rest = -lost;
    for (const [to, gained] of unseen) {
      if (rest === 0) break;
      if (gained <= 0 || to === from || zoneOwner(to) !== zoneOwner(from)) continue;
      const n = Math.min(rest, gained);
      out.push({ kind: "hidden", from, to, n });
      unseen.set(to, gained - n);
      rest -= n;
    }
    unseen.set(from, -rest);
  }
  for (const key of keys) {
    const times = shuffles(next, key) - shuffles(prev, key);
    if (times > 0) out.push({ kind: "shuffle", zone: key, times });
  }
  // combat and damage: on cards seen in both views
  for (const [id] of after) {
    const was = prev.cards[id];
    const now = next.cards[id];
    if (!was || !now || was.zone !== now.zone) continue;
    if (now.attacking && (!was.attacking || was.attacking.id !== now.attacking.id)) out.push({ kind: "attack", id, target: now.attacking });
    else if (now.attacking_without_target && !was.attacking && !was.attacking_without_target) out.push({ kind: "attack", id, target: null });
    if (now.blocking && now.blocking !== was.blocking) out.push({ kind: "block", id, attacker: now.blocking });
    const hurt = (now.damage ?? 0) - (was.damage ?? 0);
    if (hurt > 0) out.push({ kind: "damage", id, amount: hurt });
  }
  for (const p of next.players) {
    const was = prev.players.find((q) => q.id === p.id);
    if (was && was.life !== p.life) out.push({ kind: "life", player: p.id, delta: p.life - was.life });
  }
  return out;
}

/** The table's motion feed: the store publishes each view's events; the 2D and 3D tables listen. */
export type MotionListener = (events: TableEvent[], next: GameView, prev: GameView) => void;
const listeners = new Set<MotionListener>();

export function onTableEvents(listener: MotionListener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function publishTableEvents(prev: GameView, next: GameView, dragged: ReadonlySet<string>): void {
  if (!listeners.size || prev.viewer !== next.viewer) return; // (a hot-seat table switching whose view it shows: nothing moved)
  const events = tableEvents(prev, next, dragged);
  if (!events.length) return;
  for (const listener of listeners) {
    try {
      listener(events, next, prev);
    } catch (err) {
      console.error("table motion", err); // (display only: a failed animation never stops the game)
    }
  }
}
