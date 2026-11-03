/**
 * The scripted tables' seat buttons (Oops I Baked a Pie): Untap, Draw, Scry, Mill, Reveal and Mulligan, by your mat. One
 * definition for both tables: the 2D table's round buttons beside your mat (game/SeatButtons.tsx) and the 3D
 * table's physical buttons on the table (table3d/seatProps.ts). Click does one, right-click three, or hover a
 * button and type a number.
 */
import { useGame } from "../state/gameStore";
import { draw, send } from "./actions";
import { isOut } from "./outOfGame";

export type SeatActionId = "untap" | "draw" | "scry" | "mill" | "reveal" | "mulligan";

/** In the Oops table's order, left to right along your mat's near edge; Mulligan sits apart, to the right. */
export const SEAT_ACTIONS: { id: SeatActionId; label: string; title: string }[] = [
  { id: "untap", label: "Untap", title: "Untap all your permanents (U)" },
  { id: "draw", label: "Draw", title: "Draw: click 1, right-click 3, or hover and type a number" },
  { id: "scry", label: "Scry", title: "Scry: look at the top cards (click 1, right-click 3, or hover and type a number)" },
  { id: "mill", label: "Mill", title: "Mill: click 1, right-click 3, or hover and type a number" },
  { id: "reveal", label: "Reveal", title: "Reveal the top card(s): click 1, right-click 3, or hover and type a number" },
  { id: "mulligan", label: "Mulligan", title: "Mulligan: shuffle your hand into your library and draw 7 (Ctrl+Z undoes it)" },
];

/** Do a seat button's action, n times over (Untap and Mulligan happen once). */
export function runSeatAction(id: SeatActionId, n: number, me: string): void {
  if (n < 1 || isOut(useGame.getState().view, me)) return; // -- out of the game -- the buttons are gone for them (game/outOfGame.ts)
  if (id === "untap") void send({ type: "untap_all", player: me });
  else if (id === "mulligan") void send({ type: "mulligan", player: me });
  else if (id === "draw") void draw(me, n);
  else if (id === "mill") void send({ type: "mill", player: me, count: n });
  else if (id === "reveal") void send({ type: "reveal_top", player: me, count: n });
  else void send({ type: "look_top", player: me, count: n }).then((ok) => ok && useGame.getState().openBrowser({ zone: `${me}:library`, title: `Scry ${n}: drag cards to the bottom, or leave them on top`, limit: n }));
}

/**
 * Typing a number over a hovered button, as on the Tabletop Simulator tables: digits build the count (shown on the
 * button), and a short pause does the action that many times.
 */
export class TypedCount {
  private id: SeatActionId | null = null;
  private digits = "";
  private timer = 0;
  constructor(private onShow: (id: SeatActionId | null, n: string) => void, private onDone: (id: SeatActionId, n: number) => void) {}

  /** A key while `id` is hovered; true if it was a digit for the button. */
  key(id: SeatActionId | null, key: string): boolean {
    if (!id || id === "untap" || id === "mulligan" || !/^[0-9]$/.test(key)) return false;
    this.digits = `${this.id === id ? this.digits : ""}${key}`.slice(0, 3);
    this.id = id;
    this.onShow(id, this.digits);
    window.clearTimeout(this.timer);
    this.timer = window.setTimeout(() => {
      const [done, n] = [this.id, Number(this.digits)];
      this.id = null;
      this.digits = "";
      this.onShow(null, "");
      if (done) this.onDone(done, n);
    }, 900);
    return true;
  }

  dispose(): void {
    window.clearTimeout(this.timer);
  }
}

/**
 * Clicks on a counter gathered into one change (life on the 3D hearts): three quick clicks send "−3" once, one log
 * line and one undo step, and `onPending` shows the change on the way.
 */
export class Batcher {
  private sums = new Map<string, number>();
  private timers = new Map<string, number>();
  constructor(private commit: (key: string, delta: number) => void, private onPending: (key: string, pending: number) => void, private wait = 650) {}

  bump(key: string, delta: number): void {
    const sum = (this.sums.get(key) ?? 0) + delta;
    this.sums.set(key, sum);
    this.onPending(key, sum);
    window.clearTimeout(this.timers.get(key));
    this.timers.set(key, window.setTimeout(() => this.flush(key), this.wait));
  }

  pending(key: string): number {
    return this.sums.get(key) ?? 0;
  }

  private flush(key: string): void {
    const sum = this.sums.get(key) ?? 0;
    this.sums.delete(key);
    this.timers.delete(key);
    this.onPending(key, 0);
    if (sum) this.commit(key, sum);
  }

  dispose(): void {
    for (const key of [...this.timers.keys()]) {
      window.clearTimeout(this.timers.get(key));
      this.flush(key); // leaving mid-count still counts
    }
  }
}
