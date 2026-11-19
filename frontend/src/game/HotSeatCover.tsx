/**
 * -- hot-seat hand-off -- several players share this computer (a local table): when the table starts waiting on another of them (their
 * priority, their decision), an opaque cover says "Pass to Bob" over the whole screen. The view switches to Bob only once someone
 * clicks it (or presses Enter): until then the table shown is still the last player's, and Bob's hidden cards are never fetched while
 * the last player is looking. Never for a bot or a target dummy (the server plays them) and never at a LAN table (one screen each).
 * Settings → Hot-seat hand-off.
 */
import { useEffect, useRef } from "react";
import { useGame } from "../state/gameStore";
import { usePrefs } from "../state/prefs";
import type { GameView } from "../types/game";
import { isOut } from "./outOfGame";
import { waitingOn } from "./Signals";
import "./hotseat.css";

/** The player this screen should be handed to now, or null. */
export function handoffTarget(view: GameView): string | null {
  if (view.game.mode !== "local" || view.rules?.winner || !view.players.some((p) => p.id === view.viewer)) return null;
  const people = view.players.filter((p) => !p.bot && !p.dummy && !isOut(view, p.id));
  if (people.length < 2) return null;
  const who = waitingOn(view);
  return who !== view.viewer && people.some((p) => p.id === who) ? who : null;
}

export function HotSeatCover() {
  const target = useGame((s) => (s.view && !s.interim ? handoffTarget(s.view) : null));
  const view = useGame((s) => s.view);
  const enabled = usePrefs((s) => s.hotseatHandoff);
  const button = useRef<HTMLButtonElement>(null);
  // (it stays up until Bob's own view has arrived: the last player's table is what the store holds until then)
  const show = enabled && !!target;
  useEffect(() => { if (show) button.current?.focus(); }, [show]);
  if (!show || !view || !target) return null;
  const p = view.players.find((x) => x.id === target)!;
  const go = () => useGame.getState().setViewer(target);
  return (
    <div className="modal-backdrop hotseat-cover" role="dialog" aria-modal="true" aria-labelledby="hotseat-title" data-testid="hotseat-cover"
      style={{ ["--seat" as string]: p.color }} onClick={go}>
      <div className="hotseat-plate">
        <span className="hotseat-chip" aria-hidden>{p.name.slice(0, 1).toUpperCase()}</span>
        <h2 id="hotseat-title">Pass to {p.name}</h2>
        <p>{p.name}'s turn to act. The table stays hidden until {p.name} is ready.</p>
        <button ref={button} className="btn primary" data-testid="hotseat-ready">I'm {p.name}: show my view</button>
      </div>
    </div>
  );
}
