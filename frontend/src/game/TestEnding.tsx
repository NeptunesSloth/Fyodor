import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import { CardFace } from "../cards/CardFace";
import { toastError } from "../components/Toasts";
import { api } from "../services/api";
import { seatToken } from "../services/games";
import { useCard } from "../state/cardCache";
import { perspective, useGame } from "../state/gameStore";
import { usePrefs } from "../state/prefs";
import type { GameView } from "../types/game";
import { send } from "./actions";
import { useIsHost } from "./HostTools";
import { playEndScene, type EndPlay } from "./motion/endScene";
import { testEnding, type TestEnding as Ending } from "./nightEnding";
import { ENDING_WORD, causeLine, combatLine, combatLoss, endingSource, endingVariant, lifeTick, otherLine, tickAt } from "./testEndingBits";
import "./testEnding.css";

/** -- test-table ending -- undo back to just before the action that ended the test for this seat (app/api/games.py, test/take-back). */
const takeBack = (gameId: string, as: string | null) => {
  const t = seatToken(gameId);
  return api.post<GameView>(`/games/${gameId}/test/take-back`, { as }, t ? { "X-Seat-Token": t } : {});
};

/** The word settles in over this long (ms at 1×: the research doc's game-end band, 600–1200 ms); the rest follows it. */
const INTRO_MS = 1100;
/** The life ticks down from here, for this long (ms at 1×). */
const TICK_AT = 450;
const TICK_MS = 750;

/**
 * -- test-table ending -- a test against target dummies has no pod result to confirm, so when it ends at this seat (you lost or
 * conceded, every dummy is out, or a draw) the game ends here like a game: the table dims and greys under a heavy vignette, DEFEAT
 * (or VICTORY, or DRAW) settles in, then the cause, the card the rules recorded with the loss (else the one the log names just before
 * it), and your life ticking to its last value,
 * and a game menu. Take it back undoes the action that ended it; Start over deals a new game at the same table; Look at the board
 * (or Escape) fades it away to a small tab that brings it back; Leave goes back to the Play page. The table reacts with the
 * end-of-game scene (motion/endScene.ts: both renderers, and its sting when sound is on). Click or Space skips the settling in;
 * reduced motion shows it at once; the player's animation speed scales it. The server decides everything; only public facts show.
 */
export function TestEnding() {
  const view = useGame((s) => s.view);
  const actingAs = useGame((s) => s.actingAs);
  const me = view ? perspective(view, actingAs) : "";
  const ending = view ? testEnding(view, me) : null;
  if (!view || !ending) return null;
  return <EndingScreen key={ending.key} view={view} me={me} ending={ending} />;
}

