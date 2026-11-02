/**
 * A die drawn flat (SVG): a shaded polyhedron as it looks from a little above, lit from the top left like the table,
 * in a seat colour with the ink that reads best on it. The roll panel's buttons, the toy tray's picker and the 2D
 * table's drawn dice (no WebGL) use it, so every die in the app has the same face.
 */
import type { CSSProperties } from "react";

export type GlyphKind = "d4" | "d6" | "d8" | "d10" | "d12" | "d20" | "d100" | "coin";

type RGB = [number, number, number];
const hex = (h: string): RGB => {
  const m = /^#?([0-9a-f]{6})$/i.exec(h.trim());
  const n = m ? parseInt(m[1]!, 16) : 0xd4a852;
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
};
const css = ([r, g, b]: RGB) => `rgb(${Math.round(r)}, ${Math.round(g)}, ${Math.round(b)})`;
function toHsl([r, g, b]: RGB): [number, number, number] {
  r /= 255; g /= 255; b /= 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  const l = (max + min) / 2;
  if (max === min) return [0, 0, l];
  const d = max - min;
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
  const h = max === r ? (g - b) / d + (g < b ? 6 : 0) : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return [h / 6, s, l];
}
function fromHsl(h: number, s: number, l: number): RGB {
  const f = (n: number) => {
    const k = (n + h * 12) % 12;
    const a = s * Math.min(l, 1 - l);
    return 255 * (l - a * Math.max(-1, Math.min(k - 3, 9 - k, 1)));
  };
  return [f(0), f(8), f(4)];
}
const lum = (c: RGB) => {
  const ch = (v: number) => {
    v /= 255;
    return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * ch(c[0]) + 0.7152 * ch(c[1]) + 0.0722 * ch(c[2]);
};

/** The resin body of a seat colour (as the 3D dice: table3d/diceLook.ts bodyColor) and its ink. */
export function glyphColors(seat: string): { body: RGB; ink: string } {
  const [h, s] = toHsl(hex(seat));
  const body = fromHsl(h, Math.min(1, s * 1.1 + 0.12), 0.42);
  const l = lum(body);
  const ivory = 0.83, soot = 0.007;
  const ink = (Math.max(l, ivory) + 0.05) / (Math.min(l, ivory) + 0.05) >= (Math.max(l, soot) + 0.05) / (Math.min(l, soot) + 0.05) ? "#f4ecdc" : "#17120d";
  return { body, ink };
}

const shade = (c: RGB, k: number): string => css(k >= 1 ? [c[0] + (255 - c[0]) * (k - 1), c[1] + (255 - c[1]) * (k - 1), c[2] + (255 - c[2]) * (k - 1)] : [c[0] * k, c[1] * k, c[2] * k]);

const PIPS: Record<number, [number, number][]> = {
  1: [[0, 0]], 2: [[-1, 1], [1, -1]], 3: [[-1, 1], [0, 0], [1, -1]], 4: [[-1, 1], [1, 1], [-1, -1], [1, -1]],
  5: [[-1, 1], [1, 1], [0, 0], [-1, -1], [1, -1]], 6: [[-1, 1], [1, 1], [-1, 0], [1, 0], [-1, -1], [1, -1]],
};

/** Facets per die: [points, brightness]; the front face last (it carries the number), with where the number sits. */
const FACETS: Record<Exclude<GlyphKind, "coin">, { facets: [string, number][]; text: [number, number, number] }> = {
  d4: { facets: [["50,8 8,86 50,70", 1.18], ["50,8 92,86 50,70", 0.72], ["8,86 92,86 50,70", 0.55], ["50,22 22,78 78,78", 1]], text: [50, 62, 30] },
  d6: { facets: [["14,26 30,12 92,12 76,26", 1.25], ["76,26 92,12 92,74 76,88", 0.66], ["14,26 76,26 76,88 14,88", 1]], text: [45, 57, 40] },
  d8: { facets: [["50,4 6,50 50,96", 1.16], ["50,4 94,50 50,96", 0.7], ["50,10 14,50 50,60 86,50", 1.32], ["14,50 50,60 86,50 50,92", 0.86], ["50,14 18,54 82,54", 1]], text: [50, 43, 30] },
  d10: { facets: [["50,4 6,46 16,62 50,96", 1.15], ["50,4 94,46 84,62 50,96", 0.68], ["16,62 50,96 84,62 50,72", 0.6], ["50,4 18,48 50,70 82,48", 1]], text: [50, 49, 26] },
  d12: { facets: [["50,4 92,32 78,86 22,86 8,32", 0.7], ["50,4 8,32 26,40 50,22", 1.25], ["50,4 92,32 74,40 50,22", 1.05], ["8,32 22,86 32,74 26,40", 1.1], ["92,32 78,86 68,74 74,40", 0.6], ["22,86 78,86 68,74 32,74", 0.75], ["50,22 74,40 68,74 32,74 26,40", 1]], text: [50, 52, 30] },
  d20: { facets: [["50,3 92,27 92,73 50,97 8,73 8,27", 0.72], ["50,3 8,27 22,62", 1.22], ["50,3 92,27 78,62", 0.9], ["8,27 8,73 22,62", 1.08], ["92,27 92,73 78,62", 0.58], ["8,73 50,97 22,62", 0.85], ["92,73 50,97 78,62", 0.55], ["22,62 78,62 50,97", 0.7], ["50,3 22,62 78,62", 1]], text: [50, 47, 30] },
  d100: { facets: [["50,4 6,46 16,62 50,96", 1.15], ["50,4 94,46 84,62 50,96", 0.68], ["16,62 50,96 84,62 50,72", 0.6], ["50,4 18,48 50,70 82,48", 1]], text: [50, 49, 25] },
};

export function DieGlyph({ kind, value, color = "#d4a852", className, style, title }: {
  kind: GlyphKind;
  /** The number on the front face ("H"/"T" on a coin); none: blank. */
  value?: string;
  color?: string;
  className?: string;
  style?: CSSProperties;
  title?: string;
}) {
  const { body, ink } = glyphColors(color);
  const under = value === "6" || value === "9";
  if (kind === "coin") {
    const brass: RGB = [201, 163, 92];
    return (
      <svg className={`die-glyph ${className ?? ""}`} viewBox="0 0 100 100" style={style} role={title ? "img" : undefined} aria-label={title} aria-hidden={title ? undefined : true}>
        <ellipse cx="50" cy="56" rx="44" ry="40" fill={shade(brass, 0.45)} />
        <ellipse cx="50" cy="50" rx="44" ry="40" fill={shade(brass, 1.12)} />
        <ellipse cx="50" cy="50" rx="36" ry="32" fill={css(body)} stroke={shade(brass, 0.7)} strokeWidth="2.5" />
        {value && <text className="die-glyph-n" x="50" y="51" textAnchor="middle" dominantBaseline="central" fontSize="34" style={{ fill: shade(brass, 1.3) }}>{value}</text>}
      </svg>
    );
  }
  const f = FACETS[kind];
  const pips = kind === "d6" && value && /^[1-6]$/.test(value) ? PIPS[Number(value)]! : null;
  const [tx, ty, size] = f.text;
  const small = value && value.length > 2 ? 0.7 : value && value.length > 1 ? 0.84 : 1;
  return (
    <svg className={`die-glyph ${className ?? ""}`} viewBox="0 0 100 100" style={{ ["--glyph-ink" as string]: ink, ...style }} role={title ? "img" : undefined} aria-label={title} aria-hidden={title ? undefined : true}>
      {f.facets.map(([pts, k], i) => <polygon key={i} points={pts} fill={shade(body, k)} stroke={shade(body, 0.45)} strokeWidth="1.2" strokeLinejoin="round" />)}
      {pips ? (
        <g aria-hidden>
          {pips.map(([px, py], i) => <circle key={i} cx={tx + px * 17} cy={ty - py * 17} r={value === "1" ? 8 : 6} fill={ink} />)}
          <text className="die-glyph-n" x={tx} y={ty} opacity="0" fontSize="1">{value}</text>
        </g>
      ) : value && (
        <text className="die-glyph-n" x={tx} y={ty} textAnchor="middle" dominantBaseline="central" fontSize={size * small}>
          {value}
        </text>
      )}
      {value && under && !pips && <rect x={tx - size * 0.22} y={ty + size * 0.42} width={size * 0.44} height={Math.max(2, size * 0.07)} fill={ink} />}
    </svg>
  );
}

/** The glyph for a roll of `sides` (a coin flip: the coin). */
export const glyphKind = (sides: number, coin: boolean): GlyphKind =>
  coin || sides === 2 ? "coin" : sides === 100 ? "d100" : ([4, 6, 8, 10, 12, 20].includes(sides) ? `d${sides}` : "d20") as GlyphKind;
