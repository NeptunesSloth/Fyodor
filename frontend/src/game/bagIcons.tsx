/**
 * The Bag of Extras' pictures (game/ExtrasBag.tsx), drawn as crisp SVG in one line weight: the counters as coloured chips
 * (each kind its own colour and glyph, as the counter chips by a Tabletop Simulator Commander table), the dice as clean
 * outlines with their number, the bag itself in the player's seat colour. Colour is never the only cue: every chip has its
 * glyph and its name under it.
 */
import type { CSSProperties } from "react";
import type { BAG_DICE } from "./bags";
import { GLYPH_BOX, SEAT_GLYPH_PATHS } from "./seatGlyphs";

/** A spiral, round and round (stun). */
function spiral(): string {
  let d = "";
  for (let i = 0; i <= 72; i++) {
    const a = (i / 72) * Math.PI * 3.1 + Math.PI;
    const r = 3 + (i / 72) * 19;
    d += `${i ? "L" : "M"}${(50 + r * Math.cos(a)).toFixed(2)} ${(50 + r * Math.sin(a)).toFixed(2)} `;
  }
  return d.trim();
}

export type CounterKind = "+1/+1" | "-1/-1" | "loyalty" | "charge" | "shield" | "stun" | "energy" | "experience";

/** Each counter's chip: its colour, the ink of its glyph, and the glyph (100-unit box, stroked). */
export const COUNTER_CHIPS: Record<CounterKind, { fill: string; ink: string; d: string }> = {
  "+1/+1": { fill: "#2f8a46", ink: "#f4fbf5", d: "M50 30 V70 M30 50 H70" },
  "-1/-1": { fill: "#8a2626", ink: "#fbf1f1", d: "M30 50 H70" },
  loyalty: { fill: "#d7d9de", ink: "#1b1d22", d: "M32 50 L50 32 L68 50 M32 68 L50 50 L68 68" },
  charge: { fill: "#e3b42a", ink: "#1f1700", d: "M54 24 L36 54 H52 L46 76 L66 44 H50 Z" },
  shield: { fill: "#2c6fcf", ink: "#f2f7ff", d: "M50 25 L70 32 V50 C70 63 61 71 50 76 C39 71 30 63 30 50 V32 Z" },
  stun: { fill: "#7446c4", ink: "#f6f1ff", d: spiral() },
  energy: { fill: "#e0702a", ink: "#fff6ef", d: "M50 26 L70 50 L50 74 L30 50 Z M50 40 L58 50 L50 60 L42 50 Z" },
  experience: { fill: "#c2427f", ink: "#fff3f9", d: "M50 26 L57 43 L75 44 L61 56 L66 74 L50 64 L34 74 L39 56 L25 44 L43 43 Z" },
};

/** The glyphs drawn as lines; the others are solid shapes. */
const LINED = new Set<CounterKind>(["+1/+1", "-1/-1", "loyalty", "stun"]);

/** A counter as a chip: the coloured disc with its notched rim and the glyph in its middle. */
export function CounterChipIcon({ kind }: { kind: CounterKind }) {
  const c = COUNTER_CHIPS[kind];
  return (
    <span className="chip-disc" style={{ "--chip": c.fill, "--chip-ink": c.ink } as CSSProperties} aria-hidden>
      <svg viewBox="0 0 100 100">
        <path d={c.d} fill={LINED.has(kind) ? "none" : "currentColor"} fillRule="evenodd" stroke="currentColor"
          strokeWidth={LINED.has(kind) ? (kind === "stun" ? 7 : 9) : 2} strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </span>
  );
}

/** Each die's outline seen face on (100-unit box), its inner facet lines, and where its number sits. */
const DICE: Record<(typeof BAG_DICE)[number], { outline: string; facets?: string; y: number; size: number }> = {
  4: { outline: "M50 12 L88 82 H12 Z", y: 63, size: 26 },
  6: { outline: "M20 20 H80 V80 H20 Z", y: 52, size: 32 },
  8: { outline: "M50 8 L88 50 L50 92 L12 50 Z", facets: "M12 50 H88", y: 39, size: 22 },
  10: { outline: "M50 8 L90 44 L50 92 L10 44 Z", facets: "M10 44 L50 60 L90 44 M50 60 V92", y: 42, size: 20 },
  12: { outline: "M50 8 L90 37 L75 85 H25 L10 37 Z", facets: "M50 26 L71 41 L63 66 H37 L29 41 Z M50 8 V26 M90 37 L71 41 M75 85 L63 66 M25 85 L37 66 M10 37 L29 41", y: 50, size: 19 },
  20: { outline: "M50 6 L88 28 V72 L50 94 L12 72 V28 Z", facets: "M50 22 L76 66 H24 Z M50 6 V22 M88 28 L50 22 L12 28 M88 72 L76 66 M12 72 L24 66 M50 94 L76 66 M50 94 L24 66", y: 52, size: 18 },
};

export function DieIcon({ sides }: { sides: (typeof BAG_DICE)[number] }) {
  const d = DICE[sides];
  return (
    <svg className="die-icon" viewBox="0 0 100 100" aria-hidden>
      <path className="die-body" d={d.outline} />
      {d.facets && <path className="die-facets" d={d.facets} />}
      <text x="50" y={d.y} textAnchor="middle" dominantBaseline="central" fontSize={d.size}>{sides}</text>
    </svg>
  );
}

/** The bag (the seat button's glyph), filled with the current colour. */
export function BagGlyph() {
  return (
    <svg className="extras-mark" viewBox={`0 0 ${GLYPH_BOX} ${GLYPH_BOX}`} aria-hidden>
      <path d={SEAT_GLYPH_PATHS.extras.d} fill="currentColor" />
    </svg>
  );
}

export function SearchGlyph() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden className="bag-find-glyph">
      <circle cx="10.5" cy="10.5" r="6" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <path d="M15 15 L20 20" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

export function CloseGlyph() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden>
      <path d="M7 7 L17 17 M17 7 L7 17" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}
