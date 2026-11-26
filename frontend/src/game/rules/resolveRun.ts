import type { GameView } from "../../types/game";
import { isVisible } from "../../types/game";

/**
 * -- smart resolve -- what one press of RESOLVE does (the server's ``own_triggers``, backend app/rules/engine.py own_run_over): the top
 * object, then on through the run of your own triggered abilities under it (six landfall triggers: one press), at most OWN_RUN. It
 * stops for anything else on top (your spell, someone else's object), a decision, or a card you drew that you could cast now.
 */
export const OWN_RUN = 20;

/** How many objects, from the top, are your own triggered abilities in a row (0: the top is something else). */
export function ownTriggerRun(view: GameView, me: string): number {
  let n = 0;
  for (let i = view.stack.length - 1; i >= 0 && n < OWN_RUN; i--) {
    const c = view.cards[view.stack[i]!];
    if (!c || !isVisible(c) || c.ability?.kind !== "triggered" || c.controller !== me) break;
    n++;
  }
  return n;
}

/** The big button's word: "Resolve", or "Resolve 6 triggers" when the press goes through a run of your own triggers. */
export function resolveVerb(view: GameView, me: string): string {
  const run = ownTriggerRun(view, me);
  return run > 1 ? `Resolve ${run}${run >= OWN_RUN && view.stack.length > OWN_RUN ? "+" : ""} triggers` : "Resolve";
}

export function resolveTitle(view: GameView, me: string): string {
  const run = ownTriggerRun(view, me);
  return run > 1
    ? `Resolve your ${run} triggered abilities on top, one after another. Stops and gives you priority back if anything else goes on the stack, ` +
      "you have a choice to make, or you draw a card you could cast now (P)"
    : "Resolve the top object of the stack. You get priority back after it resolves while anything is left on the stack, so you can " +
      "respond to each spell and to other players' triggers; a run of your own triggers under it goes on in the same press (P)";
}
