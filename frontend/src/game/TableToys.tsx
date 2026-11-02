import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Modal } from "../components/Modal";
import { usePrefs } from "../state/prefs";
import { resolveRenderer } from "../table3d/renderer";
import type { ToyTrayScene } from "../table3d/toyTray";
import type { GameView } from "../types/game";
import { play } from "./sound";
import { DieGlyph } from "./DieGlyph";
import "./dice.css";
import {
  DIE_KINDS, MAX_DICE, TALLY_MAX, TALLY_MIN, addDie, emptyPool, keepRoll, loadToys, poolLabel, poolOf, poolSize,
  rollHeadline, rollLine, rollPool, rollTotal, saveToys, secureInt, sidesOf, spinPath, spinPlayers,
  type DieKind, type Roll, type ToysSaved,
} from "./toys";
import "./night.css";
import "./toys.css";

/*
 * DICE & TOYS (docs/ELIMINATION_HUB.md): something light for a player who is out, or a spectator, while the game goes
 * on. A dice tray (d4 … d20 and a coin, several at once, with a short history), a random player that is clearly just
 * for fun, and a tally. Everything stays in this browser (game/toys.ts): nothing is sent, and the live table's dice,
 * log and sounds are untouched. The dice are the table's own: the 3D tray throws them with table3d/dice.ts (with their
 * own clatter), the 2D tray with the drawn dice (game/DieGlyph.tsx), the fallback without WebGL or on low graphics.
 */

type Tab = "dice" | "spin" | "tally";
const TABS: { id: Tab; label: string }[] = [{ id: "dice", label: "Dice tray" }, { id: "spin", label: "Random player" }, { id: "tally", label: "Tally" }];
const NAME: Record<DieKind, string> = { d4: "d4", d6: "d6", d8: "d8", d10: "d10", d12: "d12", d20: "d20", coin: "coin" };

const reducedMotion = () => {
  if (usePrefs.getState().reducedMotion) return true;
  try {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch {
    return false;
  }
};

/** Enter rolls (or spins) unless focus is on a text field or on another control that answers Enter itself. */
function enterIsOurs(e: KeyboardEvent): boolean {
  if (e.key !== "Enter" || e.repeat || e.defaultPrevented || e.altKey || e.ctrlKey || e.metaKey) return false;
  const t = e.target as HTMLElement | null;
  if (!t?.closest) return true;
  if (t.closest("input, textarea, select, [contenteditable]")) return false;
  return !t.closest("button, a") || !!t.closest("[data-enter-rolls]");
}

export function TableToys({ view, viewer, onClose }: { view: GameView; viewer?: string; onClose: () => void }) {
  const [tab, setTab] = useState<Tab>("dice");
  const [saved, setSaved] = useState<ToysSaved>(loadToys);
  const update = useCallback((fn: (s: ToysSaved) => ToysSaved) => setSaved((s) => {
    const next = fn(s);
    saveToys(next);
    return next;
  }), []);
  const me = viewer ?? view.viewer;
  const color = view.players.find((p) => p.id === me)?.color ?? "#d7ae63";
  const players = useMemo(() => spinPlayers(view), [view]);
  const enter = useRef<() => void>(() => undefined);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!enterIsOurs(e)) return;
      e.preventDefault();
      e.stopPropagation();
      enter.current();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <Modal title="Dice & toys" onClose={onClose} footer={
      <>
        <span className="hint">Only in this browser: nothing is sent to the table. {tab === "tally" ? "" : `Enter ${tab === "dice" ? "rolls" : "spins"} · `}Esc closes.</span>
        <span className="spacer" />
        <button className="tt-btn" onClick={onClose}>Close</button>
      </>
    }>
      <div className="toys" data-testid="toys" style={{ ["--seat" as string]: color }}>
        <div className="toys-tabs" role="tablist" aria-label="Toys">
          {TABS.map((t) => (
            <button key={t.id} role="tab" aria-selected={tab === t.id} onClick={() => setTab(t.id)} data-testid={`toys-tab-${t.id}`}>{t.label}</button>
          ))}
        </div>
        {tab === "dice" && <DiceToy saved={saved} update={update} color={color} enter={enter} />}
        {tab === "spin" && <SpinToy players={players} enter={enter} />}
        {tab === "tally" && <TallyToy tally={saved.tally} update={update} enter={enter} />}
      </div>
    </Modal>
  );
}

