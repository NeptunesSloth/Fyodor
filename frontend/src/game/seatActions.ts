/**
 * The scripted tables' seat buttons (Oops I Baked a Pie): Untap, Draw, Scry, Mill and Reveal, by your mat. One
 * definition for both tables: the 2D table's round buttons beside your mat (game/SeatButtons.tsx) and the 3D
 * table's physical buttons on the table (table3d/seatProps.ts). Click does one, right-click three, or hover a
 * button and type a number.
 */
import { useGame } from "../state/gameStore";
import { draw, send } from "./actions";

export type SeatActionId = "untap" | "draw" | "scry" | "mill" | "reveal";

export const SEAT_ACTIONS: { id: SeatActionId; label: string; color: string; title: string }[] = [
  { id: "untap", label: "Untap", color: "#e0b43c", title: "Untap all your permanents (U)" },
  { id: "draw", label: "Draw", color: "#5aa64f", title: "Draw: click 1, right-click 3, or hover and type a number" },
  { id: "scry", label: "Scry", color: "#4f86c9", title: "Scry: look at the top cards (click 1, right-click 3, or hover and type a number)" },
  { id: "mill", label: "Mill", color: "#c4483c", title: "Mill: click 1, right-click 3, or hover and type a number" },
  { id: "reveal", label: "Reveal", color: "#b8b2a3", title: "Reveal the top card(s): click 1, right-click 3, or hover and type a number" },
];

const circle = (cx: number, cy: number, r: number) => `M${cx - r} ${cy}a${r} ${r} 0 1 0 ${2 * r} 0a${r} ${r} 0 1 0 ${-2 * r} 0`;

/**
 * Each button's icon (24×24, stroked), after the Oops buttons: an untap arrow, a card coming off the library, an
 * eye, a skull, a magnifying glass. SVG path data, so the 2D buttons and the 3D table's canvas (Path2D) draw the
 * same thing.
 */
export const SEAT_ICONS: Record<SeatActionId, string[]> = {
  untap: ["M19 12a7 7 0 1 1-2.1-5", "M19.5 3.5v4.4h-4.4"],
  draw: ["M7.5 9.5h9v11h-9z", "M12 2.5v8", "M8.8 5.6l3.2-3.1 3.2 3.1"],
  scry: ["M2 12c2.6-4.2 6-6.3 10-6.3s7.4 2.1 10 6.3c-2.6 4.2-6 6.3-10 6.3S4.6 16.2 2 12z", circle(12, 12, 3)],
  mill: ["M12 3a7 7 0 0 0-4 12.7V20h8v-4.3A7 7 0 0 0 12 3z", circle(9.4, 11, 1.4), circle(14.6, 11, 1.4), "M10.5 20v-2.2M13.5 20v-2.2"],
  reveal: [circle(10.5, 10.5, 6), "M15 15l5.8 5.8"],
};

/** Do a seat button's action, n times over (Untap ignores n). */
export function runSeatAction(id: SeatActionId, n: number, me: string): void {
  if (n < 1) return;
  if (id === "untap") void send({ type: "untap_all", player: me });
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
    if (!id || id === "untap" || !/^[0-9]$/.test(key)) return false;
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
