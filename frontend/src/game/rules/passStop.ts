import { create } from "zustand";
import { isVisible, type GameView, type LogEntryView } from "../../types/game";
import { drewLine, newDraws } from "../drawNotices";

/*
 * -- playtest (nov 16) -- why automatic passing stopped, said where the pass controls are (PassStop.tsx, over the turn dial):
 * - a loop pause: the rules engine stopped resolving a chain that keeps refilling the stack (Shabraz and Marina Vendrell's Grimoire), and
 *   said so in a log line that only showed, cut short, in the one-line log ticker;
 * - Resolve all stopped because I drew a card I can cast right now (the engine gives me priority back, 117.3b, and says nothing).
 * Built from my own view only: the public log line, my own hand and my own hints (nothing about anyone else's hand).
 */

export interface PassStop {
  kind: "loop" | "drew";
  /** What the banner says. */
  text: string;
  /** The stack when it stopped: the banner goes once the stack moves on. */
  stack: string;
}

/** A log line's words as this viewer reads them. */
export function logText(e: Pick<LogEntryView, "parts">): string {
  return e.parts.map((p) => ("t" in p ? p.t : "card" in p ? p.card.name : p.group.map((g) => g.card.name).join(", "))).join("");
}

/** The rules engine's loop-pause line (engine.loop_pause): "This keeps repeating … Automatic passing stopped …". */
const LOOP = /keeps repeating|automatic passing stopped/i;

/** The loop-pause line that arrived between two views, if any (the newest). */
export function loopNote(prev: GameView | null | undefined, next: GameView): string | null {
  if (!prev || prev.game.id !== next.game.id || !next.rules) return null;
  const seen = prev.log.length ? prev.log[prev.log.length - 1]!.seq : -1;
  const fresh = next.log.filter((e) => e.seq > seen).map(logText).filter((t) => LOOP.test(t));
  return fresh.length ? fresh[fresh.length - 1]! : null;
}

/** Cards of mine the hints let me cast now (any way: plain, free, an alternative cost). */
function castableNow(view: GameView, ids: string[]): string[] {
  const h = view.rules?.hints;
  if (!h) return [];
  return ids.filter((id) => h.castable?.includes(id) || h.free_castable?.includes(id) || !!h.alt_castable?.[id]);
}

/**
 * Resolve all (armed: `drawn`, the cards I drew since I clicked it) has stopped with the stack not empty, my priority, no decision of mine
 * and a card I drew castable now: their names. Null: it didn't stop for that (it finished, someone acted, a decision came up).
 */
export function drewStop(next: GameView, me: string, drawn: string[]): string[] | null {
  const r = next.rules;
  if (!r || r.paused || !next.stack.length || r.prefs?.pass_until || r.decision || !r.hints.has_priority) return null;
  if (r.priority !== me && r.acting_as == null) return null;
  const hand = new Set((next.zones[`${me}:hand`] as string[] | undefined) ?? []);
  const ids = castableNow(next, drawn.filter((id) => hand.has(id)));
  const names = ids.map((id) => next.cards[id]).filter(isVisible).map((c) => c.name);
  return names.length ? names : null;
}

export function drewText(names: string[]): string {
  return `Stopped: you drew ${drewLine(names, names.length, 3)} and can cast ${names.length === 1 ? "it" : "them"} now.`;
}

interface PassStopStore {
  /** Resolve all was clicked and hasn't finished: the cards I drew since. */
  armed: string[] | null;
  stop: PassStop | null;
  arm: () => void;
  dismiss: () => void;
  /** A new view: does it explain a stop? */
  update: (prev: GameView | null | undefined, next: GameView, me: string) => void;
}

export const usePassStop = create<PassStopStore>((set, get) => ({
  armed: null,
  stop: null,
  arm: () => set({ armed: [], stop: null }),
  dismiss: () => set({ stop: null }),
  update: (prev, next, me) => {
    const { armed, stop } = get();
    const stack = next.stack.join(",");
    const loop = loopNote(prev, next);
    if (loop) {
      set({ armed: null, stop: { kind: "loop", text: loop, stack } });
      return;
    }
    if (armed) {
      const ev = newDraws(prev, next, me);
      const drawn = ev ? [...armed, ...ev.ids] : armed;
      const names = drewStop(next, me, drawn);
      if (names) set({ armed: null, stop: { kind: "drew", text: drewText(names), stack } });
      else if (!next.rules?.prefs?.pass_until || !next.stack.length) set({ armed: null }); // (done, or stopped for something on the table)
      else if (ev) set({ armed: drawn });
      return;
    }
    // the stack moved on (or a decision opened): the reason is old news
    if (stop && (stop.stack !== stack || next.rules?.decision || !next.rules)) set({ stop: null });
  },
}));