// -- the dice tray -----------------------------------------------------------------------------------------------------

/** Whether the tray will be the 3D one (as TrayView decides). */
const threeTray = () => usePrefs.getState().graphics !== "low" && resolveRenderer(usePrefs.getState().renderer) === "3d";

function DiceToy({ saved, update, color, enter }: {
  saved: ToysSaved;
  update: (fn: (s: ToysSaved) => ToysSaved) => void;
  color: string;
  enter: React.RefObject<() => void>;
}) {
  const [last, setLast] = useState<Roll | null>(null);
  const { pool, history } = saved;
  const size = poolSize(pool);
  const rollThis = useCallback((p = pool) => {
    const roll = rollPool(p);
    if (!roll) return;
    setLast(roll);
    update((s) => keepRoll(s, roll));
    // this browser only; the 3D tray's dice make their own sound as they land
    if (!threeTray()) play(roll.groups.every((g) => g.kind === "coin") ? "coin" : "dice");
  }, [pool, update]);
  enter.current = () => rollThis();
  const add = (kind: DieKind, delta: number) => update((s) => ({ ...s, pool: addDie(s.pool, kind, delta) }));

  return (
    <div className="toys-dice">
      <div className="toys-pick" data-enter-rolls role="group" aria-label="Dice to roll">
        {DIE_KINDS.map((k) => (
          <div key={k} className={`toys-die ${pool[k] ? "on" : ""}`}>
            <button className="toys-add" onClick={() => add(k, 1)} disabled={addDie(pool, k, 1) === pool}
              aria-label={`Add a ${NAME[k]}`} title={`Add a ${NAME[k]}`} data-testid={`toys-add-${k}`}>
              <DieGlyph kind={k} value={k === "coin" ? "H" : String(sidesOf(k))} color={color} />
              <span className="toys-kind">{NAME[k]}</span>
            </button>
            <div className="toys-step">
              <button className="toys-less" onClick={() => add(k, -1)} disabled={!pool[k]} aria-label={`Remove a ${NAME[k]}`} title={`Remove a ${NAME[k]}`}>−</button>
              <span className="toys-n" aria-label={`${pool[k]} ${NAME[k]}`}>{pool[k] ? `×${pool[k]}` : "·"}</span>
            </div>
          </div>
        ))}
      </div>
      <div className="toys-pool">
        <span className="toys-pool-label">{size ? poolLabel(pool) : "Pick some dice"}</span>
        <span className="hint">{size}/{MAX_DICE}</span>
        <button className="tt-btn ghost" onClick={() => update((s) => ({ ...s, pool: emptyPool() }))} disabled={!size}>Clear dice</button>
        <span className="spacer" />
        <button className="tt-btn brass toys-roll" data-enter-rolls data-testid="toys-roll" disabled={!size} onClick={() => rollThis()} autoFocus>Roll</button>
      </div>
      <TrayView roll={last} color={color} />
      <div className="toys-result" aria-live="polite">
        {last && (
          <div key={last.id} className="toys-result-row">
            <span className="toys-total-label">{rollTotal(last) === null ? "Coins" : "Total"}</span>
            <span className="toys-total" data-testid="toys-total">{rollHeadline(last)}</span>
            <span className="toys-breakdown">{rollLine(last)}</span>
          </div>
        )}
      </div>
      <section className="toys-history" aria-label="Recent rolls">
        <div className="toys-history-head">
          <span>Recent rolls</span>
          <span className="hint">this browser only</span>
          <span className="spacer" />
          <button className="tt-btn ghost" onClick={() => update((s) => ({ ...s, history: [] }))} disabled={!history.length} data-testid="toys-clear">Clear</button>
        </div>
        {history.length ? (
          <ol data-testid="toys-history">
            {history.map((r) => (
              <li key={r.id}>
                <span className="toys-history-sum">{rollHeadline(r)}</span>
                <span className="toys-history-line" title={rollLine(r)}>{rollLine(r)}</span>
                <button className="tt-btn ghost" onClick={() => rollThis(poolOf(r))} title="Roll these dice again">Reroll</button>
              </li>
            ))}
          </ol>
        ) : <p className="hint">No rolls yet.</p>}
      </section>
    </div>
  );
}

