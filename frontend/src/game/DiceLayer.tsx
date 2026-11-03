import { useEffect, useRef, useState, type CSSProperties } from "react";
import { perspective, useGame } from "../state/gameStore";
import { usePrefs } from "../state/prefs";
import { hasWebgl } from "../table3d/renderer";
import type { DiceOverlay } from "../table3d/diceOverlay";
import { CANNON_MS, fireTimes, tagLabel, volleyCount, volleys } from "./cannon";
import { DICE_SHOWN, diceClock, natural, rollLine, useDiceFeed, type DiceShow } from "./dice";
import { diceClack } from "./diceSound";
import { DieGlyph, glyphKind } from "./DieGlyph";
import { seededRandom } from "./seededRandom";
import "./dice.css";
import "./tabletoys.css";

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
  /** -- table toys -- the drawn dice cannon at the table's edge while it fires (game/cannon.ts). */
  const [cannon, setCannon] = useState<Cannon2D | null>(null);
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
    if (r.cannon) {
      fireCannon(r);
      return;
    }
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

  /**
   * -- table toys -- a dice cannon show: a little brass cannon at the table's right edge puffs each volley, and each die
   * lands on the mat of the player it was fired at (the overlay's 3D dice flying in from the cannon, or drawn dice), the
   * re-fires of a tie after the dice before them. Reduced motion: no cannon and no flight, just the dice at rest.
   */
  const fireCannon = (r: DiceShow) => {
    const view = useGame.getState().view;
    const vols = volleys(r);
    if (!view || !vols.length) return;
    const me = perspective(view, useGame.getState().actingAs);
    const prefs = usePrefs.getState();
    const reduced = prefs.reducedMotion || document.body.classList.contains("reduced-motion");
    const speed = Math.max(0.25, prefs.animationSpeed || 1);
    const first = r.cannon?.mode === "first";
    const who = (pid: string | null) => view.players.find((p) => p.id === pid);
    const colorOf = (pid: string) => (first ? who(pid)?.color : who(r.actor)?.color) ?? "#d7ae63";
    const matOf = (pid: string) => () => {
      const rect = document.querySelector(`[data-drop="${pid}:battlefield"]`)?.getBoundingClientRect();
      return rect && rect.width > 0 ? { rect, near: pid === me } : null;
    };
    const targets = new Set(vols.map((v) => v.player));
    // the cannon's muzzle: the right edge of the table, about level with the middle of the mats
    const mats = [...targets].map((pid) => matOf(pid)()?.rect).filter((x): x is DOMRect => !!x);
    const muzzle = { x: window.innerWidth - 46, y: mats.length ? mats.reduce((a, m) => a + m.top + m.height / 2, 0) / mats.length : window.innerHeight / 2, height: 60 };
    const show = (times: number[]) => {
      const gone = times[times.length - 1]! + CANNON_MS.linger;
      if (!reduced) setCannon({ key: r.key, y: muzzle.y, times: times.map((t) => t / speed), leave: gone / speed, at: times, gone });
    };
    const drawAll = () => {
      const ms = reduced ? 0 : 1150 / speed;
      const times = fireTimes(volleyCount(r), (_round, at) => at + ms * speed);
      setDrawn((all) => [...all.filter((d) => !targets.has(d.actor ?? "")),
        ...vols.map((v) => drawnOf(v.show, colorOf(v.player), who(v.player)?.name ?? "", matOf(v.player)(), { wait: reduced ? 0 : times[v.round]! / speed, tag: tagLabel(v.tag) }))]);
      show(times);
    };
    if (three && !failed.current) {
      void ensure().then((o) => {
        if (!o) return drawAll();
        for (const pid of targets) o.clear(pid);
        const times = fireTimes(volleyCount(r), (round, at) => {
          let landed = at;
          for (const v of vols.filter((x) => x.round === round)) {
            const { settles } = o.throw(v.show, colorOf(v.player), who(v.player)?.name ?? "", matOf(v.player), {
              cannonRound: round, muzzle: reduced ? null : muzzle,
              delay: reduced ? 0 : at, tag: tagLabel(v.tag), keep: true,
            });
            landed = Math.max(landed, settles);
          }
          return landed;
        });
        show(times);
      });
      return;
    }
    drawAll();
  };

  const toy = cannon && <CannonPuffs c={cannon} onDone={() => setCannon((c) => (c === cannon ? null : c))} />;
  if (!drawn.length) return toy || null;
  return (
    <div className="dice-layer" data-testid="dice-layer">
      {toy}
      {drawn.map((d) => <DrawnThrow key={d.key} d={d} onClear={() => setDrawn((all) => all.filter((x) => x !== d))} />)}
    </div>
  );
}

// -- table toys: the drawn dice cannon ----------------------------------------------------------------------------------

/** `times`, `leave`: real ms (the animation speed applied); `at`, `gone`: the same in show time (the dice's test clock). */
interface Cannon2D { key: string; y: number; times: number[]; leave: number; at: number[]; gone: number }

/**
 * A small brass cannon drawn at the table's right edge (2D table): it slides in, kicks and puffs smoke at each volley, and
 * slides away again. Times are real ms (the animation speed already applied). Off the mats, and gone when it's done.
 */
