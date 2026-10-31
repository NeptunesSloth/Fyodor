/**
 * Turn alert: when the table starts waiting on me and this tab is in the background (looking up a card in another
 * tab, say), the tab title flashes "● Your turn" and a short chime plays once. It stops as soon as I come back or
 * the table stops waiting. LAN tables only (a hot-seat table is one shared screen). Settings → Turn alert.
 */
import { useEffect } from "react";
import { perspective, useGame } from "../state/gameStore";
import { usePrefs } from "../state/prefs";
import { SPECTATOR, type GameView } from "../types/game";
import { waitingOn } from "./Signals";
import { play } from "./sound";

/** What the table is waiting on me for, or null. */
export function waitReason(view: GameView, me: string): string | null {
  if (view.viewer === SPECTATOR || view.game.mode !== "lan") return null;
  if (view.rules?.decision?.player === me) return "Your decision";
  if (view.response?.waiting.includes(me)) return "Your response";
  if (waitingOn(view) !== me) return null;
  return view.turn.active_player === me ? "Your turn" : "Your priority";
}

const FLASH_MS = 1100;

export function useTurnAlert(): void {
  const reason = useGame((s) => (s.view ? waitReason(s.view, perspective(s.view, s.actingAs)) : null));
  const enabled = usePrefs((s) => s.turnAlert);
  useEffect(() => {
    // another tab, or another window in front (the game on a second monitor while you read a card elsewhere)
    if (!enabled || !reason || (!document.hidden && document.hasFocus())) return;
    const original = document.title;
    const alert = `● ${reason} — ${original}`;
    let on = true;
    document.title = alert;
    play("turn");
    const timer = window.setInterval(() => {
      on = !on;
      document.title = on ? alert : original;
    }, FLASH_MS);
    const stop = () => {
      window.clearInterval(timer);
      document.title = original;
    };
    const onBack = () => { if (!document.hidden && document.hasFocus()) stop(); };
    document.addEventListener("visibilitychange", onBack);
    window.addEventListener("focus", onBack);
    return () => {
      document.removeEventListener("visibilitychange", onBack);
      window.removeEventListener("focus", onBack);
      stop();
    };
  }, [reason, enabled]);
}
