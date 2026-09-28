import { memo } from "react";
import { CardFace } from "../cards/CardFace";
import { useCard } from "../state/cardCache";
import { isVisible, type GameCard } from "../types/game";

/** Draws any game object: hidden card back, face-down card, ability, custom token or real card. */
export const GameCardFace = memo(function GameCardFace({ card, size = "normal", peek = false }: { card: GameCard; size?: "small" | "normal" | "large"; peek?: boolean }) {
  const visible = isVisible(card);
  const data = useCard(visible ? card.card_id : null);
  if (!visible) return <CardFace faceDown />;
  if (card.face_down && !peek) {
    return (
      <div className="face-down-known">
        <CardFace faceDown />
        <span className="peek-badge" title="Face down — you know what it is">👁</span>
      </div>
    );
  }
  if (card.ability) {
    return (
      <div className="card-face ability-card">
        <div className="ability-inner">
          <div className="ability-kind">{card.ability.kind === "other" ? "ability" : `${card.ability.kind} ability`}</div>
          {card.ability.source_name && <div className="ability-source">{card.ability.source_name}</div>}
          <div className="ability-text">{card.ability.text}</div>
        </div>
      </div>
    );
  }
  if (!card.card_id && card.token) {
    return (
      <CardFace
        size={size}
        custom={{
          name: card.token.name,
          type_line: card.token.type_line,
          oracle_text: card.token.text,
          power: card.token.power,
          toughness: card.token.toughness,
          colors: card.token.colors,
        }}
      />
    );
  }
  if (!card.card_id) return <CardFace custom={{ name: card.name, type_line: "Unknown card" }} />;
  return <CardFace card={data} face={card.face} size={size} />;
});

export function CounterBadges({ counters }: { counters?: Record<string, number> | undefined }) {
  if (!counters) return null;
  const entries = Object.entries(counters);
  if (!entries.length) return null;
  const plus = counters["+1/+1"] ?? 0;
  const minus = counters["-1/-1"] ?? 0;
  const net = plus - minus;
  return (
    <div className="counters">
      {(plus || minus) && (
        <span className={`counter pt ${net >= 0 ? "pos" : "neg"}`} title={`+1/+1: ${plus}, -1/-1: ${minus}`}>
          {net >= 0 ? `+${net}/+${net}` : `${net}/${net}`}
        </span>
      )}
      {entries
        .filter(([k]) => k !== "+1/+1" && k !== "-1/-1")
        .map(([k, v]) => (
          <span key={k} className={`counter kind-${k.replace(/[^a-z]/gi, "")}`} title={`${k} counters`}>
            {k === "loyalty" ? "◆" : k.slice(0, 8)} {v}
          </span>
        ))}
    </div>
  );
}
