import { useEffect, useRef, useState } from "react";
import { toast } from "../components/Toasts";
import { perspective, useGame } from "../state/gameStore";
import { usePrefs } from "../state/prefs";
import { send } from "./actions";
import { rollLine, type DiceShow } from "./dice";
import { DieGlyph, type GlyphKind } from "./DieGlyph";
import { keyLabel } from "./hotkeys";
import "./dice.css";

/**
 * The table's roll panel (the tool tray's Dice button, or Shift+R): pick a die and how many, then Roll; quick picks
 * for the usual rolls; the table's last few rolls, each one click from rolling the same again. It sends the server's
 * own `roll` (or `coin`) action: the host rolls, the log records it, and every table throws the dice it rolled.
 * Enter rolls, Esc closes. The last pick is remembered on this device.
 */
const KINDS: { id: GlyphKind; label: string; sides: number }[] = [
  { id: "d4", label: "d4", sides: 4 }, { id: "d6", label: "d6", sides: 6 }, { id: "d8", label: "d8", sides: 8 },
  { id: "d10", label: "d10", sides: 10 }, { id: "d12", label: "d12", sides: 12 }, { id: "d20", label: "d20", sides: 20 },
  { id: "d100", label: "d100", sides: 100 }, { id: "coin", label: "Coin", sides: 2 },
];
const MAX = 12;
const KEY = "fyodor.dicePanel";

interface Choice { kind: GlyphKind; count: number }
const load = (): Choice => {
  try {
    const p = JSON.parse(localStorage.getItem(KEY) ?? "null") as Choice | null;
    if (p && KINDS.some((k) => k.id === p.kind) && Number.isInteger(p.count) && p.count >= 1 && p.count <= MAX) return p;
  } catch { /* first time, or private mode */ }
  return { kind: "d20", count: 1 };
};
const save = (p: Choice) => {
  try { localStorage.setItem(KEY, JSON.stringify(p)); } catch { /* not remembered */ }
};

/** The action for a roll: a coin flip is its own action. */
export function rollAction(sides: number, count: number, coin: boolean): { type: "roll" | "coin"; sides?: number; count: number } {
  return coin ? { type: "coin", count } : { type: "roll", sides, count };
}

/** "3d6" → 3 × d6; "d20" → 1 × d20 (2–1000 sides, 1–100 dice, as the server allows). */
export function parseDice(text: string): { sides: number; count: number } | null {
  const m = /^\s*(\d*)\s*d\s*(\d+)\s*$/i.exec(text);
  if (!m) return null;
  const count = Number(m[1] || 1);
  const sides = Number(m[2]);
  if (!Number.isInteger(count) || count < 1 || count > 100 || sides < 2 || sides > 1000) return null;
  return { sides, count };
}

