import { sleeveStyle, useSleeve } from "./appearance";
import { memo } from "react";
import { CardFace } from "../cards/CardFace";
import { useCard } from "../state/cardCache";
import { isVisible, type GameCard } from "../types/game";
import { counterName, counterShort } from "./counters";
import { addCounter } from "./actions";

/** Draws any game object: hidden card back, face-down card, ability, custom token or real card. */
export const GameCardFace = memo(function GameCardFace({ card, size = "normal", peek = false }: { card: GameCard; size?: "small" | "normal" | "large"; peek?: boolean }) {
  const visible = isVisible(card);
  const data = useCard(visible ? card.card_id : null);
  const sleeve = sleeveStyle(useSleeve(card.owner));
  if (!visible) return <CardFace faceDown backStyle={sleeve} />;
  if (card.face_down && !peek) {
    return (
      <div className="face-down-known">
        <CardFace faceDown backStyle={sleeve} />
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

/**
 * A card's counters. With `cardId` they are steppers, as on the Tabletop Simulator encoder: click adds one,
 * right-click takes one off (on the +N/+N chip: a +1/+1 counter, or a -1/-1 once none are left).
 */
export function CounterBadges({ counters, cardId }: { counters?: Record<string, number> | undefined; cardId?: string }) {
  if (!counters) return null;
  const entries = Object.entries(counters);
  if (!entries.length) return null;
  const plus = counters["+1/+1"] ?? 0;
  const minus = counters["-1/-1"] ?? 0;
  const net = plus - minus;
  const step = (kind: string, delta: number) => (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (cardId) void addCounter([cardId], kind, delta);
  };
  const ptStep = (e: React.MouseEvent, up: boolean) => {
    if (up) return step(minus ? "-1/-1" : "+1/+1", minus ? -1 : 1)(e);
    return step(plus ? "+1/+1" : "-1/-1", plus ? -1 : 1)(e);
  };
  const live = cardId ? { role: "button" as const, tabIndex: -1, onPointerDown: (e: React.PointerEvent) => e.stopPropagation() } : {};
  const hint = cardId ? " (click +1, right-click −1)" : "";
  return (
    <div className={`counters ${cardId ? "steppers" : ""}`}>
      {(plus || minus) && (
        <span className={`counter pt ${net >= 0 ? "pos" : "neg"}`} title={`+1/+1: ${plus}, -1/-1: ${minus}${hint}`} {...live}
          {...(cardId ? { onClick: (e: React.MouseEvent) => ptStep(e, true), onContextMenu: (e: React.MouseEvent) => ptStep(e, false) } : {})}>
          {net >= 0 ? `+${net}/+${net}` : `${net}/${net}`}
        </span>
      )}
      {entries
        .filter(([k]) => k !== "+1/+1" && k !== "-1/-1")
        .map(([k, v]) => (
          <span key={k} className={`counter kind-${k.replace(/[^a-z]/gi, "")}`} title={`${counterName(k, v)}${hint}`} {...live}
            {...(cardId ? { onClick: step(k, 1), onContextMenu: step(k, -1) } : {})}>
            {k === "loyalty" ? "◆" : counterShort(k)} {v}
          </span>
        ))}
    </div>
  );
}
