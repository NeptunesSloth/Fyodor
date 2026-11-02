import { useEffect, useRef, useState } from "react";
import { CardFace } from "../cards/CardFace";
import { toastError } from "../components/Toasts";
import { answerProposal, voteNext } from "../services/night";
import { useCardCache } from "../state/cardCache";
import { perspective, useGame } from "../state/gameStore";
import { usePrefs } from "../state/prefs";
import { SPECTATOR, type GameView, type NightInfo } from "../types/game";
import { Eliminated } from "./Eliminated";
import { useIsHost } from "./HostTools";
import { proposalSeat, showEliminated } from "./nightEnding";
import { PredictionsRecap } from "./Predictions";
import { SpectatorHub } from "./SpectatorHub";
import "./night.css";

/*
 * Game night moments (docs/GAME_NIGHT_FLOW.md): the short pre-game intro with the turn order and
 * its d20 rolls, a 3-2-1 countdown, the agree/decline bar for a proposed ending, and the result
 * spotlight with the rematch vote. Every number here comes from the server; the client only shows it. When the rules
 * engine ends the game the server opens the same proposal with the engine's result, so the spotlight and the vote follow
 * once the players confirm it.
 * Nothing blocks the game: the intro and the spotlight are skippable (click, Space, Esc) and scaled
 * by the player's animation speed; reduced motion keeps the fades and drops the movement.
 */

const seenKey = (kind: string, view: GameView) => `fyodor.night.${kind}.${view.game.id}.${view.game.night?.number ?? 1}`;
function seen(key: string): boolean {
  try {
    return sessionStorage.getItem(key) === "1";
  } catch {
    return false;
  }
}
function markSeen(key: string): void {
  try {
    sessionStorage.setItem(key, "1");
  } catch {
    /* private window: the moment may replay, which is harmless */
  }
}

/**
 * Automated browsers (the E2E suite) skip the timed intro and spotlight unless a test opts in with
 * localStorage "fyodor.nightScenes" = "1", the same convention as the renderer choice.
 */
function scenesOn(): boolean {
  try {
    if (localStorage.getItem("fyodor.nightScenes") === "1") return true;
  } catch {
    /* fall through */
  }
  return !navigator.webdriver;
}

/** Milliseconds scaled by the player's animation speed (reduced motion keeps the timing, not the movement). */
function useScale(): (ms: number) => number {
  const speed = usePrefs((s) => s.animationSpeed) || 1;
  return (ms) => ms / speed;
}

function useSkipKeys(active: boolean, skip: () => void) {
  useEffect(() => {
    if (!active) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === " " || e.key === "Escape" || e.key === "Enter") {
        e.preventDefault();
        e.stopPropagation();
        skip();
      }
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [active, skip]);
}

export function GameNight() {
  const view = useGame((s) => s.view);
  if (!view?.game.night) return null;
  return (
    <>
      {/* keyed per game of the night: a rematch replays the intro, a new result its spotlight */}
      <GameIntro key={`intro-${view.game.night.number}`} view={view} night={view.game.night} />
      <ProposalBar view={view} night={view.game.night} />
      <ResultScene key={`result-${view.game.night.number}`} view={view} night={view.game.night} />
      <Out view={view} />
      <SpectatorHub view={view} />
    </>
  );
}

/** The eliminated player's own moment (others never see it); gone once the game has a result or the rules ended it. */
function Out({ view }: { view: GameView }) {
  const actingAs = useGame((s) => s.actingAs);
  const me = perspective(view, actingAs);
  if (!showEliminated(view, me)) return null;
  return <Eliminated key={`${me}-${view.game.night?.number}`} view={view} me={me} sceneOn={scenesOn()} />;
}

// --------------------------------------------------------------------------- the intro

/** Seats in the order they take turns: from the player who goes first, around the table. */
function turnOrder(view: GameView): string[] {
  const order = view.seat_order;
  const first = Math.max(0, order.indexOf(view.turn.active_player));
  return [...order.slice(first), ...order.slice(0, first)];
}

