import { useEffect, useState } from "react";
import { toast, toastError } from "../components/Toasts";
import type { Signal } from "../services/gameSocket";
import { openMenu } from "../components/ContextMenu";
import { EMOTES, REACTIONS, sendSignal } from "../services/night";
import { perspective, useGame } from "../state/gameStore";
import { usePrefs } from "../state/prefs";
import { SPECTATOR, type GameView } from "../types/game";
import { play } from "./sound";
import { FlipButton, FlipLayer, TABLE_GLYPH } from "./TableFlip";

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
      // -- install update -- the host is installing an update: Fyodor closes and comes back (app/api/updates.py), the table returns with it
      const notice = sig as unknown as { kind: string; message?: string };
      if (notice.kind === "update") {
        toast(notice.message || "Updating — Fyodor will restart.", undefined, undefined, { sticky: true });
        return;
      }
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
          {bubbles.map((b) => (EMOTES as readonly string[]).includes(b.emoji)
            ? <li key={b.id} className="signal-said">{b.name}: <b>“{b.emoji}”</b></li>
            : <li key={b.id}><span className="signal-emoji" aria-hidden>{b.emoji}</span>{b.name}</li>)}
        </ul>
      )}
      {out && view.game.mode === "lan" && !tableOff && <ReactionBar gameId={view.game.id} />}
      {!out && view.game.mode === "lan" && !tableOff && <EmoteButton gameId={view.game.id} />}
      {/* -- flip the table -- (any table: a Sandbox test too), and everyone's view of a flip */}
      <FlipButton />
      <FlipLayer />
    </>
  );
}

/** Table talk for players still in the game: a fixed set, shown to everyone like a reaction (rate limited by the server). */
function EmoteButton({ gameId }: { gameId: string }) {
  const send = (text: string) => void sendSignal(gameId, "react", text).catch(toastError);
  return (
    <button className="signal-bar signal-emote tt-btn ghost" data-testid="emote" title="Say something to the table"
      onClick={(e) => openMenu(e, [...EMOTES.map((t) => ({ label: t, onClick: () => send(t) })),
        { label: `${TABLE_GLYPH} Flip the table…`, onClick: () => window.dispatchEvent(new Event("fyodor:flip-open")) }], "Say to the table")}>
      Emote
    </button>
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
