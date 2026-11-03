/**
 * Dice you can see, as at a Tabletop Simulator table: every public roll or coin flip in the log is thrown from the
 * roller's seat across their mat and lands there, on the 3D table and the 2D table alike (table3d/dice.ts; on the 2D
 * table the same dice in an overlay, or game/DiceLayer.tsx's drawn dice without WebGL). The numbers come from the
 * server (rolled on the host, written to the log); this is presentation only. Rolls already in the log when the
 * table opens aren't replayed.
 *
 * Landed dice stay where they fell, with a chip over each and a line saying what was rolled, until the roller rolls
 * again, someone clicks them away (on their own screen), or the turn ends: a roll usually settles something for the
 * rest of the turn ("roll a d20 at the beginning of combat…"), so it stays readable that long, and no longer, so dice
 * don't pile up over the cards.
 */
import { useEffect, useRef } from "react";
import { useGame } from "../state/gameStore";
import type { CannonLog, LogEntryView } from "../types/game";

/** ``ignored``: indexes into ``results`` of rolls the rules ignored (706.6: "roll one more die and ignore the lowest", Barbarian Class). */
export interface DiceShow {
  key: string; actor: string | null; sides: number; results: number[]; coin: boolean; ignored?: number[];
  /** -- table toys -- fired from the dice cannon (game/cannon.ts): who each die lands in front of, and in which volley. */
  cannon?: CannonLog | null;
}

/** What thrown dice are made of (Settings → Dice, this screen only): table3d/diceLook.ts. */
export type DiceLook = "resin" | "marble" | "metal" | "gem";
export const DICE_LOOKS: { id: DiceLook; label: string }[] = [
  { id: "resin", label: "Glossy resin" },
  { id: "marble", label: "Marble swirl" },
  { id: "metal", label: "Enamelled metal" },
  { id: "gem", label: "Gemstone" },
];

/** Dice drawn for one roll; a bigger roll shows these and its total. */
export const DICE_SHOWN = 12;
/**
 * Tests and screenshots: freeze every throw at this many milliseconds after it started (null: live). Headless
 * software WebGL draws about a frame a second and a screenshot takes seconds, so wall-clock timing can't pin a frame.
 */
export const diceClock: { frozen: number | null } = { frozen: null };

declare global {
  interface Window {
    /** Test hook: freeze (or, with null, release) every throw at a time in ms. */
    __fyodorDice?: { freeze: (ms: number | null) => void };
  }
}
if (typeof window !== "undefined") {
  window.__fyodorDice = {
    freeze: (ms) => {
      diceClock.frozen = ms;
      window.dispatchEvent(new Event("fyodor:dice-clock")); // renderers that draw on demand draw again
    },
  };
}

/** "2d6", "d20", "d100", "coin", "3 coins" (dice the rules ignored aren't counted). */
export function rollLabel(r: Pick<DiceShow, "sides" | "results" | "coin" | "ignored">): string {
  const n = r.results.length - (r.ignored?.length ?? 0);
  if (r.coin) return n === 1 ? "coin" : `${n} coins`;
  return `${n > 1 ? n : ""}d${r.sides}`;
}

/** The line under a roll: "Bob · 2d6: 3 + 6 = 9". */
export function rollLine(name: string, r: Pick<DiceShow, "sides" | "results" | "coin" | "ignored">): string {
  return `${name ? `${name} · ` : ""}${rollLabel(r)}: ${rollSummary(r)}`;
}

/** A d20 that came up 20 or 1 (kept rolls only): the table marks it. */
export function natural(r: Pick<DiceShow, "sides" | "coin" | "results" | "ignored">, i: number): "high" | "low" | null {
  if (r.coin || r.sides !== 20 || r.ignored?.includes(i)) return null;
  return r.results[i] === 20 ? "high" : r.results[i] === 1 ? "low" : null;
}

const keyOf = (e: LogEntryView) => `${e.seq}:${e.ts}`;

/** Each roll's dice as text: "3 + 5 = 8", "14", "heads", "2 heads". */
export function rollSummary(r: Pick<DiceShow, "results" | "coin" | "ignored">): string {
  if (r.coin) return r.results.length === 1 ? (r.results[0] ? "heads" : "tails") : `${r.results.filter(Boolean).length} heads`;
  const kept = keptRolls(r);
  const ignored = (r.ignored ?? []).map((i) => r.results[i]).filter((v): v is number => v !== undefined);
  const shown = kept.length === 1 ? String(kept[0]) : `${kept.slice(0, DICE_SHOWN).join(" + ")}${kept.length > DICE_SHOWN ? " + …" : ""} = ${kept.reduce((a, b) => a + b, 0)}`;
  return ignored.length ? `${shown} (ignored ${ignored.join(", ")})` : shown;
}

/** The rolls that count: the results without the ones the rules ignored. */
export function keptRolls(r: Pick<DiceShow, "results" | "ignored">): number[] {
  const ignored = new Set(r.ignored ?? []);
  return r.results.filter((_, i) => !ignored.has(i));
}

/** Calls `onRoll` once for each new roll that reaches this table. */
export function useDiceFeed(onRoll: (r: DiceShow) => void): void {
  const handler = useRef(onRoll);
  handler.current = onRoll;
  useEffect(() => {
    const seen = new Set((useGame.getState().view?.log ?? []).filter((e) => e.roll).map(keyOf));
    return useGame.subscribe((s, prev) => {
      const log = s.view?.log;
      if (!log || log === prev.view?.log) return;
      for (const e of log) {
        if (!e.roll || seen.has(keyOf(e))) continue;
        seen.add(keyOf(e));
        handler.current({ key: keyOf(e), actor: e.actor, sides: e.roll.sides, results: e.roll.results, coin: e.roll.coin, ignored: e.roll.ignored ?? [], cannon: e.roll.cannon ?? null });
      }
    });
  }, []);
}