function rollsOf(night: NightInfo, pid: string): number[] {
  return night.rolls.filter((r) => pid in r).map((r) => r[pid]!);
}

function GameIntro({ view, night }: { view: GameView; night: NightInfo }) {
  const key = seenKey("intro", view);
  const fresh = view.turn.number === 1 && !night.result;
  const [stage, setStage] = useState<"order" | 3 | 2 | 1 | "done">(() => (fresh && scenesOn() && !seen(key) ? "order" : "done"));
  const scale = useScale();
  const skip = useRef(() => {
    markSeen(key);
    setStage("done");
  }).current;
  useSkipKeys(stage !== "done", skip);
  useEffect(() => {
    if (stage === "done") return;
    const wait = stage === "order" ? scale(2600 + view.seat_order.length * 90) : scale(520);
    const next = stage === "order" ? 3 : stage === 1 ? "done" : ((stage - 1) as 2 | 1);
    const t = window.setTimeout(() => (next === "done" ? skip() : setStage(next)), wait);
    return () => window.clearTimeout(t);
  }, [stage, scale, skip, view.seat_order.length]);
  if (stage === "done") return null;

  const source = night.order_source === "d20" ? "Everyone rolled a d20: highest goes first."
    : night.order_source === "winner_last" ? "Last game's winner goes last." : "Turn order";
  return (
    <div className="night-intro" role="dialog" aria-modal="true" aria-label={`Game ${night.number}: turn order`} data-testid="game-intro" onClick={skip}>
      {stage === "order" ? (
        <div className="night-card plaque-wrap">
          <div className="plaque night-plaque">
            <h2 className="night-title">Game {night.number}</h2>
            <p className="night-sub">{source}</p>
            <ol className="night-order">
              {turnOrder(view).map((pid, i) => {
                const p = view.players.find((x) => x.id === pid);
                const rolls = rollsOf(night, pid);
                return (
                  <li key={pid} className="night-row" style={{ "--i": i, "--seat": p?.color ?? "var(--frame)" } as React.CSSProperties}>
                    <span className="night-pos">{i + 1}</span>
                    <CommanderArt view={view} pid={pid} />
                    <span className="night-who">
                      <b>{p?.name ?? pid}{pid === view.viewer ? " (you)" : ""}</b>
                      <span>{p?.commanders.map((c) => c.name).join(" & ") || "No commander"}</span>
                    </span>
                    {night.previous_winner === pid && <span className="night-tag">Won last game</span>}
                    {rolls.length > 0 && (
                      <span className="night-dice" aria-label={`Rolled ${rolls.join(", then ")}`}>
                        {rolls.map((r, k) => <span key={k} className={`night-die ${k < rolls.length - 1 ? "tied" : ""}`}>{r}</span>)}
                      </span>
                    )}
                  </li>
                );
              })}
            </ol>
            <div className="night-foot">
              <span>{view.players.find((p) => p.id === view.turn.active_player)?.name} goes first</span>
              <button className="tt-btn ghost" onClick={skip}>Skip</button>
            </div>
          </div>
        </div>
      ) : (
        <div key={stage} className="night-count" aria-live="assertive">{stage}</div>
      )}
    </div>
  );
}

function CommanderArt({ view, pid }: { view: GameView; pid: string }) {
  const cmd = view.players.find((p) => p.id === pid)?.commanders[0];
  const card = useCardCache((s) => (cmd?.card_id ? s.cards[cmd.card_id] : undefined));
  return (
    <span className="night-art" aria-hidden>
      {card ? <CardFace card={card} size="small" /> : <span className="night-art-empty">{(cmd?.name ?? "?").slice(0, 1)}</span>}
    </span>
  );
}

// --------------------------------------------------------------------------- agreed ending (and the rules result)

