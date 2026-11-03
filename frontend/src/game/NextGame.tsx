import { useEffect, useState } from "react";
import { Modal } from "../components/Modal";
import { toast, toastError } from "../components/Toasts";
import { ApiError } from "../services/api";
import { listDecks } from "../services/decks";
import { myDecks, type LobbyDeckBody } from "../services/games";
import { clearNextDeck, getNextDeck, queueNextDeck, type QueuedDeck } from "../services/spectate";
import type { DeckSummary } from "../types/decks";
import { queueBody, queuedLabel } from "./spectate";

/**
 * NEXT GAME (docs/SPECTATOR_ACTIVITIES_MILESTONE.md §2): queue the deck you want for the next game while this one goes on.
 * Nothing about this game or the lobby changes now. When the pod returns to the lobby, the queued deck is proposed as your
 * deck (not ready: you confirm it or change it there); a same-decks rematch ignores it.
 */
export function NextGameDialog({ gameId, onClose }: { gameId: string; onClose: () => void }) {
  const [queued, setQueued] = useState<QueuedDeck | null | undefined>(undefined);
  const [hostDecks, setHostDecks] = useState<DeckSummary[] | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const saved = myDecks();

  useEffect(() => {
    getNextDeck(gameId).then((r) => setQueued(r.queued), (e) => {
      toastError(e);
      onClose();
    });
    // the host's deck library is offered on the host computer only (the server enforces this too)
    listDecks().then(setHostDecks, (e) => {
      if (!(e instanceof ApiError && e.status === 403)) toastError(e);
    });
  }, [gameId, onClose]);

  const queue = async (body: LobbyDeckBody) => {
    setBusy(true);
    try {
      const res = await queueNextDeck(gameId, body);
      setQueued(res.queued);
      toast(`Next game: ${queuedLabel(res.queued)}. It will be your deck when the pod returns to the lobby.`);
    } catch (e) {
      toastError(e);
    } finally {
      setBusy(false);
    }
  };
  const keep = async () => {
    setBusy(true);
    try {
      await clearNextDeck(gameId);
      setQueued(null);
    } catch (e) {
      toastError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal wide title="Next game" onClose={onClose} footer={
      <>
        <span className="hint">This game and the lobby don't change now. A rematch with the same decks keeps your current deck.</span>
        <span className="spacer" />
        <button className="tt-btn brass" onClick={onClose}>Done</button>
      </>
    }>
      <div className="next-game" data-testid="next-game">
        <div className="next-game-now">
          {queued === undefined ? <span className="hint">Loading…</span> : queued ? (
            <>
              <span className="next-game-tag">Next game</span>
              <b>{queuedLabel(queued)}</b>
              <span className="hint">{queued.card_count} cards · ready for the lobby</span>
              <span className="spacer" />
              <button className="tt-btn" disabled={busy} onClick={() => void keep()}>Keep current deck</button>
            </>
          ) : (
            <>
              <span className="next-game-tag">Next game</span>
              <b>Keep current deck</b>
              <span className="hint">or choose another below</span>
            </>
          )}
        </div>
        {hostDecks && hostDecks.length > 0 && (
          <section>
            <h4>Table decks</h4>
            <div className="deck-pick-list">
              {hostDecks.map((d) => (
                <button key={d.id} className="deck-pick" disabled={busy} onClick={() => void queue({ deck_id: d.id })}>
                  <b>{d.commanders.join(" & ") || d.name}</b><span className="hint">{d.name}</span>
                </button>
              ))}
            </div>
          </section>
        )}
        <section>
          <h4>My decks</h4>
          {saved.length ? (
            <div className="deck-pick-list">
              {saved.map((d) => {
                const body = queueBody(d);
                return (
                  <button key={d.id} className="deck-pick" disabled={busy || !body} onClick={() => body && void queue(body)}
                    title={body ? undefined : "Saved as an Archidekt link only: choose it in the lobby"}>
                    <b>{d.commanders.join(" & ") || d.name}</b><span className="hint">{d.name}</span>
                  </button>
                );
              })}
            </div>
          ) : <p className="hint">Decks you bring to tables (and Deck Lab copies) show up here.</p>}
        </section>
        <section>
          <h4>Paste a list</h4>
          <textarea className="deck-lab-text next-game-text" aria-label="Deck list" spellCheck={false} value={text} rows={6}
            placeholder={"Commander\n1 Muldrotha, the Gravetide\nDeck\n1 Sol Ring\n…"} onChange={(e) => setText(e.target.value)} />
          <button className="tt-btn" disabled={busy || !text.trim()} onClick={() => void queue({ text })}>Queue this list</button>
        </section>
      </div>
    </Modal>
  );
}