export function DicePanel({ onClose }: { onClose: () => void }) {
  const [pick, setPick] = useState<Choice>(load);
  const [custom, setCustom] = useState("");
  const panel = useRef<HTMLDivElement>(null);
  const seats = useGame((s) => s.view?.players);
  const log = useGame((s) => s.view?.log);
  const keymap = usePrefs((s) => s.keymap);
  const mine = useGame((s) => (s.view ? s.view.players.find((p) => p.id === perspective(s.view!, s.actingAs))?.color : undefined));
  const recent = (log ?? []).filter((e) => e.roll).slice(-4).reverse();
  const kind = KINDS.find((k) => k.id === pick.kind)!;
  const coin = kind.id === "coin";
  const label = coin ? (pick.count === 1 ? "a coin" : `${pick.count} coins`) : `${pick.count > 1 ? pick.count : ""}d${kind.sides}`;

  const roll = (sides: number, count: number, isCoin = false) => {
    void send(rollAction(sides, count, isCoin));
  };
  const rollPick = () => {
    save(pick);
    roll(kind.sides, pick.count, coin);
  };
  const rollCustom = () => {
    const d = parseDice(custom);
    if (!d) return toast("Use the form XdY, e.g. 3d6 or d100", "warn");
    roll(d.sides, d.count);
  };

  // Enter rolls (outside the text box, which rolls its own), Esc closes, a click outside closes
  const enter = useRef(rollPick);
  enter.current = rollPick;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
        return;
      }
      if (e.key !== "Enter" || e.repeat || (e.target as HTMLElement).closest?.("input, textarea")) return;
      const t = e.target as HTMLElement;
      if (t.closest?.("button") && !t.closest("[data-enter-rolls]")) return; // a focused button answers Enter itself
      e.preventDefault();
      enter.current();
    };
    const onDown = (e: PointerEvent) => {
      const t = e.target as HTMLElement;
      if (panel.current?.contains(t) || t.closest?.("[data-dice-toggle]")) return;
      onClose();
    };
    window.addEventListener("keydown", onKey, true);
    window.addEventListener("pointerdown", onDown, true);
    return () => {
      window.removeEventListener("keydown", onKey, true);
      window.removeEventListener("pointerdown", onDown, true);
    };
  }, [onClose]);

  const key = keyLabel("dice", keymap);
  const set = (p: Partial<Choice>) => setPick((cur) => ({ ...cur, ...p }));
  const colorOf = (pid: string | null) => seats?.find((p) => p.id === pid)?.color;
  const nameOf = (pid: string | null) => seats?.find((p) => p.id === pid)?.name ?? "";
  return (
    <div className="dice-panel" ref={panel} role="dialog" aria-label="Roll dice" data-testid="dice-panel">
      <div className="dice-panel-head">
        <span className="dice-panel-title">Roll dice</span>
        <span className="spacer" />
        {key && <kbd title="Opens and closes this panel">{key}</kbd>}
      </div>
      <div className="dice-kinds" role="group" aria-label="Die">
        {KINDS.map((k) => (
          <button key={k.id} type="button" className="dice-kind" aria-pressed={pick.kind === k.id} onClick={() => set({ kind: k.id })}
            onDoubleClick={() => { set({ kind: k.id }); roll(k.sides, pick.count, k.id === "coin"); }} data-testid={`dice-kind-${k.id}`}>
            <DieGlyph kind={k.id} value={k.id === "coin" ? "H" : k.id === "d100" ? "%" : String(k.sides)} color={mine} />
            {k.label}
          </button>
        ))}
      </div>
      <div className="dice-roll-row">
        <div className="dice-count" role="group" aria-label="How many">
          <button type="button" onClick={() => set({ count: pick.count - 1 })} disabled={pick.count <= 1} aria-label="One fewer">−</button>
          <output aria-live="polite" data-testid="dice-count">{pick.count}</output>
          <button type="button" onClick={() => set({ count: pick.count + 1 })} disabled={pick.count >= MAX} aria-label="One more">+</button>
        </div>
        <button type="button" className="tt-btn brass" onClick={rollPick} data-enter-rolls data-testid="dice-roll" autoFocus>Roll {label}</button>
      </div>
      <div className="dice-quick" role="group" aria-label="Quick rolls">
        <button type="button" className="tt-btn" onClick={() => roll(20, 1)} data-testid="dice-quick-d20">1d20</button>
        <button type="button" className="tt-btn" onClick={() => roll(6, 2)} data-testid="dice-quick-2d6">2d6</button>
        <button type="button" className="tt-btn" onClick={() => roll(2, 1, true)} data-testid="dice-quick-coin">Flip a coin</button>
      </div>
      <form className="dice-custom" onSubmit={(e) => { e.preventDefault(); rollCustom(); }}>
        <input value={custom} onChange={(e) => setCustom(e.target.value)} placeholder="Other: 3d6, d100, 4d8…" aria-label="Other dice, as XdY" maxLength={12} />
        <button type="submit" className="tt-btn" disabled={!custom.trim()}>Roll</button>
      </form>
      {recent.length > 0 && (
        <section className="dice-recent" aria-label="Recent rolls">
          <div className="dice-recent-head">Recent rolls</div>
          <ol>
            {recent.map((e) => {
              const r = e.roll!;
              const show: Pick<DiceShow, "sides" | "results" | "coin" | "ignored"> = r;
              return (
                <li key={e.seq} style={{ ["--seat" as string]: colorOf(e.actor) }}>
                  <i className="who" aria-hidden />
                  <span className="what" title={rollLine(nameOf(e.actor), show)}>{rollLine(nameOf(e.actor), show)}</span>
                  <button type="button" className="tt-btn ghost" onClick={() => roll(r.sides, r.results.length - (r.ignored?.length ?? 0) || 1, r.coin)} title="Roll the same dice">Again</button>
                </li>
              );
            })}
          </ol>
        </section>
      )}
      <p className="dice-panel-hint">Rolled on the host and written to the log; every table sees the same dice land. <kbd>Enter</kbd> rolls, <kbd>Esc</kbd> closes.</p>
    </div>
  );
}
