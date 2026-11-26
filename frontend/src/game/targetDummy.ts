/**
 * -- target dummy -- Sandbox's practice opponent (docs/MACROS_AND_SOLO.md): a seat with no deck that never takes a turn; the server
 * answers its priority and choices (up to MAX_DUMMIES of them). The table only offers the tools around it: add it, reset it, set how it
 * blocks, spawn test cards for it.
 */
import type { MenuItem } from "../components/ContextMenu";
import type { Action, DummyBlocks, GameView, PlayerView } from "../types/game";

/** How the dummy blocks with automation on (the server's setting: app/game/dummy.py); in the Sandbox start and Solo tools. */
export const DUMMY_BLOCKS: [DummyBlocks, string][] = [
  ["never", "Never"],
  ["chump", "Chump the biggest attacker"],
  ["all", "Block with everything it can"],
];

/** How many dummies a table may seat (the server's MAX_DUMMIES: app/game/handlers/dummy.py). */
export const MAX_DUMMIES = 3;
/** The dummy's seat colour (the server's: unpainted wood-and-steel grey). */
export const DUMMY_COLOR = "#8a8f98";

/** The table's target dummies still at the table, in seat order. */
export function dummiesOf(view: GameView | null | undefined): PlayerView[] {
  return view?.players.filter((p) => p.dummy && !p.left) ?? [];
}

/** The table's first target dummy. */
export function dummyOf(view: GameView | null | undefined): PlayerView | undefined {
  return dummiesOf(view)[0];
}

/** Whether a dummy (the first, or ``d``) is out of the game (lost to damage, poison or commander damage): Reset dummy brings it back. */
export function dummyIsOut(view: GameView | null | undefined, d: PlayerView | undefined = dummyOf(view)): boolean {
  return !!d && !!view?.rules && (d.id in (view.rules.lost ?? {}) || (view.rules.conceded ?? []).includes(d.id));
}

/** Whose battlefield Spawn a card can put a test card on: yours, and each dummy's when there are any. */
export function spawnOwners(view: GameView | null | undefined): { id: string | null; label: string }[] {
  const ds = dummiesOf(view);
  return ds.length ? [{ id: null, label: "You" }, ...ds.map((d) => ({ id: d.id, label: d.name }))] : [];
}

/** -- the Sandbox start's dummy seats -- the name a new dummy seat gets: the server's own default ("Target Dummy", then numbered). */
export function dummyName(index: number): string {
  return index === 0 ? "Target Dummy" : `Target Dummy ${index + 1}`;
}

/** A dummy seat set up on the Sandbox start: its name, how it blocks, and its own starting life ("": the table's). */
export interface DummySeat { name: string; blocks: DummyBlocks; life: string }

/** The add_dummy actions that seat ``seats`` (in order: the seat numbers follow it), at most MAX_DUMMIES. */
export function dummyActions(seats: DummySeat[]): Action[] {
  return seats.slice(0, MAX_DUMMIES).map((d, i) => {
    const life = Number(d.life);
    return {
      type: "add_dummy",
      blocks: d.blocks,
      name: d.name.trim() || dummyName(i),
      ...(d.life.trim() && Number.isInteger(life) && life >= 1 ? { life } : {}),
    };
  });
}

/** The dummy seats remembered by "Same as last time" (older records kept one checkbox: ``dummy`` and ``dummyBlocks``). */
export function rememberedDummies(last: { dummies?: DummySeat[]; dummy?: boolean; dummyBlocks?: DummyBlocks } | null): DummySeat[] {
  if (!last) return [];
  if (Array.isArray(last.dummies)) {
    return last.dummies.slice(0, MAX_DUMMIES).map((d, i) => ({ name: typeof d.name === "string" ? d.name : dummyName(i),
      blocks: DUMMY_BLOCKS.some(([k]) => k === d.blocks) ? d.blocks : "never", life: typeof d.life === "string" ? d.life : "" }));
  }
  return last.dummy ? [{ name: dummyName(0), blocks: last.dummyBlocks ?? "never", life: "" }] : [];
}

/** The Solo tools' dummy entries (the host's: seating and resetting them are table-level tools). */
export function dummyMenu(view: GameView | null | undefined, isHost: boolean, send: (a: Action) => unknown): MenuItem[] {
  if (!isHost || !view) return [];
  const ds = dummiesOf(view);
  const auto = !!view.rules; // (with automation off the dummy's cards are moved by hand: the setting waits for it)
  const several = ds.length > 1;
  const items = ds.flatMap((d): MenuItem[] => {
    const blocks = d.dummy_blocks ?? "never";
    const out = dummyIsOut(view, d);
    return [
      { label: `${out ? "Restore" : "Reset"} ${several ? d.name : "dummy"}…`, hint: `${d.life} life`,
        onClick: () => { if (window.confirm(`Reset ${d.name}: life back to the start, poison and commander damage cleared, its permanents removed${out ? ", back in the game" : ""}?`)) void send({ type: "reset_dummy", player: d.id }); } },
      { label: several ? `${d.name} blocks` : "Dummy blocks", hint: auto ? DUMMY_BLOCKS.find(([k]) => k === blocks)?.[1] : "with automation on",
        submenu: DUMMY_BLOCKS.map(([k, label]): MenuItem => k === blocks
          ? { label, hint: "current", disabled: true }
          : { label, onClick: () => void send({ type: "set_dummy", blocks: k, player: d.id }) }) },
    ];
  });
  if (ds.length < MAX_DUMMIES) {
    const allowed = !!view.game.settings.allow_test_objects;
    const full = view.players.filter((p) => !p.left).length >= 6;
    const add: MenuItem = { label: ds.length ? "Add another target dummy" : "Add a target dummy", disabled: !allowed || full,
      hint: !allowed ? "off at this table" : full ? "the table is full" : "an opponent to hit", onClick: () => void send({ type: "add_dummy" }) };
    return ds.length ? [...items, add] : [add];
  }
  return items;
}
