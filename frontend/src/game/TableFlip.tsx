import { useEffect, useRef, useState } from "react";
import { toast, toastError } from "../components/Toasts";
import { api } from "../services/api";
import { seatToken } from "../services/games";
import type { Signal } from "../services/gameSocket";
import { perspective, useGame } from "../state/gameStore";
import { usePrefs } from "../state/prefs";
import { SPECTATOR, type GameView } from "../types/game";
import { send } from "./actions";
import { motionMs, onMotionSkip } from "./motion/timing";
import { canConcede } from "./rules/intents";
import { play } from "./sound";
import "./responseFlip.css";

/*
 * -- flip the table -- the classic rage-quit, (╯°□°)╯︵ ┻━┻. "Just flip it" is a soft signal (backend app/api/night.py kind "flip":
 * once in 30 s per player, never logged or saved, nothing in the game changes); "Flip it and concede" is the ordinary concession
 * (104.3a, 800.4) with a log line, after which the server sends the flip (only ever for the player who conceded). Everyone sees the
 * flipper's side jolt up and settle back: 2D, their battlefield's cards tumble (CSS translate/rotate, never their positions); 3D,
 * their mat's cards fly up and drop back (table3d/tableFlip.ts). Reduced motion: no animation, just the shout. Any click or key skips.
 */

export const FLIP_GLYPH = "(╯°□°)╯︵ ┻━┻";
export const TABLE_GLYPH = "┻━┻";

const flipNow = (gameId: string, as?: string) => {
  const t = seatToken(gameId);
  return api.post(`/games/${gameId}/night/signal`, { kind: "flip", as_player: as ?? null }, t ? { "X-Seat-Token": t } : {});
};
export const concedeAndFlip = () => send({ type: "concede", flip: true });

function reducedMotion(): boolean {
  return !!usePrefs.getState().reducedMotion || (typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches);
}

/** May ``me`` flip at all (a seated player; the host's reactions switch also covers flips). */
export function canFlip(view: GameView | null, me: string): boolean {
  return !!view && view.viewer !== SPECTATOR && view.seat_order.includes(me) && view.game.night?.reactions !== false;
}

/** The two choices, as a small confirm (the flip button's, and the Emote menu's). ``onDone``: closed. */
export function FlipConfirm({ view, me, onDone }: { view: GameView; me: string; onDone: () => void }) {
  const first = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    first.current?.focus();
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") onDone(); };
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [onDone]);
  const concede = canConcede(view, me);
  const fun = async () => {
    onDone();
    try {
      await flipNow(view.game.id, view.game.mode === "local" ? me : undefined);
    } catch (e) {
      toastError(e);
    }
  };
  return (
    <div className="flip-confirm plaque" role="dialog" aria-label="Flip the table" data-testid="flip-confirm">
      <p className="flip-confirm-head"><span aria-hidden>{FLIP_GLYPH}</span> Flip the table?</p>
      <button ref={first} type="button" className="tt-btn" data-testid="flip-fun" onClick={() => void fun()}
        title="Everyone sees your side of the table flip. Nothing in the game changes (once every 30 seconds)">Just flip it (for fun)</button>
      {concede && (
        <button type="button" className="tt-btn danger" data-testid="flip-concede" onClick={() => { onDone(); void concedeAndFlip(); }}
          title="Concede the game (CR 104.3a) and flip the table on your way out">Flip it and concede</button>
      )}
      <button type="button" className="tt-btn ghost" data-testid="flip-cancel" onClick={onDone}>Keep playing</button>
    </div>
  );
}

/** "┻━┻ Flip" above Emote, bottom left: the two choices. */
export function FlipButton() {
  const view = useGame((s) => s.view);
  const actingAs = useGame((s) => s.actingAs);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const on = () => setOpen(true);
    window.addEventListener("fyodor:flip-open", on);
    return () => window.removeEventListener("fyodor:flip-open", on);
  }, []);
  if (!view) return null;
  const me = perspective(view, actingAs);
  const r = view.rules;
  // (out of the game: the reaction bar has this corner; the concession already had its flip)
  if (!canFlip(view, me) || (r && (r.conceded.includes(me) || me in (r.lost ?? {})))) return null;
  return (
    <div className="flip-anchor">
      {open && <FlipConfirm view={view} me={me} onDone={() => setOpen(false)} />}
      <button type="button" className="tt-btn ghost flip-btn" data-testid="flip-table" aria-expanded={open} aria-haspopup="dialog"
        title="Flip the table: for fun, or as you concede" onClick={() => setOpen(!open)}>
        <span className="flip-btn-glyph" aria-hidden>{TABLE_GLYPH}</span> Flip
      </button>
    </div>
  );
}

