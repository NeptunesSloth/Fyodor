/**
 * -- target dummy -- Sandbox's practice opponent (docs/MACROS_AND_SOLO.md): a seat with no deck that never takes a turn; the server
 * answers its priority and choices. The table only offers the tools around it: add it, reset it, spawn test cards for it.
 */
import type { MenuItem } from "../components/ContextMenu";
import type { Action, GameView, PlayerView } from "../types/game";

/** The table's target dummy (one at most). */
export function dummyOf(view: GameView | null | undefined): PlayerView | undefined {
  return view?.players.find((p) => p.dummy && !p.left);
}

/** Whether a dummy is out of the game (lost to damage, poison or commander damage): Reset dummy brings it back. */
export function dummyIsOut(view: GameView | null | undefined): boolean {
  const d = dummyOf(view);
  return !!d && !!view?.rules && (d.id in (view.rules.lost ?? {}) || (view.rules.conceded ?? []).includes(d.id));
}

/** Whose battlefield Spawn a card can put a test card on: yours, and the dummy's when there is one. */
export function spawnOwners(view: GameView | null | undefined): { id: string | null; label: string }[] {
  const d = dummyOf(view);
  return d ? [{ id: null, label: "You" }, { id: d.id, label: d.name }] : [];
}

/** The Solo tools' dummy entries (the host's: seating and resetting it are table-level tools). */
export function dummyMenu(view: GameView | null | undefined, isHost: boolean, send: (a: Action) => unknown): MenuItem[] {
  if (!isHost || !view) return [];
  const d = dummyOf(view);
  if (!d) {
    const allowed = !!view.game.settings.allow_test_objects;
    const full = view.players.filter((p) => !p.left).length >= 6;
    return [{ label: "Add a target dummy", disabled: !allowed || full, hint: !allowed ? "off at this table" : full ? "the table is full" : "an opponent to hit",
      onClick: () => void send({ type: "add_dummy" }) }];
  }
  return [{ label: dummyIsOut(view) ? "Restore dummy…" : "Reset dummy…", hint: `${d.life} life`,
    onClick: () => { if (window.confirm(`Reset ${d.name}: life back to the start, poison and commander damage cleared, its permanents removed${dummyIsOut(view) ? ", back in the game" : ""}?`)) void send({ type: "reset_dummy" }); } }];
}
