import { memo, useEffect, useMemo, useState } from "react";
import { imageUrl } from "../services/cards";
import type { CardData, CardFaceData } from "../types/cards";
import { useImageRetry } from "./imageRetry";
import { ManaText } from "./ManaText";
import { textMeasure, proxyFontsReady, tinyNameSize, whenProxyFontsReady } from "./proxyMeasure";
import { GLYPHS, layoutProxy, proxyColours, proxyFace, stripReminders, TIERS, type ProxyFace } from "./proxy";

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
  const { failed, nonce, onError } = useImageRetry();
  if (faceDown) return <div className={`card-face card-back ${backStyle ? "sleeved" : ""} ${className ?? ""}`} style={backStyle} aria-label="Face-down card" />;
  if (!card && !custom) return <div className={`card-face card-loading ${className ?? ""}`} />;

  if (card) {
    const imgFace = card.double_faced ? Math.min(face, card.image_faces - 1) : 0;
    const src = imageUrl(card.id, imgFace, size);
    if (card.has_image && failed !== src) {
      return (
        <div className={`card-face ${className ?? ""}`}>
          <img key={nonce} src={src} alt={card.name} draggable={false} loading="lazy" onError={() => onError(src)} />
        </div>
      );
    }
  }
  return <TextCard card={card} custom={custom} face={face} className={className} />;
});

function TextCard({ card, custom, face, className }: { card?: CardData | undefined; custom?: CustomFace | undefined; face: number; className?: string | undefined }) {
  // (a token's `custom` is a fresh object on every render: key on what it says)
  const c = custom;
  const p = useMemo(() => proxyFace(card, face, c),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [card, face, c?.name, c?.type_line, c?.oracle_text, c?.power, c?.toughness, c?.colors?.join("")]);
  // laid out with estimated widths until the fonts load, then measured again
  const [fonts, setFonts] = useState(proxyFontsReady);
  useEffect(() => {
    if (fonts) return;
    let live = true;
    void whenProxyFontsReady().then(() => live && setFonts(true));
    return () => { live = false; };
  }, [fonts]);
  // eslint-disable-next-line react-hooks/exhaustive-deps -- `fonts` changes what textMeasure() returns
  const { style, full, small } = useMemo(() => proxyStyle(p), [p, fonts]);
  const text = full.text.reminders ? p.text : stripReminders(p.text);
  return (
    <div className={`card-face ${className ?? ""}`}>
      <div className={`text-card col-${p.frame.toLowerCase()} kind-${p.kind}${full.text.fits ? "" : " tc-crowded"}${small.text.fits ? "" : " tc-crowded-s"}${full.name.lines.length > 1 ? " tc-name2" : ""}`} style={style}>
        <div className="tc-head">
          {p.cost && (
            <span className="tc-cost">
              <ManaText text={p.cost} />
            </span>
          )}
          <span className="tc-name">{p.name}</span>
        </div>
        <div className="tc-art" aria-hidden>
          <svg className="tc-glyph" viewBox="0 0 24 24">
            <path className="tc-glyph-lit" d={GLYPHS[p.kind]} transform="translate(0 0.7)" />
            <path d={GLYPHS[p.kind]} />
          </svg>
        </div>
        <div className="tc-type">{p.type}</div>
        <div className="tc-text">
          {text.split("\n").filter((l) => l.trim()).map((line, i) => (
            <p key={i}>
              <RulesLine line={line} />
            </p>
          ))}
        </div>
        {p.stat && <div className={`tc-pt tc-${p.stat.kind}`}>{p.stat.text}</div>}
      </div>
    </div>
  );
}

/** One paragraph of rules text with its mana symbols; reminder text (in parentheses) is printed lighter. */
function RulesLine({ line }: { line: string }) {
  const parts = line.split(/(\([^()]*\))/);
  return (
    <>
      {parts.map((part, i) => (part ? (i % 2 ? <span key={i} className="tc-rem"><ManaText text={part} /></span> : <ManaText key={i} text={part} />) : null))}
    </>
  );
}

const styles = new Map<string, ReturnType<typeof layoutStyle>>();

/** The proxy's colours and fitted sizes, shared by every copy of the same card face (30 Islands lay out once). */
function proxyStyle(p: ProxyFace) {
  const key = [proxyFontsReady(), p.name, p.cost, p.type, p.text, p.stat?.text, p.frame, p.field.join(""), p.kind].join("\u0001");
  let hit = styles.get(key);
  if (!hit) {
    if (styles.size > 600) styles.clear();
    styles.set(key, (hit = layoutStyle(p)));
  }
  return hit;
}

/** The proxy's colours and its fitted sizes at the full and small levels of detail, as CSS variables (card units = cqw). */
function layoutStyle(p: ProxyFace) {
  const c = proxyColours(p);
  const measure = textMeasure();
  const full = layoutProxy(p, TIERS.full, measure);
  const small = layoutProxy(p, TIERS.small, measure);
  const style = {
    "--tc-frame": c.frame, "--tc-dark": c.dark, "--tc-bar": c.bar, "--tc-paper": c.paper,
    "--tc-field": c.field[0], "--tc-field2": c.field[1], "--tc-glyph": c.glyph, "--tc-glyph-lit": c.glyphLit,
    "--tc-ns": full.name.size, "--tc-ts": full.type.size, "--tc-fs": full.text.size, "--tc-tb": full.text.box,
    "--tc-ns-s": small.name.size, "--tc-ts-s": small.type.size, "--tc-fs-s": small.text.size, "--tc-tb-s": small.text.box,
    "--tc-ns-t": tinyNameSize(p.name, measure),
  } as React.CSSProperties;
  return { style, full, small };
}
