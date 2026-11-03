import { useEffect, useState } from "react";
import { Modal } from "../components/Modal";
import { useGame } from "../state/gameStore";
import { isVisible, type DigLog, type LogEntryView } from "../types/game";
import { moveCards, send } from "./actions";
import { GameCardFace } from "./GameCardFace";

/**
 * After "reveal until" or a cascade from the library menu (the scripted tables' chores, resolved on the server):
 * the cards that turned up, and where they go. Only their owner gets the choice; everyone else sees them in the
 * log and on top of the library (or in exile).
 */
export function DigDialog({ me }: { me: string }) {
  const [dig, setDig] = useState<DigLog | null>(null);
  useEffect(() => {
    const keyOf = (e: LogEntryView) => `${e.seq}:${e.ts}`;
    const seen = new Set((useGame.getState().view?.log ?? []).filter((e) => e.dig).map(keyOf));
    return useGame.subscribe((s, prev) => {
      const log = s.view?.log;
      if (!log || log === prev.view?.log) return;
      for (const e of log) {
        if (!e.dig || seen.has(keyOf(e))) continue;
        seen.add(keyOf(e));
        if (e.dig.player === me) setDig(e.dig);
      }
    });
  }, [me]);
  const cards = useGame((s) => s.view?.cards);
  if (!dig || !cards) return null;
  const where = dig.mode === "cascade" ? `${dig.player}:exile` : `${dig.player}:library`;
  // only the cards still where the reveal left them (anything already moved drops out)
  const here = dig.cards.filter((id) => cards[id]?.zone === where);
  const hit = dig.hit && here.includes(dig.hit) ? cards[dig.hit] : undefined;
  const rest = here.filter((id) => id !== dig.hit);
  const close = () => setDig(null);
  if (!hit && !rest.length) return null;
  const bottomRandom = async (ids: string[]) => {
    if (await moveCards(ids, "library", { player: dig.player, position: "bottom" })) await send({ type: "shuffle", player: dig.player, card_ids: ids });
  };
  return (
    <Modal title={dig.mode === "cascade" ? "Cascade" : "Revealed from your library"} onClose={close} wide>
      <div className="dig" data-testid="dig-dialog">
        {hit && isVisible(hit) && (
          <section className="dig-hit">
            <h3>{dig.mode === "cascade" ? "You may cast it without paying its mana cost" : "Found"}</h3>
            <div className="dig-row"><span className="dig-card"><GameCardFace card={hit} size="small" /></span></div>
            <div className="row">
              {dig.mode === "cascade" && <button className="btn primary" onClick={() => void moveCards([hit.id], "stack")}>Cast it (to the stack)</button>}
              <button className="btn" onClick={() => void moveCards([hit.id], "hand", { player: dig.player })}>Put into your hand</button>
              <button className="btn" onClick={() => void moveCards([hit.id], "battlefield", { player: dig.player })}>Put onto the battlefield</button>
              <button className="btn ghost" onClick={() => void moveCards([hit.id], "graveyard", { player: dig.player })}>Graveyard</button>
            </div>
          </section>
        )}
        {rest.length > 0 && (
          <section className="dig-rest">
            <h3>{dig.mode === "cascade" ? "The rest" : "The others"} ({rest.length})</h3>
            <div className="dig-row">
              {rest.map((id) => { const c = cards[id]; return c && isVisible(c) ? <span key={id} className="dig-card"><GameCardFace card={c} size="small" /></span> : null; })}
            </div>
            <div className="row">
              <button className={`btn ${dig.mode === "cascade" ? "primary" : ""}`} onClick={() => void bottomRandom(rest)} data-testid="dig-bottom">Bottom, in a random order</button>
              <button className="btn" onClick={() => void moveCards(rest, "graveyard", { player: dig.player })}>Graveyard</button>
              {dig.mode === "reveal_until" && <button className="btn" onClick={() => void send({ type: "shuffle", player: dig.player })}>Shuffle the library</button>}
            </div>
          </section>
        )}
        <p className="hint">Everyone saw these cards. {dig.mode === "reveal_until" ? "Cards you leave stay revealed on top of your library." : "Cards you leave stay in exile."}</p>
      </div>
    </Modal>
  );
}