function EndingScreen({ view, me, ending }: { view: GameView; me: string; ending: Ending }) {
  const isHost = useIsHost();
  const speed = usePrefs((s) => (s.animationSpeed > 0 ? s.animationSpeed : 1));
  const reducedPref = usePrefs((s) => s.reducedMotion);
  const reduced = reducedPref || (typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches);
  const variant = endingVariant(ending.kind);
  const [looking, setLooking] = useState(false);
  const [settled, setSettled] = useState(reduced);
  const [busy, setBusy] = useState(false);
  const primary = useRef<HTMLButtonElement>(null);
  const scene = useRef<EndPlay | null>(null);

  const mine = view.players.find((p) => p.id === me);
  const tick = lifeTick(mine);
  const [life, setLife] = useState(reduced ? tick.to : tick.from);
  const source = variant === "defeat" && mine ? endingSource(view, me, mine.name) : null;
  const card = useCard(source?.card_id ?? null);
  const r = view.rules;
  const gang = variant === "defeat" ? combatLoss(view, me) : 0;
  const line = variant === "defeat" ? (gang > 1 ? combatLine(gang) : causeLine(r?.lost[me], !!r?.conceded.includes(me))) : otherLine(view, variant);
  const winner = variant === "defeat" && r?.winner ? view.players.find((p) => p.id === r.winner)?.name : null;
  const ms = (n: number) => (reduced ? 0 : Math.round(n / speed));

  const settle = useCallback(() => {
    setSettled(true);
    setLife(tick.to);
  }, [tick.to]);

  // the table's own end-of-game reaction and its sting, once per ending (both renderers); stopped when the screen goes
  useEffect(() => {
    scene.current = playEndScene(variant, () => undefined);
    return () => scene.current?.stop();
  }, [variant]);

  // the word settles in, then the life ticks to its last value
  useEffect(() => {
    if (settled) return;
    const done = window.setTimeout(settle, ms(INTRO_MS + TICK_AT));
    let raf = 0;
    const start = performance.now() + ms(TICK_AT);
    const step = (now: number) => {
      const t = (now - start) / Math.max(1, ms(TICK_MS));
      if (t >= 0) setLife(tickAt(tick.from, tick.to, t));
      if (t < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => {
      window.clearTimeout(done);
      cancelAnimationFrame(raf);
    };
  }, [settled]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (settled && !looking) primary.current?.focus({ preventScroll: true });
  }, [settled, looking]);

  // Space or Enter skips the settling in; Escape looks at the board (the table's keys wait while the screen is up)
  useEffect(() => {
    if (looking) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        scene.current?.stop();
        setLooking(true);
        return;
      }
      if (!settled && (e.key === " " || e.key === "Enter")) {
        e.preventDefault();
        e.stopPropagation();
        settle();
      }
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [looking, settled, settle]);

  const run = async (work: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await work();
    } catch (e) {
      toastError(e);
    } finally {
      setBusy(false);
    }
  };
  const local = view.game.mode === "local";
  const word = ENDING_WORD[variant];
  const look = () => {
    scene.current?.stop();
    setLooking(true);
  };

  if (looking) {
    return (
      <button className={`te-tab ${variant}`} data-testid="test-ending-tab" onClick={() => setLooking(false)}
        title="The test is over: show the end screen again">
        <span className="te-tab-word">{word}</span>
        <span className="te-tab-more">Show</span>
      </button>
    );
  }

  return (
    <div className={`te-scene ${variant} ${settled ? "settled" : "intro"} ${reduced ? "instant" : ""}`}
      style={{ "--te-intro": `${ms(INTRO_MS)}ms` } as CSSProperties}
      role="dialog" aria-modal="true" aria-labelledby="te-word" aria-describedby="te-cause" data-testid="test-ending"
      onPointerDown={() => { if (!settled) settle(); }}>
      <div className="te-shade" aria-hidden />
      <div className="te-stage">
        <h2 id="te-word" className="te-word">{word}</h2>
        <div className="te-rule" aria-hidden />
        <p id="te-cause" className="te-cause">
          {source && <><b className="te-source">{source.name}</b><span className="te-dash" aria-hidden> — </span></>}
          {line}
          {winner && <span className="te-winner"> {winner} wins.</span>}
        </p>
        <div className="te-facts">
          {source && card && <span className="te-card" aria-hidden><CardFace card={card} size="normal" /></span>}
          {mine && (
            <span className="te-life" aria-label={`Your life: ${tick.to}`}>
              <span className="te-life-label">Your life</span>
              <span className="te-life-num" aria-hidden>{life}</span>
              <span className="te-life-was">{tick.from !== tick.to ? `from ${tick.from} · ` : ""}turn {view.turn.number}</span>
            </span>
          )}
        </div>
        <nav className="te-menu" aria-label="What next">
          <button ref={primary} className="te-btn primary" disabled={busy} data-testid="test-ending-takeback"
            onClick={() => void run(() => takeBack(view.game.id, local ? me : null))}>
            <span className="te-btn-name">Take it back</span>
            <span className="te-btn-hint">Undo the action that ended it</span>
          </button>
          {isHost && (
            <button className="te-btn" disabled={busy} data-testid="test-ending-restart"
              onClick={() => void run(() => send({ type: "restart_game", draw: 7, fresh: true }))}>
              <span className="te-btn-name">Start over</span>
              <span className="te-btn-hint">{view.players.some((p) => p.bot) ? "Same decks and seats, reshuffled" : "Same decks and dummies, reshuffled"}</span>
            </button>
          )}
          <button className="te-btn" data-testid="test-ending-keep" onClick={look}>
            <span className="te-btn-name">Look at the board</span>
            <span className="te-btn-hint">Esc</span>
          </button>
          <a className="te-btn quiet" href="#/play" data-testid="test-ending-leave">
            <span className="te-btn-name">Leave</span>
            <span className="te-btn-hint">Back to Play</span>
          </a>
        </nav>
      </div>
    </div>
  );
}
