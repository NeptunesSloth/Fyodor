import { useState } from "react";
import { toast } from "../components/Toasts";
import { perspective, useGame } from "../state/gameStore";
import { undoRequest, type UndoRequestOp } from "../services/undoRequest";
import type { GameView } from "../types/game";
import { undoRequestSeat } from "./undoPolicy";

/**
 * -- quick undo request -- "Bob asks to undo: cast Sol Ring — Approve / Decline" (TABLETOP_QOL_MILESTONE #7). A compact strip
 * under the top bar, never a modal: the players who answer see the buttons, the one who asked sees it waiting and can withdraw
 * it. The server decides everything (app/game/undo_requests.py) and performs the undo once everyone approved.
 */
export function UndoRequestBar() {
  const view = useGame((s) => s.view);
  const actingAs = useGame((s) => s.actingAs);
  if (!view) return null;
  return <UndoRequestStrip view={view} me={view.viewer === "__spectator__" ? null : perspective(view, actingAs)} />;
}

export function UndoRequestStrip({ view, me }: { view: GameView; me: string | null }) {
  const [busy, setBusy] = useState(false);
  const seat = undoRequestSeat(view, me);
  if (!seat) return null;
  const answer = async (op: UndoRequestOp) => {
    setBusy(true);
    try {
      await undoRequest(view.game.id, op);
    } catch (e) {
      toast(e instanceof Error ? e.message : String(e), "error");
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className={`resp-bar undo-req ${seat.mustAnswer ? "ask" : ""}`} role="status" data-testid="undo-request">
      <span className="resp-what"><b>{seat.title}</b></span>
      {seat.why && <span className="resp-status undo-req-why">{seat.why}</span>}
      <span className="resp-status">{seat.waiting.length ? `Waiting for ${seat.waiting.join(", ")}` : "Everyone approved"}</span>
      {seat.mustAnswer && (
        <>
          <button className="tt-btn" disabled={busy} data-testid="undo-decline" onClick={() => void answer("decline")}>Decline</button>
          <button className="tt-btn brass" disabled={busy} data-testid="undo-approve" onClick={() => void answer("approve")}>Approve</button>
        </>
      )}
      {seat.mine && (
        <button className="tt-btn ghost" disabled={busy} data-testid="undo-withdraw" onClick={() => void answer("withdraw")}>Withdraw</button>
      )}
    </div>
  );
}
