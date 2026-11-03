import { useEffect, useRef, useState, type CSSProperties } from "react";
import { perspective, useGame } from "../state/gameStore";
import { usePrefs } from "../state/prefs";
import { hasWebgl } from "../table3d/renderer";
import type { DiceOverlay } from "../table3d/diceOverlay";
import { DICE_SHOWN, natural, rollLine, useDiceFeed, type DiceShow } from "./dice";
import { diceClack } from "./diceSound";
import { DieGlyph, glyphKind } from "./DieGlyph";
import { seededRandom } from "./seededRandom";
import "./dice.css";

/**
 * The 2D table's dice (game/dice.ts). Where WebGL works (and graphics aren't on low), the 3D table's own dice in a
 * transparent overlay (table3d/diceOverlay.ts, loaded with the first roll): the same throw every other screen sees,
 * landing on the roller's mat with real shadows, a chip over each die and the line saying what was rolled. Without
 * WebGL, drawn dice (game/DieGlyph.tsx) tumble in from the roller's edge, bounce and come to rest with their numbers
 * up. Either way they stay until the roller rolls again, someone clicks them away here, or the turn ends.
 */
export function DiceLayer() {
  const graphics = usePrefs((s) => s.graphics);
  const look = usePrefs((s) => s.diceLook);
  const [three] = useState(() => graphics !== "low" && hasWebgl());
  const failed = useRef(false);
  const overlay = useRef<DiceOverlay | null>(null);
  const loading = useRef<Promise<DiceOverlay | null> | null>(null);
  const [drawn, setDrawn] = useState<Drawn[]>([]);
  const turn = useGame((s) => s.view?.turn.number ?? 0);

  // the overlay lives as long as the table; it is built on the first roll
  useEffect(() => () => {
    overlay.current?.dispose();
    overlay.current = null;
    loading.current = null;
  }, []);
  useEffect(() => overlay.current?.setLook(look), [look]);
  // a new turn clears the table's dice
  const lastTurn = useRef(turn);
  useEffect(() => {
    if (turn === lastTurn.current) return;
    lastTurn.current = turn;
    overlay.current?.clear();
    setDrawn([]);
  }, [turn]);

  const ensure = (): Promise<DiceOverlay | null> => {
    loading.current ??= import("../table3d/diceOverlay").then((m) => {
      try {
        overlay.current = new m.DiceOverlay(graphics === "high" ? "high" : "medium", usePrefs.getState().diceLook);
        window.__fyodorDice2d = { positions: () => overlay.current?.positions() ?? [], state: () => overlay.current?.describe() ?? [] };
        return overlay.current;
      } catch {
        failed.current = true;
        return null;
      }
    }, () => {
      failed.current = true;
      return null;
    });
    return loading.current;
  };

  useDiceFeed((r) => {
    const view = useGame.getState().view;
    if (!view) return;
    const who = view.players.find((p) => p.id === r.actor);
    const me = perspective(view, useGame.getState().actingAs);
    const color = who?.color ?? "#d7ae63";
    const name = who?.name ?? "";
    const mat = () => {
      const el = document.querySelector(`[data-drop="${r.actor}:battlefield"]`) ?? document.querySelector(`[data-drop="${me}:battlefield"]`);
      const rect = el?.getBoundingClientRect();
      return rect && rect.width > 0 ? { rect, near: r.actor === me || !r.actor } : null;
    };
    const draw = () => setDrawn((all) => [...all.filter((d) => d.actor !== r.actor), drawnOf(r, color, name, mat())]);
    if (three && !failed.current) {
      void ensure().then((o) => (o ? o.throw(r, color, name, mat) : draw()));
      return;
    }
    draw();
  });

  if (!drawn.length) return null;
  return (
    <div className="dice-layer" data-testid="dice-layer">
      {drawn.map((d) => <DrawnThrow key={d.key} d={d} onClear={() => setDrawn((all) => all.filter((x) => x !== d))} />)}
    </div>
  );
}

declare global {
  interface Window {
    /** Test hook: the 2D table's 3D dice overlay, once a roll has built it. */
    __fyodorDice2d?: { positions: () => { x: number; y: number }[]; state: () => { key: string; dice: { label: string; ignored: boolean; resting: boolean }[] }[] };
  }
}

// -- without WebGL: drawn dice ----------------------------------------------------------------------------------------

interface DrawnDie { x: number; y: number; value: string; ignored: boolean; crit: "high" | "low" | null; spin: number; rest: number; delay: number }
interface Drawn extends DiceShow { color: string; name: string; dice: DrawnDie[]; fy: number; size: number; line: { x: number; y: number } }

