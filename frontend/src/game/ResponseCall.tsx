import { useEffect, useState } from "react";
import type { Signal } from "../services/gameSocket";
import { perspective, playerName, useGame } from "../state/gameStore";
import { usePrefs } from "../state/prefs";
import { SPECTATOR, type GameView } from "../types/game";
import { send } from "./actions";
import { keyLabel, matchHotkey } from "./hotkeys";
import { passPriority } from "./rules/intents";
import { usePassStop } from "./rules/passStop";
import { play } from "./sound";
import "./responseFlip.css";

/*
 * -- I have a response -- "wait, I have a response!", as at a real table (backend app/rules/response_call.py). A seated player who
 * doesn't hold priority while the game moves on (someone casting or passing, a stack about to resolve, a step about to end, a bot
 * acting, a long chain resolving) presses the dial's button or R: the server holds the game for them at the next priority they would
 * legally get (it never takes priority out of turn) and everyone hears it: "Alice has a response!" over the dial, in their seat colour
 * with their name (never colour alone). Pressing again cancels. The server decides; this only asks and shows.
 */

/** May ``me`` call for a hold now? A player in the game, rules engine running, who doesn't have priority to act right now. */
export function canCallResponse(view: GameView | null, me: string): boolean {
  const r = view?.rules;
  if (!view || !r || r.paused || view.viewer === SPECTATOR || !view.seat_order.includes(me)) return false;
  if (r.winner || r.draw_reason || r.conceded.includes(me) || me in (r.lost ?? {}) || r.controlled_by) return false;
  if (view.game.night?.result) return false;
  if (r.decision && (r.decision.player === me || r.decision.player === r.acting_as)) return false; // (the table waits on my own choice)
  const mine = (r.priority === me || (!!r.acting_as && r.priority === r.acting_as)) && !r.decision;
  return !mine || useGame.getState().resolving != null;
}

export const callResponse = (on: boolean) => send({ type: "set_prefs", respond: on });

/** What a hold waits for, in words ("before Lightning Bolt resolves" / "before this step ends"). */
export function holdWhen(view: GameView): string {
  const top = view.stack.length ? view.cards[view.stack[view.stack.length - 1]!] : undefined;
  if (!top) return "before this step ends";
  const name = "name" in top && top.name ? top.name : "the top of the stack";
  return `before ${name} resolves`;
}

/** The big "I have a response!" button on the dial while the game waits on someone else (pressed: called; again: cancel). */
export function ResponseCallButton({ view, me }: { view: GameView; me: string }) {
  const [asked, setAsked] = useState<boolean | null>(null); // (optimistic until the server's view says so)
  const keymap = usePrefs((s) => s.keymap);
  const called = (view.rules?.responding ?? []).includes(me);
  useEffect(() => setAsked(null), [called]);
  if (!canCallResponse(view, me)) return null;
  const on = asked ?? called;
  const key = keyLabel("respond", keymap);
  const press = () => {
    setAsked(!on);
    void callResponse(!on).then((ok) => { if (!ok) setAsked(null); });
  };
  return (
    <div className={`resp-call${on ? " on" : ""}`}>
      <button type="button" className="resp-call-btn" data-testid="response-call" aria-pressed={on} onClick={press}
        title={on ? `Cancel your call: the game goes on as usual${key ? ` (${key})` : ""}`
          : `Stop the game for your answer: you get priority ${holdWhen(view)}, whatever your stops say. Everyone hears it${key ? ` (${key})` : ""}`}>
        <span className="resp-call-word">{on ? "Response called" : "I have a response!"}</span>
        {key && <kbd className="resp-call-key" aria-hidden>{key}</kbd>}
      </button>
      <p className="resp-call-hint" role="status">{on ? `You get priority ${holdWhen(view)} · press again to cancel` : "Wait! Hold the game for your answer"}</p>
    </div>
  );
}

interface Shout { id: number; from: string; name: string; at: number }
let shoutId = 0;
const SHOUT_MS = 3200;

/**
 * Over the dial: "Alice has a response!" when someone calls (the server's shout reaches every table at once, before the action lands),
 * then a quiet line while they wait for priority. Reduced motion: no slide, just there. Also R and Shift+Space (Resolve all) here.
 */
export function ResponseShout() {
  const view = useGame((s) => s.view);
  const actingAs = useGame((s) => s.actingAs);
  const [shouts, setShouts] = useState<Shout[]>([]);
  useEffect(() => {
    const on = (e: Event) => {
      const sig = (e as CustomEvent<Signal>).detail;
      if (sig.kind !== "response" || !sig.from) return;
      const s = useGame.getState();
      const me = s.view ? perspective(s.view, s.actingAs) : "";
      if (sig.from !== me) play("response");
      const shout = { id: ++shoutId, from: sig.from, name: sig.from_name, at: Date.now() };
      setShouts((xs) => [...xs.filter((x) => x.from !== sig.from).slice(-2), shout]);
      window.setTimeout(() => setShouts((xs) => xs.filter((x) => x.id !== shout.id)), SHOUT_MS);
    };
    window.addEventListener("fyodor:signal", on);
    return () => window.removeEventListener("fyodor:signal", on);
  }, []);
  useResponseKeys();
  if (!view) return null;
  const me = perspective(view, actingAs);
  const waiting = (view.rules?.responding ?? []).filter((p) => !shouts.some((s) => s.from === p));
  if (!shouts.length && !waiting.length) return null;
  const color = (pid: string) => view.players.find((p) => p.id === pid)?.color;
  return (
    <div className="resp-shouts" aria-live="assertive" data-testid="response-shouts">
      {shouts.map((s) => (
        <p key={s.id} className="resp-shout" data-testid="response-shout" style={{ ["--player-color" as string]: color(s.from) }}>
          <span className="resp-shout-seat" aria-hidden />
          {s.from === me ? <><b>You</b> called a response</> : <><b>{s.name}</b> has a response!</>}{/* (-- sweep B2 -- not "You have a response!" on the caller's own screen) */}
        </p>
      ))}
      {waiting.map((pid) => (
        <p key={pid} className="resp-wait" data-testid="response-waiting" style={{ ["--player-color" as string]: color(pid) }}>
          <span className="resp-shout-seat" aria-hidden />
          {pid === me ? "You get priority" : `${playerName(view, pid)} gets priority`} {holdWhen(view)}
        </p>
      ))}
    </div>
  );
}

/** R: call (or cancel) a hold while the game waits on someone else (with the manual response helper's window open, R stays its
 * Respond: game/GameScreen.tsx); Shift+Space: Resolve all while you have priority with a stack. */
function useResponseKeys() {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (target?.closest?.("input, textarea, select, [contenteditable]") || document.querySelector(".modal-backdrop")) return;
      const s = useGame.getState();
      const view = s.view;
      if (!view?.rules || view.response) return;
      const id: string | null = matchHotkey(e, usePrefs.getState().keymap); // ("resolve_all": game/hotkeys.ts)
      const me = perspective(view, s.actingAs);
      if (id === "respond" && canCallResponse(view, me)) {
        e.preventDefault();
        void callResponse(!(view.rules.responding ?? []).includes(me));
      } else if (id === "resolve_all") {
        const r = view.rules;
        const mine = (r.priority === me || (!!r.acting_as && r.priority === r.acting_as)) && !r.decision && !r.controlled_by;
        if (mine && view.stack.length && s.resolving == null) {
          e.preventDefault();
          usePassStop.getState().arm();
          void passPriority("stack_empty");
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}
