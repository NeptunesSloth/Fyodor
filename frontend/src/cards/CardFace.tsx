import { memo, useState } from "react";
import { imageUrl } from "../services/cards";
import type { CardData, CardFaceData } from "../types/cards";
import { ManaText } from "./ManaText";

export interface CustomFace {
  name: string;
  type_line?: string | null;
  oracle_text?: string | null;
  power?: string | null;
  toughness?: string | null;
  colors?: string[] | null;
}

interface Props {
  card?: CardData | undefined;
  /** Used for custom tokens / abilities with no database entry. */
  custom?: CustomFace | undefined;
  face?: number;
  faceDown?: boolean;
  /** Custom sleeve image for a face-down card. */
  backStyle?: React.CSSProperties;
  size?: "small" | "normal" | "large";
  className?: string;
}

/** Which face data to display for a given face index. */
export function faceData(card: CardData, face: number): CardFaceData | null {
  if (!card.faces.length) return null;
  return card.faces[Math.min(face, card.faces.length - 1)] ?? null;
}

export function colorClass(colors: string[] | null | undefined): string {
  if (!colors || colors.length === 0) return "col-c";
  if (colors.length > 1) return "col-m";
  return `col-${colors[0]!.toLowerCase()}`;
}

/** A single card picture: the cached scan when available, otherwise a readable text card. */
export const CardFace = memo(function CardFace({ card, custom, face = 0, faceDown, backStyle, size = "normal", className }: Props) {
  const [failed, setFailed] = useState<string | null>(null);
  if (faceDown) return <div className={`card-face card-back ${backStyle ? "sleeved" : ""} ${className ?? ""}`} style={backStyle} aria-label="Face-down card" />;
  if (!card && !custom) return <div className={`card-face card-loading ${className ?? ""}`} />;

  if (card) {
    const imgFace = card.double_faced ? Math.min(face, card.image_faces - 1) : 0;
    const src = imageUrl(card.id, imgFace, size);
    if (card.has_image && failed !== src) {
      return (
        <div className={`card-face ${className ?? ""}`}>
          <img src={src} alt={card.name} draggable={false} loading="lazy" onError={() => setFailed(src)} />
        </div>
      );
    }
  }
  return <TextCard card={card} custom={custom} face={face} className={className} />;
});

function TextCard({ card, custom, face, className }: { card?: CardData | undefined; custom?: CustomFace | undefined; face: number; className?: string | undefined }) {
  const f = card ? (card.double_faced ? faceData(card, face) : null) : null;
  const name = f?.name ?? card?.name ?? custom?.name ?? "";
  const mana = f ? f.mana_cost : card?.mana_cost;
  const type = f?.type_line ?? card?.type_line ?? custom?.type_line;
  const text = f?.oracle_text ?? card?.oracle_text ?? custom?.oracle_text;
  const power = f?.power ?? card?.power ?? custom?.power;
  const toughness = f?.toughness ?? card?.toughness ?? custom?.toughness;
  const loyalty = f?.loyalty ?? card?.loyalty;
  const colors = f?.colors ?? card?.colors ?? custom?.colors;
  return (
    <div className={`card-face ${className ?? ""}`}>
      <div className={`text-card ${colorClass(colors)}`}>
      <div className="tc-head">
        <span className="tc-name">{name}</span>
        <span className="tc-cost">
          <ManaText text={mana} />
        </span>
      </div>
      <div className="tc-art" />
      <div className="tc-type">{type}</div>
      <div className="tc-text">
        {(text ?? "").split("\n").map((line, i) => (
          <p key={i}>
            <ManaText text={line} />
          </p>
        ))}
      </div>
      {(power != null || loyalty != null) && (
        <div className="tc-pt">{power != null ? `${power}/${toughness}` : loyalty}</div>
      )}
      </div>
    </div>
  );
}