/** Where each drawn die comes to rest on the mat (seeded by the roll, never two on top of each other). */
function drawnOf(r: DiceShow, color: string, name: string, spot: { rect: DOMRect; near: boolean } | null): Drawn {
  const rect = spot?.rect ?? new DOMRect(window.innerWidth / 2 - 200, window.innerHeight / 2 - 100, 400, 200);
  const near = spot?.near ?? true;
  const rnd = seededRandom(r.key);
  const size = Math.max(40, Math.min(58, rect.height / 4.2));
  const shown = r.results.slice(0, DICE_SHOWN);
  const cx = rect.left + rect.width / 2;
  const cy = rect.top + rect.height / 2 + (near ? -1 : 1) * rect.height * 0.06;
  const placed: { x: number; y: number }[] = [];
  const dice = shown.map((v, i) => {
    let x = cx, y = cy;
    for (let tries = 0; tries < 40; tries++) {
      x = cx + (rnd() - 0.5) * Math.min(rect.width * 0.5, size * (2.4 + shown.length * 0.9));
      y = cy + (rnd() - 0.5) * Math.min(rect.height * 0.5, size * 2.2);
      if (placed.every((p) => Math.hypot(p.x - x, p.y - y) > size * 1.15)) break;
    }
    placed.push({ x, y });
    return {
      x, y, value: r.coin ? (v ? "H" : "T") : String(v), ignored: !!r.ignored?.includes(i), crit: natural(r, i),
      spin: (1.5 + rnd() * 1.5) * (rnd() < 0.5 ? -1 : 1), rest: (rnd() - 0.5) * 24, delay: i * 45,
    };
  });
  const bottom = Math.max(...dice.map((d) => d.y)) + size * 0.7;
  const top = Math.min(...dice.map((d) => d.y)) - size * 0.7;
  return {
    ...r, color, name, dice, size,
    // thrown in from the roller's edge of the mat
    fy: near ? rect.bottom - cy + size : rect.top - cy - size,
    line: { x: cx, y: near ? bottom : top - 32 },
  };
}

function DrawnThrow({ d, onClear }: { d: Drawn; onClear: () => void }) {
  const prefs = usePrefs.getState();
  const ms = prefs.reducedMotion || document.body.classList.contains("reduced-motion") ? 0 : Math.round(1150 / (prefs.animationSpeed || 1));
  const [rested, setRested] = useState(ms === 0);
  // a clack as each bounce lands (the drawn dice have no physics: three hops, the last one soft)
  useEffect(() => {
    if (!ms) return;
    const timers = [0.45, 0.72, 0.82].map((k, i) => window.setTimeout(() => diceClack([5, 3, 1.4][i]!, "table", 0.5, d.coin), ms * k));
    timers.push(window.setTimeout(() => setRested(true), ms));
    return () => timers.forEach((t) => window.clearTimeout(t));
  }, [ms, d.coin]);
  const kind = glyphKind(d.sides, d.coin);
  const crits = d.dice.map((x) => x.crit);
  const crit = crits.includes("high") ? "high" : crits.includes("low") ? "low" : null;
  const line = rollLine(d.name, d);
  return (
    <div className="dice-throw2d" style={{ ["--seat" as string]: d.color }} data-testid="dice-throw">
      {d.dice.map((x, i) => (
        <div key={i} className={`dice2d${x.ignored ? " ignored" : ""}${x.crit ? ` crit-${x.crit}` : ""}`} data-testid="dice-die"
          title={x.ignored ? "Ignored: the rules ignore this roll" : undefined}
          style={{
            transform: `translate(${x.x}px, ${x.y}px)`, ["--d" as string]: `${d.size}px`, ["--t" as string]: `${ms}ms`,
            ["--fx" as string]: `${(d.dice[0]!.x - x.x) * 0.5}px`, ["--fy" as string]: `${d.fy + (d.dice[0]!.y - x.y)}px`,
            ["--bx" as string]: "0px", ["--by" as string]: `${d.fy * 0.35}px`,
            ["--spin" as string]: x.spin, ["--rest" as string]: `${x.rest}deg`, ["--delay" as string]: `${x.delay}ms`,
          } as CSSProperties}>
          <span className="dice2d-shadow" />
          <span className="dice2d-body"><DieGlyph kind={kind} value={x.value} color={d.color} title={x.ignored ? `${x.value}, ignored` : x.value} /></span>
        </div>
      ))}
      <button type="button" className={`dice-line dice-line2d${rested ? " on" : ""}${crit ? ` crit-${crit}` : ""}`} data-testid="dice-line" onClick={onClear}
        style={{ transform: `translate(${d.line.x}px, ${d.line.y}px) translate(-50%, 0)` }} title="Clear these dice (from this screen)" aria-label={`${line}. Clear these dice`}>
        <span className="dice-line-text">{line}</span>
        {crit && <span className="dice-line-tag">{crit === "high" ? "Natural 20" : "Natural 1"}</span>}
        <span className="dice-line-x" aria-hidden>×</span>
      </button>
    </div>
  );
}