/** The tray: the 3D throw when the 3D table can run here, else (or if it fails) the 2D throw. */
function TrayView({ roll, color }: { roll: Roll | null; color: string }) {
  const renderer = usePrefs((s) => s.renderer);
  const graphics = usePrefs((s) => s.graphics);
  const [failed, setFailed] = useState(false);
  const three = !failed && graphics !== "low" && resolveRenderer(renderer) === "3d";
  return (
    <div className={`toys-tray ${three ? "is-3d" : ""}`} data-testid="toys-tray">
      {three ? <Tray3D roll={roll} color={color} quality={graphics === "high" ? "high" : "medium"} onFail={() => setFailed(true)} /> : <Tray2D roll={roll} color={color} />}
      {!roll && <span className="toys-tray-empty">Pick dice, then roll</span>}
    </div>
  );
}

/** The drawn dice (as the 2D table's, game/DiceLayer.tsx): each die tumbles in from the near edge and rests, number up. */
function Tray2D({ roll, color }: { roll: Roll | null; color: string }) {
  if (!roll) return null;
  let i = 0;
  return (
    <div className="toys-tray-2d" key={roll.id} aria-hidden>
      {roll.groups.map((g) => (
        <div key={g.kind} className="toys-group">
          {g.results.map((v, j) => {
            const n = i++;
            return (
              <span key={j} className="die2d-wrap toys-glyph" style={{ ["--i" as string]: n, ["--fx" as string]: `${((n * 47) % 140) - 70}px`, ["--fy" as string]: "150px" }}>
                <DieGlyph kind={g.kind} value={g.kind === "coin" ? (v ? "H" : "T") : String(v)} color={color} />
              </span>
            );
          })}
        </div>
      ))}
    </div>
  );
}

/** A small three.js tray with the live table's dice (table3d/toyTray.ts, loaded only here). */
function Tray3D({ roll, color, quality, onFail }: { roll: Roll | null; color: string; quality: "medium" | "high"; onFail: () => void }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const scene = useRef<ToyTrayScene | null>(null);
  const shown = useRef<string | null>(null);
  const latest = useRef({ roll, color });
  latest.current = { roll, color };
  const fail = useRef(onFail);
  fail.current = onFail;
  const throwIt = useCallback(() => {
    const s = scene.current;
    const { roll: r, color: c } = latest.current;
    if (!s || !r || shown.current === r.id) return;
    shown.current = r.id;
    const speed = usePrefs.getState().animationSpeed || 1;
    try {
      s.throw(r.groups.map((g) => ({ key: `${r.id}:${g.kind}`, sides: sidesOf(g.kind), coin: g.kind === "coin", results: g.results })),
        { reduced: reducedMotion(), speed, color: c, look: usePrefs.getState().diceLook });
    } catch {
      fail.current();
    }
  }, []);
  useEffect(() => {
    let alive = true;
    let made: ToyTrayScene | null = null;
    import("../table3d/toyTray").then((m) => {
      if (!alive || !canvas.current) return;
      try {
        made = new m.ToyTrayScene(canvas.current, quality, usePrefs.getState().diceLook);
        scene.current = made;
        throwIt();
      } catch {
        fail.current();
      }
    }, () => alive && fail.current());
    return () => {
      alive = false;
      made?.dispose();
      scene.current = null;
      shown.current = null;
    };
  }, [quality, throwIt]);
  useEffect(throwIt, [roll, throwIt]);
  return <canvas ref={canvas} className="toys-canvas" aria-hidden />;
}

// -- the random player (just for fun) ----------------------------------------------------------------------------------

