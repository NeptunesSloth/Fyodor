import { useEffect, useRef, useState } from "react";
import { toast, toastError } from "../components/Toasts";
import { ApiError } from "../services/api";
import type { Signal } from "../services/gameSocket";
import { sendPing, type PingTarget } from "../services/night";
import { perspective, useGame } from "../state/gameStore";
import { usePrefs } from "../state/prefs";
import { isVisible, SPECTATOR } from "../types/game";
import { pingable, pingPoint, pingTargetAt } from "./ping";
import { keyLabel } from "./hotkeys";

const TIP_KEY = "fyodor.tip.ping";

/** Once per browser: the first time you hover a card everyone can see at a LAN table, say how to ping it. */
function usePingTip(): void {
  useEffect(() => useGame.subscribe((s, prev) => {
    if (!s.hover || s.hover === prev.hover || !s.view || s.view.game.mode !== "lan" || s.view.viewer === SPECTATOR) return;
    if (!pingable(s.view, s.hover)) return;
    try {
      if (localStorage.getItem(TIP_KEY)) return;
      localStorage.setItem(TIP_KEY, "1");
    } catch {
      return;
    }
    const key = keyLabel("ping", usePrefs.getState().keymap) ?? "G";
    toast(`Tip: press ${key} (or Alt+click) to point at a card for everyone at the table.`);
  }), []);
}
import { play } from "./sound";

/*
 * Pings, Tabletop Simulator style: point at a card or a spot and press G (or Alt+click) and everyone at the table
 * sees a ring in your seat colour with your name, for a moment. The server relays it (only cards everyone can see)
 * and never logs, saves or replays it.
 */

const SHOW_MS = 2600;
const MOVE_TOLERANCE = 5;

interface Shown { id: number; x: number; y: number; name: string; color: string; mine: boolean; what: string; edge: boolean }
const EDGE = 28; // a ping off this screen (another camera angle) is pinned to the edge, facing where it is
let nextId = 0;

/** Send a ping for whatever is under this point (a quiet hint when there is nothing everyone can see there). */
export async function pingAt(clientX: number, clientY: number): Promise<void> {
  const s = useGame.getState();
  const view = s.view;
  if (!view || view.viewer === SPECTATOR) return;
  const target = pingTargetAt(view, clientX, clientY);
  if (!target) {
    toast("Point at a card everyone can see, or at a spot on a battlefield, to ping it");
    return;
  }
  try {
    await sendPing(view.game.id, target, view.game.mode === "local" ? perspective(view, s.actingAs) : undefined);
  } catch (e) {
    if (!(e instanceof ApiError && e.status === 429)) toastError(e);
  }
}

export function PingLayer() {
  usePingTip();
  const [shown, setShown] = useState<Shown[]>([]);
  const pointer = useRef<{ x: number; y: number } | null>(null);

  // where the pointer is, for the G key; Alt+click (without dragging: Alt-drag still places by hand)
  useEffect(() => {
    let down: { x: number; y: number } | null = null;
    const move = (e: PointerEvent) => { pointer.current = { x: e.clientX, y: e.clientY }; };
    const press = (e: PointerEvent) => { down = e.altKey && e.button === 0 ? { x: e.clientX, y: e.clientY } : null; };
    const release = (e: PointerEvent) => {
      if (down && e.altKey && Math.hypot(e.clientX - down.x, e.clientY - down.y) < MOVE_TOLERANCE && (e.target as Element)?.closest?.("main.table")) {
        void pingAt(e.clientX, e.clientY);
      }
      down = null;
    };
    const here = () => { if (pointer.current) void pingAt(pointer.current.x, pointer.current.y); };
    document.addEventListener("pointermove", move, { capture: true, passive: true }); // capture: the 3D canvas keeps its moves
    document.addEventListener("pointerdown", press, true);
    document.addEventListener("pointerup", release, true);
    window.addEventListener("fyodor:ping-here", here);
    return () => {
      document.removeEventListener("pointermove", move, true);
      document.removeEventListener("pointerdown", press, true);
      document.removeEventListener("pointerup", release, true);
      window.removeEventListener("fyodor:ping-here", here);
    };
  }, []);

  // pings from everyone (mine too: the server echoes it, so all screens agree on what was pointed at)
  useEffect(() => {
    const on = (e: Event) => {
      const sig = (e as CustomEvent<Signal>).detail;
      if (sig.kind !== "ping" || !usePrefs.getState().pings) return;
      const target: PingTarget | null = sig.card ? { card: sig.card }
        : sig.player && sig.x !== undefined && sig.y !== undefined ? { player: sig.player, x: sig.x, y: sig.y } : null;
      const at = target && pingPoint(target);
      if (!at) return;
      const view = useGame.getState().view;
      const color = view?.players.find((p) => p.id === sig.from)?.color ?? "#d0a45a";
      const mine = !!view && sig.from === perspective(view, useGame.getState().actingAs);
      const x = Math.max(EDGE, Math.min(window.innerWidth - EDGE, at.x));
      const y = Math.max(EDGE + 40, Math.min(window.innerHeight - EDGE, at.y));
      const card = sig.card ? view?.cards[sig.card] : undefined;
      const what = card && isVisible(card) ? card.name : "a spot on the table";
      const ping = { id: ++nextId, x, y, name: sig.from_name, color, mine, what, edge: x !== at.x || y !== at.y };
      setShown((xs) => [...xs.slice(-5), ping]);
      if (!mine) play("ping");
      window.setTimeout(() => setShown((xs) => xs.filter((x) => x.id !== ping.id)), SHOW_MS);
    };
    window.addEventListener("fyodor:signal", on);
    return () => window.removeEventListener("fyodor:signal", on);
  }, []);

  if (!shown.length) return null;
  return (
    <div className="ping-layer" aria-live="polite">
      {shown.map((p) => (
        <div key={p.id} className={`ping ${p.edge ? "edge" : ""}`} style={{ left: p.x, top: p.y, ["--ping-color" as string]: p.color }} data-testid="ping">
          <span className="ping-ring" aria-hidden />
          <span className="ping-ring late" aria-hidden />
          <span className="ping-dot" aria-hidden />
          <span className="ping-name">{p.mine ? "You" : p.name}<span className="sr-only"> pinged {p.what}{p.edge ? " (off screen)" : ""}</span></span>
        </div>
      ))}
    </div>
  );
}
