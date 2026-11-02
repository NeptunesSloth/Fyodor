import { useEffect, useState } from "react";
import { toast, toastError } from "../components/Toasts";
import type { Signal } from "../services/gameSocket";
import { REACTIONS, sendSignal } from "../services/night";
import { perspective, useGame } from "../state/gameStore";
import { usePrefs } from "../state/prefs";
import { SPECTATOR, type GameView } from "../types/game";
import { play } from "./sound";

/*
 * Soft social signals (TABLETOP_QOL_MILESTONE #13-14): a nudge to the player the table is waiting
 * on, and reactions from spectators and players who are already out. The server rate limits both;
 * they never touch game state, and each player can turn them off in Settings. The host can also turn
 * reactions off for the whole table (Host tools); the server then refuses them.
 */

/** Who the table is waiting on: the player deciding, the one with priority, else the active player. */
export function waitingOn(view: GameView): string {
  return view.rules?.decision?.player ?? view.rules?.priority ?? view.turn.active_player;
}

const NUDGE_COOLDOWN = 30_000;

/** "Nudge" beside the dial's "Waiting for …" (LAN tables only; never to yourself). */
export function NudgeButton({ view, me }: { view: GameView; me: string }) {
  const [until, setUntil] = useState(0);
  const [, tick] = useState(0);
  useEffect(() => {
    if (until <= Date.now()) return;
    const t = window.setTimeout(() => tick((n) => n + 1), until - Date.now());
    return () => window.clearTimeout(t);
  }, [until]);
  const target = waitingOn(view);
  if (view.game.mode !== "lan" || view.viewer === SPECTATOR || !target || target === me) return null;
  const name = view.players.find((p) => p.id === target)?.name ?? target;
  const cooling = until > Date.now();
  const nudge = async () => {
    setUntil(Date.now() + NUDGE_COOLDOWN);
    try {
      await sendSignal(view.game.id, "nudge");
      toast(`Nudged ${name}`);
    } catch (e) {
      toastError(e);
    }
  };
  return (
    <button className="tt-btn ghost td-nudge" data-testid="nudge" disabled={cooling} onClick={() => void nudge()}
      title={cooling ? "You can nudge again in a moment" : `Remind ${name} that the table is waiting`}>
      Nudge
    </button>
  );
}

interface Bubble { id: number; name: string; emoji: string }
let bubbleId = 0;

/** Nudges to me become one quiet toast; reactions float briefly at the bottom left. */
export function SignalLayer() {
  const view = useGame((s) => s.view);
  const actingAs = useGame((s) => s.actingAs);
  const nudges = usePrefs((s) => s.nudges);
  const muted = !usePrefs((s) => s.reactions);
  const tableOff = useGame((s) => s.view?.game.night?.reactions === false);  // the host's table-wide switch
  const reactions = !muted && !tableOff;
  const [bubbles, setBubbles] = useState<Bubble[]>([]);
  useEffect(() => {
    const on = (e: Event) => {
      const sig = (e as CustomEvent<Signal>).detail;
      if (sig.kind === "nudge" && nudges) {
        toast(`${sig.from_name} nudged you: the table is waiting on your action.`);
        play("response");
      } else if (sig.kind === "react" && reactions && sig.emoji) {
        const b = { id: ++bubbleId, name: sig.from_name, emoji: sig.emoji };
        setBubbles((xs) => [...xs.slice(-4), b]);
        window.setTimeout(() => setBubbles((xs) => xs.filter((x) => x.id !== b.id)), 3200);
      }
    };
    window.addEventListener("fyodor:signal", on);
    return () => window.removeEventListener("fyodor:signal", on);
  }, [nudges, reactions]);
  if (!view) return null;
  const me = perspective(view, actingAs);
  const r = view.rules;
  const out = view.viewer === SPECTATOR || (!!r && (r.conceded.includes(me) || me in r.lost));
  return (
    <>
      {bubbles.length > 0 && (
        <ul className="signal-feed" aria-live="polite" aria-label="Reactions">
          {bubbles.map((b) => <li key={b.id}><span className="signal-emoji" aria-hidden>{b.emoji}</span>{b.name}</li>)}
        </ul>
      )}
      {out && view.game.mode === "lan" && !tableOff && <ReactionBar gameId={view.game.id} />}
    </>
  );
}

function ReactionBar({ gameId }: { gameId: string }) {
  const [busy, setBusy] = useState(false);
  const react = async (emoji: string) => {
    setBusy(true);
    try {
      await sendSignal(gameId, "react", emoji);
    } catch (e) {
      toastError(e);
    } finally {
      window.setTimeout(() => setBusy(false), 3000);
    }
  };
  return (
    <div className="signal-bar" role="toolbar" aria-label="React">
      {REACTIONS.map((e) => (
        <button key={e} className="signal-btn" disabled={busy} onClick={() => void react(e)} aria-label={`React ${e}`}>{e}</button>
      ))}
    </div>
  );
}