function ProposalBar({ view, night }: { view: GameView; night: NightInfo }) {
  const actingAs = useGame((s) => s.actingAs);
  const [busy, setBusy] = useState(false);
  const p = night.proposal;
  const me = perspective(view, actingAs);
  const seat = proposalSeat(view, me);
  if (!p || !seat) return null;
  const local = view.game.mode === "local";
  const { what, waiting, mustAnswer } = seat;
  const nameOf = (pid: string) => view.players.find((x) => x.id === pid)?.name ?? pid;
  const answer = async (agree: boolean) => {
    setBusy(true);
    try {
      await answerProposal(view.game.id, agree, local ? me : undefined);
    } catch (e) {
      toastError(e);
    } finally {
      setBusy(false);
    }
  };
  if (seat.rules) {
    return (
      <div className="night-proposal plaque-wrap" role="alertdialog" aria-label="The rules ended the game" data-testid="night-rules-result">
        <div className="plaque night-proposal-body">
          <p>The rules ended the game: <b>{what}</b>.</p>
          <p className="night-proposal-wait">{seat.rules}.</p>
          <p className="night-proposal-wait">
            {local ? "Confirm to record the result." : waiting.length ? `Waiting for ${waiting.map(nameOf).join(", ")} to confirm.` : "Everyone confirmed."}
            {!local && " Everyone in the game when it ended confirms; undo takes it back."}
          </p>
          {mustAnswer && (
            <div className="night-actions">
              <button className="tt-btn" disabled={busy} data-testid="rules-result-later" onClick={() => void answer(false)}
                title="Leave it to the table: undo the last action, or record the result by hand with End game">Not yet</button>
              <button className="tt-btn brass" data-testid="rules-result-confirm" disabled={busy} onClick={() => void answer(true)}
                title="Record this result; the result and the rematch vote follow">Confirm result</button>
            </div>
          )}
        </div>
      </div>
    );
  }
  return (
    <div className="night-proposal plaque-wrap" role="alertdialog" aria-label="Proposal to end the game" data-testid="night-proposal">
      <div className="plaque night-proposal-body">
        <p><b>{p.by_name}</b> proposes ending the game: <b>{what}</b>.</p>
        <p className="night-proposal-wait">
          {waiting.length ? `Waiting for ${waiting.map(nameOf).join(", ")}.` : "Everyone agreed."} Every player still in the game must agree.
        </p>
        <div className="night-actions">
          {mustAnswer ? (
            <>
              <button className="tt-btn" disabled={busy} onClick={() => void answer(false)}>{local ? `${nameOf(me)} declines` : "Decline"}</button>
              <button className="tt-btn brass" data-testid="proposal-agree" disabled={busy} onClick={() => void answer(true)}>{local ? `${nameOf(me)} agrees` : "Agree"}</button>
            </>
          ) : seat.canWithdraw ? (
            <button className="tt-btn" disabled={busy} onClick={() => void answer(false)}>Withdraw</button>
          ) : null}
        </div>
      </div>
    </div>
  );
}

// --------------------------------------------------------------------------- result + rematch vote