function SpinToy({ players, enter }: { players: { id: string; name: string }[]; enter: React.RefObject<() => void> }) {
  const [left, setLeft] = useState<Set<string>>(() => new Set());
  const [lit, setLit] = useState<string | null>(null);
  const [picked, setPicked] = useState<string | null>(null);
  const [spinning, setSpinning] = useState(false);
  const timers = useRef<number[]>([]);
  useEffect(() => () => timers.current.forEach((t) => window.clearTimeout(t)), []);
  const pool = players.filter((p) => !left.has(p.id));
  const spin = () => {
    if (spinning || pool.length < 2) return;
    const pick = secureInt(pool.length);
    const name = pool[pick]!;
    setPicked(null);
    if (reducedMotion()) {
      setLit(null);
      setPicked(name.id);
      return;
    }
    const speed = usePrefs.getState().animationSpeed || 1;
    const path = spinPath(pool.length, pick);
    setSpinning(true);
    let at = 0;
    path.forEach((idx, k) => {
      const ease = k / Math.max(1, path.length - 1);
      at += (40 + 230 * ease * ease) / speed;
      timers.current.push(window.setTimeout(() => setLit(pool[idx]!.id), at));
    });
    timers.current.push(window.setTimeout(() => {
      setLit(null);
      setPicked(name.id);
      setSpinning(false);
      timers.current = [];
    }, at + 180 / speed));
  };
  enter.current = spin;
  const toggle = (id: string) => {
    setPicked(null);
    setLeft((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  };
  const winner = players.find((p) => p.id === picked);
  return (
    <div className="toys-spin">
      <p className="toys-note"><b>Just for fun.</b> This never sets the turn order or anything else in the game, and nobody else sees it.</p>
      <div className="toys-names" role="group" aria-label="Players to pick from (press to leave one out)">
        {players.map((p) => (
          <button key={p.id} className={`toys-name ${lit === p.id ? "lit" : ""} ${picked === p.id ? "picked" : ""}`} aria-pressed={!left.has(p.id)}
            disabled={spinning} onClick={() => toggle(p.id)} title={left.has(p.id) ? "Put back in" : "Leave out"}>
            {p.name}
          </button>
        ))}
      </div>
      <div className="toys-pool">
        <span className="toys-spin-result" aria-live="polite" data-testid="toys-spin-result">
          {winner ? <>Landed on <b>{winner.name}</b> (just for fun)</> : pool.length < 2 ? "Leave at least two names in." : spinning ? "Spinning…" : ""}
        </span>
        <span className="spacer" />
        <button className="tt-btn brass" data-enter-rolls data-testid="toys-spin" disabled={spinning || pool.length < 2} onClick={spin}>Spin</button>
      </div>
    </div>
  );
}

// -- the tally ---------------------------------------------------------------------------------------------------------

function TallyToy({ tally, update, enter }: {
  tally: ToysSaved["tally"];
  update: (fn: (s: ToysSaved) => ToysSaved) => void;
  enter: React.RefObject<() => void>;
}) {
  enter.current = () => undefined;
  const set = (patch: Partial<ToysSaved["tally"]>) => update((s) => {
    const t = { ...s.tally, ...patch };
    return { ...s, tally: { ...t, count: Math.max(TALLY_MIN, Math.min(TALLY_MAX, t.count)) } };
  });
  return (
    <div className="toys-tally">
      <label className="toys-tally-label">
        <span className="hint">Counting</span>
        <input value={tally.label} maxLength={40} onChange={(e) => set({ label: e.target.value })} aria-label="What you are counting" />
      </label>
      <div className="toys-tally-n" aria-live="polite" data-testid="toys-tally">{tally.count}</div>
      <div className="toys-tally-row">
        <button className="tt-btn" onClick={() => set({ count: tally.count - 1 })} aria-label="Minus one">−1</button>
        <button className="tt-btn brass" onClick={() => set({ count: tally.count + 1 })} aria-label="Plus one">+1</button>
        <button className="tt-btn" onClick={() => set({ count: tally.count + 5 })} aria-label="Plus five">+5</button>
        <button className="tt-btn ghost" onClick={() => set({ count: 0 })} disabled={!tally.count}>Reset</button>
      </div>
      <p className="hint">A side count of your own (spells cast this turn, times someone said "in response"…). The game's counters are untouched.</p>
    </div>
  );
}

