import { useEffect, useState } from "react";
import { toastError } from "../components/Toasts";
import { api } from "../services/api";
import { seatToken } from "../services/games";
import { perspective, useGame } from "../state/gameStore";
import type { GameView } from "../types/game";
import { send } from "./actions";
import { useIsHost } from "./HostTools";
import { testEnding } from "./nightEnding";

/** -- test-table ending -- undo back to just before the action that ended the test for this seat (app/api/games.py, test/take-back). */
const takeBack = (gameId: string, as: string | null) => {
  const t = seatToken(gameId);
  return api.post<GameView>(`/games/${gameId}/test/take-back`, { as }, t ? { "X-Seat-Token": t } : {});
};

/**
 * -- test-table ending -- a test against target dummies has no pod result to confirm, so when it ends (you lost or conceded, every
 * dummy is out, or a draw) this seat gets its own plaque: what happened, and what to do next. Take it back undoes the action that
 * ended it; Start over deals a new game at the same table (same decks, settings and dummies, reshuffled); Keep looking closes the
 * plaque on the final board (it comes back with the next ending); Leave goes back to the Play page. The server decides it all.
 */
export function TestEnding() {
  const view = useGame((s) => s.view);
  const actingAs = useGame((s) => s.actingAs);
  const isHost = useIsHost();
  const [closed, setClosed] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const me = view ? perspective(view, actingAs) : "";
  const ending = view ? testEnding(view, me) : null;
  useEffect(() => {
    if (ending && closed && closed !== ending.key) setClosed(null); // (a new ending: show it)
  }, [ending, closed]);
  if (!view || !ending || closed === ending.key) return null;
  const local = view.game.mode === "local";
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
  const word = ending.kind === "lost" ? "defeat" : ending.kind === "won" ? "victory" : "draw";
  return (
    <div className="night-proposal test-ending plaque-wrap" role="alertdialog" aria-labelledby="test-ending-title" data-testid="test-ending">
      <div className="plaque night-proposal-body">
        <div className="night-result-head">
          <span id="test-ending-title" className={`night-result-word ${word}`}>{ending.title}</span>
          <span className="night-result-line">Test over · turn {view.turn.number}</span>
        </div>
        <p className="test-ending-line">{ending.line}</p>
        <div className="night-actions">
          <button className="tt-btn ghost" data-testid="test-ending-keep" onClick={() => setClosed(ending.key)}
            title="Close this to look at the final board; it comes back with the next ending">Keep looking</button>
          <a className="tt-btn ghost" href="#/play" data-testid="test-ending-leave">Leave</a>
          {isHost && (
            <button className="tt-btn" disabled={busy} data-testid="test-ending-restart"
              title="A new game at this table: the same decks, settings and dummies, every deck reshuffled"
              onClick={() => void run(() => send({ type: "restart_game", draw: 7, fresh: true }))}>Start over</button>
          )}
          <button className="tt-btn brass" disabled={busy} data-testid="test-ending-takeback"
            title="Undo back to just before the action that ended the test"
            onClick={() => void run(() => takeBack(view.game.id, local ? me : null))}>Take it back</button>
        </div>
      </div>
    </div>
  );
}