function ResultScene({ view, night }: { view: GameView; night: NightInfo }) {
  const actingAs = useGame((s) => s.actingAs);
  const isHost = useIsHost();
  const result = night.result;
  const key = seenKey("result", view);
  const [spot, setSpot] = useState(false);
  const [busy, setBusy] = useState(false);
  const scale = useScale();
  const end = useRef(() => {
    markSeen(key);
    setSpot(false);
  });
  end.current = () => {
    markSeen(key);
    setSpot(false);
  };
  useEffect(() => {
    if (!result || seen(key) || !scenesOn()) return;
    setSpot(true);
    const winner = result.winners[0];
    if (winner) window.dispatchEvent(new CustomEvent("fyodor:camera", { detail: { id: "cam_focus_player", digit: 0, hover: null, player: winner } }));
    const t = window.setTimeout(() => end.current(), scale(2600));
    return () => window.clearTimeout(t);
  }, [result, key, scale]);
  useSkipKeys(spot, () => end.current());
  if (!result) return null;

  const me = perspective(view, actingAs);
  const seated = view.viewer !== SPECTATOR && view.seat_order.includes(me);
  const winners = result.winners;
  const won = seated && winners.includes(me);
  const kind = result.result_type === "draw" ? "draw" : result.result_type === "no_result" ? "none" : won ? "victory" : seated ? "defeat" : "winner";
  const word = { victory: "Victory", defeat: "Defeat", draw: "Draw", none: "No result", winner: `${result.winner_names.join(" & ")} ${winners.length > 1 ? "win" : "wins"}` }[kind];
  const winnerLine = result.winner_names.length ? `${result.winner_names.join(" & ")} ${winners.length > 1 ? "win" : "wins"}` : "";
  const commanderOf = (pid: string) => view.players.find((p) => p.id === pid)?.commanders.map((c) => c.name).join(" & ");
  const local = view.game.mode === "local";
  const voters = view.seat_order.filter((pid) => local || view.game.seats[pid]?.claimed);
  const myVote = night.votes[me];
  const nameOf = (pid: string) => view.players.find((x) => x.id === pid)?.name ?? pid;
  const vote = async (choice: "rematch" | "lobby", force = false) => {
    setBusy(true);
    try {
      await voteNext(view.game.id, choice, { as: local ? me : undefined, force });
    } catch (e) {
      toastError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      {spot && (
        <div className={`night-spot ${kind}`} data-testid="result-spotlight" onClick={() => end.current()} role="status" aria-live="polite">
          <div className="night-spot-inner">
            <div className="night-word">{word}</div>
            <div className="night-rule" aria-hidden />
            {kind !== "winner" && winnerLine && <div className="night-winner">{winnerLine}</div>}
            {winners.length === 1 && commanderOf(winners[0]!) && <div className="night-cmdr">{commanderOf(winners[0]!)}</div>}
            {result.agreed && <div className="night-agreed">Agreed by the players</div>}
          </div>
        </div>
      )}
      {!spot && (
        <div className="night-result plaque-wrap" data-testid="night-result">
          <div className="plaque night-result-body">
            <div className="night-result-head">
              <span className={`night-result-word ${kind}`}>{kind === "winner" ? "Game over" : word}</span>
              <span className="night-result-line">
                Game {night.number}{winnerLine ? ` · ${winnerLine}` : ""}{result.agreed ? " · agreed" : ""}
              </span>
            </div>
            {seated && (
              <div className="night-actions">
                {local ? (
                  <a className="tt-btn" href="#/play">Leave table</a>
                ) : (
                  <button className={`tt-btn ${myVote === "lobby" ? "on" : ""}`} disabled={busy} data-testid="vote-lobby" onClick={() => void vote("lobby")}>Return to lobby</button>
                )}
                <button className={`tt-btn brass ${myVote === "rematch" ? "on" : ""}`} disabled={busy || myVote === "rematch"} data-testid="vote-rematch" onClick={() => void vote("rematch")}>
                  {myVote === "rematch" ? "Rematch — waiting" : "Rematch — same decks"}
                </button>
              </div>
            )}
            {!local && (
              <ul className="night-votes" aria-label="Votes">
                {voters.map((pid) => (
                  <li key={pid}>
                    <span>{nameOf(pid)}</span>
                    <b className={night.votes[pid] ?? "waiting"}>{night.votes[pid] === "rematch" ? "Rematch" : night.votes[pid] === "lobby" ? "Lobby" : "Deciding…"}</b>
                  </li>
                ))}
              </ul>
            )}
            {view.game.predictions && <PredictionsRecap recap={view.game.predictions} />}
            {!local && isHost && voters.some((pid) => !night.votes[pid]) && (
              <button className="tt-btn ghost night-force" disabled={busy} onClick={() => void vote("lobby", true)}>Everyone back to the lobby now</button>
            )}
          </div>
        </div>
      )}
    </>
  );
}
