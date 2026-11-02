/**
 * Dice you can see, as at a Tabletop Simulator table: every public roll or coin flip in the log is shown
 * landing at the roller's seat, on the 3D table and the 2D table alike. The numbers come from the server
 * (rolled on the host, written to the log); this is presentation only. Rolls already in the log when the
 * table opens aren't replayed.
 */
import { useEffect, useRef } from "react";
import { useGame } from "../state/gameStore";
import type { LogEntryView } from "../types/game";

/** ``ignored``: indexes into ``results`` of rolls the rules ignored (706.6: "roll one more die and ignore the lowest", Barbarian Class). */
export interface DiceShow { key: string; actor: string | null; sides: number; results: number[]; coin: boolean; ignored?: number[] }

/** Dice drawn for one roll; a bigger roll shows these and its total. */
export const DICE_SHOWN = 12;
/** How long landed dice stay on the table before they fade. */
export const DICE_HOLD_MS = 5200;

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
        handler.current({ key: keyOf(e), actor: e.actor, sides: e.roll.sides, results: e.roll.results, coin: e.roll.coin, ignored: e.roll.ignored ?? [] });
      }
    });
  }, []);
}