interface Glyph { id: number; x: number; y: number; name: string }
let glyphId = 0;

/** Everyone's side of the flip: the shout, the glyph over the flipper's side and the jolt (2D here; 3D: table3d/tableFlip.ts). */
export function FlipLayer() {
  const [glyphs, setGlyphs] = useState<Glyph[]>([]);
  useEffect(() => {
    const on = (e: Event) => {
      const sig = (e as CustomEvent<Signal>).detail;
      if (sig.kind !== "flip" || !sig.from) return;
      const s = useGame.getState();
      const me = s.view ? perspective(s.view, s.actingAs) : "";
      const who = sig.from === me ? "You" : sig.from_name;
      toast(`${who} ${sig.concede ? "conceded and flipped" : "flipped"} the table ${FLIP_GLYPH}`);
      play("shuffle");
      if (reducedMotion()) return;
      const three = !!document.querySelector("[data-testid='table-3d']");
      if (three) window.dispatchEvent(new CustomEvent("fyodor:table-flip", { detail: { player: sig.from } }));
      const board = document.querySelector<HTMLElement>(`[data-drop="${sig.from}:battlefield"]`);
      const rect = !three && board ? board.getBoundingClientRect() : null;
      const g = { id: ++glyphId, x: rect ? rect.left + rect.width / 2 : window.innerWidth / 2, y: rect ? rect.top + Math.min(rect.height / 2, 120) : window.innerHeight * 0.38, name: sig.from_name };
      setGlyphs((xs) => [...xs.slice(-2), g]);
      window.setTimeout(() => setGlyphs((xs) => xs.filter((x) => x.id !== g.id)), motionMs(1500, false) + 100);
      if (!three && board) flip2D(board);
    };
    window.addEventListener("fyodor:signal", on);
    return () => window.removeEventListener("fyodor:signal", on);
  }, []);
  useEffect(() => onMotionSkip(() => setGlyphs([])), []);
  return (
    <>
      {glyphs.map((g) => (
        <div key={g.id} className="flip-glyph" data-testid="flip-glyph" aria-hidden style={{ left: g.x, top: g.y, ["--flip-ms" as string]: `${motionMs(1500, false)}ms` }}>
          {FLIP_GLYPH}
        </div>
      ))}
    </>
  );
}

const MAX_2D = 60;

/** 2D: the board jolts, its cards jump up and tumble, then everything drops back (WAAPI on translate/rotate only, never the positions). */
export function flip2D(board: HTMLElement): void {
  const dur = motionMs(900, false);
  const anims: Animation[] = [];
  const mirrored = board.hasAttribute("data-mirrored");
  const away = mirrored ? 1 : -1; // (thrown away from its owner: down the screen for an opponent's board, up for mine)
  if (typeof board.animate !== "function") return;
  // (per-keyframe easing: the throw is quick, the fall slower; one easing over the whole effect would spend the arc in its first tenth)
  const up = "cubic-bezier(0.23, 1, 0.32, 1)";
  const down = "cubic-bezier(0.77, 0, 0.175, 1)";
  anims.push(board.animate([
    { translate: "0 0", rotate: "0deg", easing: up },
    { translate: `0 ${away * 10}px`, rotate: `${-away * 0.8}deg`, offset: 0.18, easing: down },
    { translate: `0 ${-away * 3}px`, rotate: `${away * 0.4}deg`, offset: 0.55, easing: up },
    { translate: "0 0", rotate: "0deg" },
  ], { duration: dur }));
  const cards = [...board.querySelectorAll<HTMLElement>(".table-card")].slice(0, MAX_2D);
  cards.forEach((el, i) => {
    const r = ((i * 7919) % 101) / 100;
    const r2 = ((i * 104729) % 97) / 96;
    const lift = 40 + 50 * r;
    const turn = (r2 - 0.5) * 70;
    anims.push(el.animate([
      { translate: "0 0", rotate: "0deg", easing: up },
      { translate: `${(r - 0.5) * 30}px ${away * lift}px`, rotate: `${turn}deg`, offset: 0.35, easing: down },
      { translate: `0 ${-away * 4}px`, rotate: `${turn * 0.08}deg`, offset: 0.85, easing: up },
      { translate: "0 0", rotate: "0deg" },
    ], { duration: dur, delay: Math.min(i * 8, 140) }));
  });
  const off = onMotionSkip(() => { for (const a of anims) a.finish(); });
  window.setTimeout(off, dur + 400);
}