function CannonPuffs({ c, onDone }: { c: Cannon2D; onDone: () => void }) {
  const [live, setLive] = useState(0);
  const [away, setAway] = useState(false);
  // tests and screenshots: the dice's frozen clock (game/dice.ts) holds the cannon at that moment too
  const [clock, setClock] = useState(diceClock.frozen);
  useEffect(() => {
    const on = () => setClock(diceClock.frozen);
    window.addEventListener("fyodor:dice-clock", on);
    return () => window.removeEventListener("fyodor:dice-clock", on);
  }, []);
  useEffect(() => {
    if (clock !== null) return;
    const timers = c.times.map((t) => window.setTimeout(() => setLive((n) => n + 1), t));
    timers.push(window.setTimeout(() => setAway(true), c.leave));
    timers.push(window.setTimeout(onDone, c.leave + 420));
    return () => timers.forEach((t) => window.clearTimeout(t));
  }, [c, onDone, clock]);
  const puffs = clock === null ? live : c.at.filter((t) => t <= clock).length;
  const leaving = clock === null ? away : clock >= c.gone;
  const held = (since: number): CSSProperties | undefined => (clock === null ? undefined : { animationDelay: `-${Math.max(0, since)}ms`, animationPlayState: "paused" });
  return (
    <div className={`cannon2d${leaving ? " leaving" : ""}`} style={{ top: c.y, ...held(clock === null ? 0 : leaving ? clock - c.gone : clock) }} data-testid="cannon-2d" aria-hidden>
      <svg viewBox="0 0 120 70" className={`cannon2d-body${puffs ? " kick" : ""}`} key={`k${puffs}`} style={held(clock === null ? 0 : clock - (c.at[puffs - 1] ?? 0))}>
        <defs>
          <linearGradient id="cannon2d-brass" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#f0cf86" /><stop offset="0.45" stopColor="#b98a3e" /><stop offset="1" stopColor="#6e4c1c" />
          </linearGradient>
        </defs>
        <path d="M54 52 L104 52 L110 40 L60 36 Z" fill="#5a3a22" stroke="#2a1a0e" strokeWidth="2" />
        <path d="M8 22 Q6 30 8 38 L14 38 L84 42 Q100 42 104 30 Q100 18 84 18 L14 22 Z" fill="url(#cannon2d-brass)" stroke="#4a3210" strokeWidth="2" />
        <rect x="26" y="20" width="5" height="20" rx="2" fill="#d9b267" stroke="#4a3210" strokeWidth="1.2" />
        <rect x="62" y="18" width="5" height="25" rx="2" fill="#d9b267" stroke="#4a3210" strokeWidth="1.2" />
        <circle cx="110" cy="30" r="6" fill="#d9b267" stroke="#4a3210" strokeWidth="2" />
        <circle cx="74" cy="52" r="15" fill="none" stroke="#3b2a1c" strokeWidth="5" />
        <circle cx="74" cy="52" r="4" fill="#3b2a1c" />
        <path d="M74 37 V67 M59 52 H89 M63 41 L85 63 M85 41 L63 63" stroke="#3b2a1c" strokeWidth="2.4" />
      </svg>
      {Array.from({ length: puffs }, (_, i) => <span key={i} className="cannon2d-puff" style={held(clock === null ? 0 : clock - c.at[i]!)} />)}
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
interface Drawn extends DiceShow {
  color: string; name: string; dice: DrawnDie[]; fy: number; size: number; line: { x: number; y: number };
  /** -- table toys -- a cannon's volley lands this many ms later, tagged ("Goes first"). */
  wait: number; tag: string | null;
}

/** Where each drawn die comes to rest on the mat (seeded by the roll, never two on top of each other). */
function drawnOf(r: DiceShow, color: string, name: string, spot: { rect: DOMRect; near: boolean } | null, toy: { wait?: number; tag?: string | null } = {}): Drawn {
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
    ...r, color, name, dice, size, wait: toy.wait ?? 0, tag: toy.tag ?? null,
    // thrown in from the roller's edge of the mat
    fy: near ? rect.bottom - cy + size : rect.top - cy - size,
    line: { x: cx, y: near ? bottom : top - 32 },
  };
}

function DrawnThrow({ d, onClear }: { d: Drawn; onClear: () => void }) {
  const prefs = usePrefs.getState();
  const ms = prefs.reducedMotion || document.body.classList.contains("reduced-motion") ? 0 : Math.round(1150 / (prefs.animationSpeed || 1));
  const [rested, setRested] = useState(ms === 0);
  const wait = ms ? d.wait : 0;
  // a clack as each bounce lands (the drawn dice have no physics: three hops, the last one soft)
  useEffect(() => {
    if (!ms) return;
    const timers = [0.45, 0.72, 0.82].map((k, i) => window.setTimeout(() => diceClack([5, 3, 1.4][i]!, "table", 0.5, d.coin), wait + ms * k));
    timers.push(window.setTimeout(() => setRested(true), wait + ms));
    return () => timers.forEach((t) => window.clearTimeout(t));
  }, [ms, wait, d.coin]);
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
            ["--spin" as string]: x.spin, ["--rest" as string]: `${x.rest}deg`, ["--delay" as string]: `${x.delay + wait}ms`,
          } as CSSProperties}>
          <span className="dice2d-shadow" />
          <span className="dice2d-body"><DieGlyph kind={kind} value={x.value} color={d.color} title={x.ignored ? `${x.value}, ignored` : x.value} /></span>
        </div>
      ))}
      <button type="button" className={`dice-line dice-line2d${rested ? " on" : ""}${crit ? ` crit-${crit}` : ""}`} data-testid="dice-line" onClick={onClear}
        style={{ transform: `translate(${d.line.x}px, ${d.line.y}px) translate(-50%, 0)` }} title="Clear these dice (from this screen)" aria-label={`${line}. Clear these dice`}>
        <span className="dice-line-text">{line}</span>
        {(d.tag || crit) && <span className={`dice-line-tag${d.tag ? " toy" : ""}`}>{d.tag ?? (crit === "high" ? "Natural 20" : "Natural 1")}</span>}
        <span className="dice-line-x" aria-hidden>×</span>
      </button>
    </div>
  );
}
