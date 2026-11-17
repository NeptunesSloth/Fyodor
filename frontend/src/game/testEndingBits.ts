/**
 * -- test-table ending -- the pure half of the defeat / victory screen at a table with target dummies (TestEnding.tsx): which
 * variant, the cause in words, the card the log names just before the loss, and the life to tick down. Everything comes from
 * this viewer's own view (public facts: the rules' loss reasons, the table log, life totals), never from hidden information.
 */
import type { GameView, LogEntryView, PlayerView } from "../types/game";
import type { TestEnding } from "./nightEnding";

export type EndingVariant = "defeat" | "victory" | "draw";

export function endingVariant(kind: TestEnding["kind"]): EndingVariant {
  return kind === "lost" ? "defeat" : kind === "won" ? "victory" : "draw";
}

/** The big word, by variant. */
export const ENDING_WORD: Record<EndingVariant, string> = { defeat: "Defeat", victory: "Victory", draw: "Draw" };

/** The rules engine's loss reason (app/rules/sba.py, win_game.py) as a sentence about you; anything else stays the engine's words. */
export function causeLine(reason: string | null | undefined, conceded = false): string {
  if (conceded) return "You conceded the game.";
  const r = (reason ?? "").trim();
  if (!r) return "You lost the game.";
  if (r === "0 or less life") return "Your life fell to 0.";
  if (/^\d+ poison counters$/.test(r)) return `You were poisoned: ${r}.`;
  if (/combat damage from one commander$/.test(r)) return `You took ${r}.`;
  if (r === "drew from an empty library") return "You drew from an empty library.";
  if (r === "an effect") return "An effect made you lose the game.";
  return `${r.charAt(0).toUpperCase()}${r.slice(1)}.`;
}

const text = (e: LogEntryView): string => e.parts.map((p) => ("t" in p ? p.t : "card" in p ? p.card.name : "")).join("");
const firstCard = (e: LogEntryView): { name: string; card_id: string | null } | null => {
  for (const p of e.parts) if ("card" in p) return p.card;
  return null;
};

/** How far back (log lines) the card that ended it is looked for, in the turn of the loss. */
const LOOK_BACK = 6;

/**
 * The card the table log names just before ``name`` lost the game (the trigger that resolved, the creature that dealt the damage),
 * from the last "… loses the game" line; null when none is named close by. The log is this viewer's (hidden cards stay hidden).
 */
export function lossSource(log: LogEntryView[], name: string): { name: string; card_id: string | null } | null {
  const at = findLast(log, (e) => text(e).includes(`${name} loses the game`));
  if (at < 0) return null;
  const turn = log[at]!.turn;
  for (let i = at; i >= 0 && i >= at - LOOK_BACK; i--) {
    const e = log[i]!;
    if (e.turn !== turn) break;
    const c = firstCard(e);
    if (c) return c;
  }
  return null;
}

/**
 * -- loss sources -- the card that made ``me`` lose: the one the rules recorded with the loss (``rules.lost_source``: Final Fortune's
 * delayed trigger, the Lightning Bolt that took the life to 0), else the log's guess (``lossSource``), else null.
 */
export function endingSource(view: Pick<GameView, "rules" | "log">, me: string, name: string): { name: string; card_id: string | null } | null {
  return view.rules?.lost_source?.[me] ?? lossSource(view.log ?? [], name);
}

function findLast<T>(xs: T[], ok: (x: T) => boolean): number {
  for (let i = xs.length - 1; i >= 0; i--) if (ok(xs[i]!)) return i;
  return -1;
}

/** The life to tick down on the screen: from where it stood when the last turn's changes began, to where it ended. */
export function lifeTick(p: Pick<PlayerView, "life" | "life_history"> | undefined): { from: number; to: number } {
  if (!p) return { from: 0, to: 0 };
  const h = p.life_history ?? [];
  const last = h[h.length - 1];
  if (!last) return { from: p.life, to: p.life };
  const first = h.find((x) => x.turn === last.turn) ?? last;
  return { from: first.before, to: p.life };
}

/** The ticking number at ``t`` (0–1) of the way, eased out (fast first, settling on the final value). */
export function tickAt(from: number, to: number, t: number): number {
  const k = Math.min(1, Math.max(0, t));
  const eased = 1 - (1 - k) ** 3;
  return Math.round(from + (to - from) * eased);
}

/** The line under the word for the victory and draw variants (the defeat one is ``causeLine``). */
export function otherLine(view: GameView, variant: EndingVariant): string {
  const dummies = view.players.filter((p) => p.dummy && !p.left);
  if (variant === "victory") return dummies.length > 1 ? `Every target dummy is out (${dummies.length}).` : `${dummies[0]?.name ?? "The target dummy"} is out.`;
  return view.rules?.draw_reason ? `${view.rules.draw_reason}.` : "The game is a draw.";
}
