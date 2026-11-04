/**
 * The turn's brass phase dial (docs/research: no MTG app or physical aid has one): the five parts of a turn engraved
 * round a brass ring, a pip for every step (done ones inlaid brass, the current one an ember), and a needle that swings
 * to the current step. The turn's number sits in the hub in Roman numerals. Drawn in SVG, so it is crisp at any size;
 * purely a picture (the steps are read out by the dial's text beside it).
 */
import { PHASES, type PhaseName } from "../../types/game";

export const DIAL_GROUPS: { label: string; steps: PhaseName[] }[] = [
  { label: "Begin", steps: ["untap", "upkeep", "draw"] },
  { label: "Main", steps: ["main1"] },
  { label: "Combat", steps: ["begin_combat", "declare_attackers", "declare_blockers", "combat_damage", "end_combat"] },
  { label: "Main", steps: ["main2"] },
  { label: "End", steps: ["end", "cleanup"] },
];

const SWEEP = 270; // degrees the steps span (the gap at the bottom holds the turn's number)
const GAP = 1.1; // between groups, in steps
const R = 43; // the ring of pips
const C = 70; // the dial's centre (a 140 × 140 box)

/** Each step's angle (degrees clockwise from 12 o'clock) and each group's span. */
export function dialAngles(): { steps: Record<string, number>; groups: { label: string; from: number; to: number; mid: number }[] } {
  const units = DIAL_GROUPS.reduce((n, g) => n + g.steps.length, 0) - 1 + GAP * (DIAL_GROUPS.length - 1);
  const per = SWEEP / units;
  const steps: Record<string, number> = {};
  const groups: { label: string; from: number; to: number; mid: number }[] = [];
  let u = 0;
  for (const [i, g] of DIAL_GROUPS.entries()) {
    if (i) u += GAP;
    const first = u;
    for (const s of g.steps) {
      steps[s] = -SWEEP / 2 + u * per;
      u += 1;
    }
    const last = u - 1;
    const from = -SWEEP / 2 + (first - 0.42) * per;
    const to = -SWEEP / 2 + (last + 0.42) * per;
    groups.push({ label: g.label, from, to, mid: (from + to) / 2 });
  }
  return { steps, groups };
}

const pt = (deg: number, r: number): [number, number] => {
  const a = ((deg - 90) * Math.PI) / 180;
  return [C + r * Math.cos(a), C + r * Math.sin(a)];
};

function arc(from: number, to: number, r: number): string {
  const [x0, y0] = pt(from, r);
  const [x1, y1] = pt(to, r);
  return `M${x0.toFixed(2)} ${y0.toFixed(2)} A${r} ${r} 0 ${to - from > 180 ? 1 : 0} 1 ${x1.toFixed(2)} ${y1.toFixed(2)}`;
}

export function roman(n: number): string {
  if (n < 1 || n > 3999) return String(n);
  const table: [number, string][] = [[1000, "M"], [900, "CM"], [500, "D"], [400, "CD"], [100, "C"], [90, "XC"], [50, "L"], [40, "XL"], [10, "X"], [9, "IX"], [5, "V"], [4, "IV"], [1, "I"]];
  let out = "";
  for (const [v, s] of table) while (n >= v) { out += s; n -= v; }
  return out;
}

const { steps: ANGLE, groups: GROUPS } = dialAngles();

export function PhaseDial({ step, turn, color }: { step: PhaseName; turn: number; color?: string }) {
  const here = PHASES.indexOf(step);
  const angle = ANGLE[step] ?? 0;
  const group = DIAL_GROUPS.findIndex((g) => g.steps.includes(step));
  const num = roman(turn);
  return (
    <svg className="phase-dial" viewBox="0 0 140 140" aria-hidden style={{ ["--seat" as string]: color }}>
      <defs>
        <radialGradient id="pd-face" cx="38%" cy="32%" r="75%">
          <stop offset="0" stopColor="#3a2a1a" /><stop offset="0.7" stopColor="#1d140c" /><stop offset="1" stopColor="#120c07" />
        </radialGradient>
        <linearGradient id="pd-brass" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#f7e2a4" /><stop offset="0.45" stopColor="#c99a4a" /><stop offset="1" stopColor="#6e4c1c" />
        </linearGradient>
        <radialGradient id="pd-ember">
          <stop offset="0" stopColor="#fff3cf" /><stop offset="0.45" stopColor="#ffb648" /><stop offset="1" stopColor="#ff7a1a" stopOpacity="0" />
        </radialGradient>
        {GROUPS.map((g, i) => <path key={i} id={`pd-label-${i}`} d={arc(g.mid - 45, g.mid + 45, 54)} />)}
      </defs>
      {/* the bezel and the dark face */}
      <circle cx={C} cy={C} r={69} fill="url(#pd-brass)" />
      <circle cx={C} cy={C} r={65} fill="url(#pd-face)" stroke="rgba(0,0,0,0.7)" strokeWidth={2} />
      {/* the five parts: engraved arcs, the current one lit */}
      {GROUPS.map((g, i) => (
        <path key={i} d={arc(g.from, g.to, R)} className={`pd-arc ${i === group ? "here" : i < group ? "done" : ""}`} />
      ))}
      {/* the labels round the bezel (Cinzel capitals) */}
      {GROUPS.map((g, i) => (
        <text key={i} className={`pd-label ${i === group ? "here" : ""}`}>
          <textPath href={`#pd-label-${i}`} startOffset="50%" textAnchor="middle">{g.label.toUpperCase()}</textPath>
        </text>
      ))}
      {/* a pip per step */}
      {PHASES.map((ph, i) => {
        const [x, y] = pt(ANGLE[ph] ?? 0, R);
        return <circle key={ph} cx={x} cy={y} r={i === here ? 4.8 : 3} className={`pd-pip ${i === here ? "on" : i < here ? "done" : ""}`} />;
      })}
      {(() => { const [x, y] = pt(angle, R); return <circle cx={x} cy={y} r={11} fill="url(#pd-ember)" className="pd-glow" />; })()}
      {/* the needle and its hub, turned to the step */}
      <g className="pd-needle" style={{ transform: `rotate(${angle}deg)` }}>
        <path d={`M${C} ${C - 36} L${C + 3.2} ${C - 6} L${C} ${C + 9} L${C - 3.2} ${C - 6} Z`} fill="url(#pd-brass)" stroke="#3a2610" strokeWidth={0.8} />
      </g>
      <circle cx={C} cy={C} r={7} fill="url(#pd-brass)" stroke="#3a2610" strokeWidth={1} />
      <circle cx={C} cy={C} r={2.4} fill="var(--seat, #c9a35a)" />
      {/* the turn's number, in the gap at the bottom */}
      <text x={C} y={C + 31} className="pd-turn" textAnchor="middle" style={{ fontSize: num.length > 4 ? 11 : 15 }}>{num}</text>
    </svg>
  );
}
