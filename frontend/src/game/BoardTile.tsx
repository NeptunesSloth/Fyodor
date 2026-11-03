/**
 * A permanent on the arranged 2D board, as MTG Arena draws one: the art large, the name on a bar across the top, the
 * power and toughness on a parchment plate. The full card is a hover away (the card preview). A card without cached art
 * shows the redesigned proxy's art window (its colours and its type's icon), so the two read as the same card.
 */
import { memo, useMemo, useState } from "react";
import { GLYPHS, PALETTE, proxyColours, proxyFace } from "../cards/proxy";
import { imageUrl } from "../services/cards";
import { useCard } from "../state/cardCache";
import { isVisible, type CardStats, type GameCard } from "../types/game";
import { sleeveStyle, useSleeve } from "./appearance";
import { GameCardFace } from "./GameCardFace";
import { Icon } from "../components/Icon";

export const BoardTile = memo(function BoardTile({ card, stats }: { card: GameCard; stats?: CardStats | undefined }) {
  const visible = isVisible(card);
  const data = useCard(visible && !card.face_down ? card.card_id : null);
  const sleeve = sleeveStyle(useSleeve(card.owner));
  const [failed, setFailed] = useState<string | null>(null);
  const custom = visible && !card.card_id && card.token
    ? { name: card.token.name, type_line: card.token.type_line, oracle_text: card.token.text, power: card.token.power, toughness: card.token.toughness, colors: card.token.colors }
    : undefined;
  const face = visible ? card.face ?? 0 : 0;
  // (a token's `custom` is a fresh object each render: key on what it says)
  const p = useMemo(() => (visible && !card.face_down ? proxyFace(data, face, custom, visible ? card.name : "") : null),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [visible, visible && card.face_down, data, face, custom?.name, custom?.type_line, custom?.power, custom?.toughness, custom?.colors?.join(""), visible ? card.name : ""]);
  const colours = useMemo(() => (p ? proxyColours(p) : null), [p]);

  if (!visible || card.face_down) {
    return (
      <div className="board-tile tile-back card-back" style={sleeve} aria-label="Face-down card">
        {visible && <span className="peek-badge" title="Face down — you know what it is">👁</span>}
      </div>
    );
  }
  if (card.ability) return <GameCardFace card={card} />;

  const imgFace = data?.double_faced ? Math.min(face, Math.max(0, data.image_faces - 1)) : 0;
  const src = data?.has_image ? imageUrl(data.id, imgFace, "normal") : null;
  const art = src && failed !== src ? src : null;
  const frame = p ? PALETTE[p.frame].frame : PALETTE.C.frame;
  const style = {
    "--tile-frame": frame,
    ...(colours && !art ? { "--tc-field": colours.field[0], "--tc-field2": colours.field[1], "--tc-glyph": colours.glyph, "--tc-glyph-lit": colours.glyphLit } : {}),
  } as React.CSSProperties;
  const name = p?.name || card.name;
  const pt = tilePT(stats, p?.stat?.kind === "pt" ? p.stat.text : null);

  return (
    <div className={`board-tile ${art ? "has-art" : "tile-proxy"} ${card.is_token ? "tile-token" : ""}`} style={style}>
      {art ? (
        <img className="tile-art" src={art} alt={card.name} draggable={false} loading="lazy" onError={() => setFailed(art)} />
      ) : (
        <div className="tile-field" aria-hidden>
          {p && (
            <svg className="tile-glyph" viewBox="0 0 24 24">
              <path className="tc-glyph-lit" d={GLYPHS[p.kind]} transform="translate(0 0.7)" />
              <path d={GLYPHS[p.kind]} />
            </svg>
          )}
        </div>
      )}
      <div className="tile-name" title={name}>
        {card.commander_key && <Icon name="crown" size={11} className="tile-crown" />}
        {card.is_token && !card.commander_key && <i className="tile-token-mark" aria-label="Token" title="Token" />}
        <span>{name}</span>
      </div>
      {pt && (
        <span className={`tile-pt${pt.trend}`} title={pt.title} {...(stats?.pt ? { "data-testid": "stat-badge" } : {})}>
          {pt.glyphs && <i>{pt.glyphs}</i>}
          {pt.text}
        </span>
      )}
    </div>
  );
});

const KEYWORD_GLYPH: Record<string, string> = {
  flying: "🪶", haste: "»", trample: "⇶", vigilance: "◉", lifelink: "♥", deathtouch: "☠", "first strike": "⚡",
  "double strike": "⚡⚡", menace: "⚔", reach: "↑", hexproof: "◈", indestructible: "⛨",
};

/** The P/T plate: the rules' current values when automation knows them (raised or lowered from the printed ones), else what's printed. */
export function tilePT(stats: CardStats | undefined, printed: string | null): { text: string; trend: string; title?: string; glyphs?: string } | null {
  if (stats?.pt) {
    const base = Number(stats.base?.[0] ?? NaN) + Number(stats.base?.[1] ?? NaN);
    const now = stats.pt[0] + stats.pt[1];
    const trend = Number.isNaN(base) || now === base ? "" : now > base ? " up" : " down";
    const title = [stats.gained?.length ? `Has: ${stats.gained.join(", ")}` : "", stats.lost?.length ? `Lost: ${stats.lost.join(", ")}` : ""].filter(Boolean).join("\n");
    const glyphs = stats.gained?.length ? stats.gained.map((k) => KEYWORD_GLYPH[k] ?? "✦").join("") : "";
    return { text: `${stats.pt[0]}/${stats.pt[1]}`, trend, ...(title ? { title } : {}), ...(glyphs ? { glyphs } : {}) };
  }
  return printed ? { text: printed, trend: "" } : null;
}
