import { useEffect, useState } from "react";
import { Modal } from "../components/Modal";
import { ResultForm, draftValid, type ResultDraft } from "../components/ResultForm";
import { toastError } from "../components/Toasts";
import { gameResult, RESULT_LABEL, recordResult, type GameResult } from "../services/pod";
import { useGame } from "../state/gameStore";
import "../pages/podstats.css";

/**
 * END GAME: the players decide when it's over and who won — nothing is detected automatically.
 * Two steps (choose, then confirm) so statistics never change by accident.
 */
export function EndGameDialog({ onClose }: { onClose: () => void }) {
  const view = useGame((s) => s.view);
  const [draft, setDraft] = useState<ResultDraft>({ result_type: "single", winners: [], notes: "" });
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [recorded, setRecorded] = useState<GameResult | null>(null);
  const gameId = view?.game.id;
  const resultId = view?.game.result_id;
  useEffect(() => {
    if (gameId && resultId) gameResult(gameId).then(setRecorded, toastError);
  }, [gameId, resultId]);
  if (!view) return null;
  const players = view.seat_order.map((pid) => ({ seat: pid, name: view.players.find((p) => p.id === pid)?.name ?? pid }));
  const name = (seat: string) => players.find((p) => p.seat === seat)?.name ?? seat;

  if (recorded) {
    return (
      <Modal title="Game result" onClose={onClose}>
        <div className="result-summary" data-testid="result-recorded">
          <p><b>Game #{recorded.number}</b> · {RESULT_LABEL[recorded.result_type]}</p>
          {recorded.winners.length > 0 && <p>Winner{recorded.winners.length > 1 ? "s" : ""}: <b>{recorded.winners.join(" + ")}</b></p>}
          {recorded.notes && <p className="hint">“{recorded.notes}”</p>}
          <p className="hint">Recorded. Corrections are made in <a href="#/stats">Pod stats</a> on the host computer.</p>
        </div>
      </Modal>
    );
  }

  const record = async () => {
    setBusy(true);
    try {
      setRecorded(await recordResult(view.game.id, draft));
    } catch (e) {
      toastError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal title="End game" onClose={onClose} footer={
      confirming ? (
        <>
          <button className="tt-btn" onClick={() => setConfirming(false)} disabled={busy}>Cancel</button>
          <span className="spacer" />
          <button className="tt-btn brass" data-testid="record-result" disabled={busy} onClick={() => void record()}>Record result</button>
        </>
      ) : (
        <>
          <button className="tt-btn" onClick={onClose}>Keep playing</button>
          <span className="spacer" />
          <button className="tt-btn brass" data-testid="confirm-result" disabled={!draftValid(draft)} onClick={() => setConfirming(true)}>Confirm result</button>
        </>
      )
    }>
      {confirming ? (
        <div className="result-summary" data-testid="result-confirm">
          <h3>Game result</h3>
          <p>{RESULT_LABEL[draft.result_type]}</p>
          {draft.winners.length > 0 && <p>Winner{draft.winners.length > 1 ? "s" : ""}: <b>{draft.winners.map(name).join(" + ")}</b></p>}
          <p className="hint">Players: {players.map((p) => p.name).join(", ")}</p>
          {draft.result_type === "no_result" && <p className="hint">This game won't count toward anyone's statistics.</p>}
          {draft.notes && <p className="hint">“{draft.notes}”</p>}
        </div>
      ) : (
        <ResultForm players={players} value={draft} onChange={setDraft} />
      )}
    </Modal>
  );
}
