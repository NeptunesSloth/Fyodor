import type { CardData } from "../types/cards";
import { CardFace } from "./CardFace";
import { ManaText, OracleText } from "./ManaText";

/** Large inspection view: image plus the full rules text of every face. */
export function CardDetails({ card, face = 0, extra }: { card: CardData; face?: number; extra?: React.ReactNode }) {
  const faces = card.faces.length ? card.faces : [card];
  return (
    <div className="card-details">
      <CardFace card={card} face={face} size="large" className="details-image" />
      <div className="details-text">
        {faces.map((f, i) => (
          <section key={i} className={i === face && card.double_faced ? "active-face" : undefined}>
            <h3>
              {f.name} <span className="cost"><ManaText text={f.mana_cost} /></span>
            </h3>
            <div className="type">{f.type_line}</div>
            <div className="oracle"><OracleText text={f.oracle_text} /></div>
            {f.power != null && <div className="pt">{f.power}/{f.toughness}</div>}
            {f.loyalty != null && <div className="pt">Loyalty {f.loyalty}</div>}
            {f.defense != null && <div className="pt">Defense {f.defense}</div>}
          </section>
        ))}
        <div className="meta">
          {card.set_name} ({card.set_code.toUpperCase()}) #{card.collector_number}
          {card.artist ? ` · ${card.artist}` : ""}
        </div>
        {extra}
      </div>
    </div>
  );
}
