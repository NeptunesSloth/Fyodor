import { memo, useMemo } from "react";
import { createPortal } from "react-dom";
import { playerName, useGame } from "../state/gameStore";
import type { GameView } from "../types/game";
import { GameCardFace } from "./GameCardFace";
import { exileCastables, playFromExile, type ExileCastable } from "./exileCastables";
import "./exile.css";
import { useHoverCard } from "./hoverCard";

/**
 * CASTABLE FROM EXILE: a small row by your hand (both tables) with every exiled card you may cast or play right now, each saying
 * whose it is and, when a card's link allows it, which card exiled it ("Exiled with Ian Malcolm"). One click casts it. Only your own
 * hints feed it, so it shows nothing anyone else may not know.
 */
export function ExileCastables({ me }: { me: string }) {
  const view = useGame((s) => s.view);
  // over the page, not inside the table: the 3D table's container would otherwise become what "fixed" positions against
  return view ? createPortal(<ExileCastablesRow view={view} me={me} />, document.body) : null;
}

export function ExileCastablesRow({ view, me }: { view: GameView; me: string }) {
  const list = useMemo(() => exileCastables(view), [view]);
  if (!list.length) return null;
  return (
    <section className="exile-castables plaque-wrap" data-testid="exile-castables" aria-label="Castable from exile">
      <div className="plaque exile-castables-body">
        <span className="exile-castables-title">From exile</span>
        <div className="exile-castables-cards">
          {list.map((c) => <Castable key={c.id} c={c} card={view.cards[c.id]} owner={c.owner === me ? "yours" : playerName(view, c.owner)} />)}
        </div>
      </div>
    </section>
  );
}

const Castable = memo(function Castable({ c, card, owner }: { c: ExileCastable; card: GameView["cards"][string] | undefined; owner: string }) {
  const hover = useHoverCard();
  if (!card) return null;
  const name = "name" in card ? card.name : "card";
  const what = c.source ? `Exiled with ${c.source}` : "In exile";
  return (
    <button type="button" className="exile-castable rules-playable" data-testid="exile-castable" data-card-id={c.id}
      title={`${c.play ? "Play" : "Cast"} ${name} (${owner}'s) · ${what}`}
      onClick={() => void playFromExile(c)}
      {...hover(c.id)}>
      <span className="exile-castable-face"><GameCardFace card={card} /></span>
      <span className="exile-castable-line">
        <span className="exile-castable-what"><b>{c.play ? "Play" : "Cast"}</b> · {owner}</span>
        {c.source && <i className="exile-castable-source">with {c.source.split(",")[0]}</i>}
      </span>
    </button>
  );
});
