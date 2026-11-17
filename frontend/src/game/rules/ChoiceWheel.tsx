/**
 * The public choice wheel (docs/TABLETOP_QOL_MILESTONE.md): a pending public choice (a color, a type, a player, a number, heads or
 * tails …) as tokens round a small dial, opened where the pointer is (centered after a key press). Aim with the pointer, digits or arrows;
 * click or Enter chooses; Esc (or "List") falls back to the usual list. It answers with the list's own `choose` action; the server still
 * decides. Logic: wheel.ts. Shown by the DecisionPanel (RulesHud.tsx) on the 2D and the 3D table alike; Settings → Table turns it off.
 */
import { prettyPrompt } from "./promptWords";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { ManaText } from "../../cards/ManaText";
import type { DecisionView, GameView } from "../../types/game";
import { boxOf, faceOf, indexAt, isNumberWheel, NO_KEYS, placeWheel, ringAngles, wheelFits, wheelKey, wheelLayout, HUB, type WheelKeys } from "./wheel";
import { choose } from "./intents";
import "./wheel.css";

/** Where the pointer last was, and whether a key was pressed since: the wheel opens at the pointer, or centered for keyboard play. */
const last = { x: Number.NaN, y: Number.NaN, keyboard: true };
if (typeof window !== "undefined") {
  const at = (e: PointerEvent) => { last.x = e.clientX; last.y = e.clientY; last.keyboard = false; };
  window.addEventListener("pointermove", at, { capture: true, passive: true });
  window.addEventListener("pointerdown", at, { capture: true, passive: true });
  window.addEventListener("keydown", (e) => { if (!["Shift", "Control", "Alt", "Meta"].includes(e.key)) last.keyboard = true; }, { capture: true });
}

/** Settings → UI scale zooms the page: pointer coordinates are screen pixels, the wheel's are zoomed ones. */
function pageZoom(): number {
  const z = Number.parseFloat(getComputedStyle(document.documentElement).zoom || "1");
  return z > 0 ? z : 1;
}

function screen(): { w: number; h: number; z: number } {
  const z = pageZoom();
  return { w: window.innerWidth / z, h: window.innerHeight / z, z };
}

const spoken = (label: string) => label.replace(/[{}]+/g, " ").trim();
const TYPING = "input, textarea, select, [contenteditable]";

export function ChoiceWheel({ d, view, onList }: { d: DecisionView; view: GameView; onList: () => void }) {
  const options = useMemo(() => d.options ?? [], [d.options]);
  const labels = useMemo(() => options.map((o) => o.label), [options]);
  const faces = useMemo(() => options.map((o) => faceOf(o, view.players)), [options, view.players]);
  const layout = useMemo(() => wheelLayout(options.map((o, i) => boxOf(faces[i]!, o.label))), [options, faces]);
  const numbers = isNumberWheel(labels);
  const [origin] = useState(() => {
    const s = screen();
    const anchor = last.keyboard || Number.isNaN(last.x) ? null : { x: last.x / s.z, y: last.y / s.z };
    return { center: placeWheel(anchor, layout, s), fits: wheelFits(layout, s) };
  });
  const [keys, setKeys] = useState<WheelKeys>(NO_KEYS);
  const [sent, setSent] = useState<number | null>(null);
  const root = useRef<HTMLDivElement>(null);
  const live = useRef({ keys, sent, onList, labels });
  live.current.keys = keys;
  live.current.onList = onList;
  live.current.labels = labels;

  // Too many long options for this screen: straight to the list, before anything is painted.
  useLayoutEffect(() => { if (!origin.fits) live.current.onList(); }, [origin.fits]);

  const aim = (index: number | null) => {
    if (index === null || live.current.sent !== null || index === live.current.keys.index) return;
    const next = { index, typed: "", at: 0 };
    live.current.keys = next;
    setKeys(next);
  };
  const pick = (index: number) => {
    const o = options[index];
    if (!o || live.current.sent !== null) return;
    live.current.sent = index;
    setSent(index);
    const retry = () => { live.current.sent = null; setSent(null); };
    void choose(d.id, [o.id]).then((ok) => { if (!ok) retry(); }, retry);
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey || e.defaultPrevented) return;
      const t = e.target instanceof HTMLElement ? e.target : null;
      if (t?.closest(TYPING) || document.querySelector(".modal-backdrop, .ctx-menu")) return;
      // a control the player focused elsewhere (a life counter's arrows) keeps its keys; digits and Esc stay the wheel's
      if (t && t !== document.body && !root.current?.contains(t) && !/^\d$/.test(e.key) && e.key !== "Escape") return;
      const r = wheelKey(live.current.keys, e.key, live.current.labels, performance.now());
      if (!r) return;
      e.preventDefault();
      e.stopImmediatePropagation(); // digits and Esc are the wheel's while it is open (not the camera keys)
      if (live.current.sent !== null) return;
      if (r.act === "list") return live.current.onList();
      live.current.keys = r.keys;
      setKeys(r.keys);
      if (r.act === "choose") pick(r.keys.index);
      else if (r.keys.index >= 0) root.current?.querySelectorAll<HTMLButtonElement>(".wheel-opt")[r.keys.index]?.focus({ preventScroll: true });
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [d.id]); // (one listener per decision: it reads the latest state from `live`)

  // The wheel takes the focus as it opens (screen readers announce it; its keys work), unless the player is typing or in a dialog.
  useEffect(() => {
    if (origin.fits && !document.activeElement?.closest(TYPING) && !document.querySelector(".modal-backdrop")) root.current?.focus({ preventScroll: true });
  }, [origin]);

  if (!origin.fits) return null;
  const { center } = origin;
  const aimAt = (e: { clientX: number; clientY: number }) => {
    const z = pageZoom();
    return indexAt(e.clientX / z - center.x, e.clientY / z - center.y, options.length);
  };
  const angle = keys.index >= 0 ? (ringAngles(options.length)[keys.index]! * 180) / Math.PI + 90 : 0;
  const seg = Math.min(90, 360 / options.length);
  const aimed = keys.index >= 0 ? options[keys.index] : undefined;

  return (
    <div ref={root} className="choice-wheel" role="menu" aria-label={d.prompt} tabIndex={-1} data-testid="choice-wheel"
      style={{ left: center.x, top: center.y }}>
      <div className="wheel-caption" style={{ top: layout.bounds.top - 8 }}>
        <span className="wheel-prompt" title={prettyPrompt(d.prompt)}>{prettyPrompt(d.prompt)}</span>
        <button type="button" className="wheel-list" data-testid="wheel-list" onClick={onList} title="Show the choices as a list">
          List <kbd>Esc</kbd>
        </button>
      </div>
      <div className={`wheel-dial ${aimed ? "aimed" : ""}`} aria-hidden
        style={{ width: layout.dial * 2, height: layout.dial * 2, ["--a" as string]: `${angle}deg`, ["--seg" as string]: `${seg}deg`,
          ["--track" as string]: `${layout.dial - layout.radius}px` }}
        onPointerMove={(e) => aim(aimAt(e))}
        onClick={(e) => { const i = aimAt(e); if (i !== null) pick(i); }} />
      <div className="wheel-hub" aria-hidden style={{ width: HUB * 2, height: HUB * 2 }}>
        {aimed ? <span className="wheel-hub-label"><ManaText text={aimed.label} /></span>
          : <span className="wheel-hub-idle">{sent === null ? "Choose" : "…"}</span>}
      </div>
      {options.map((o, i) => {
        const f = faces[i]!;
        const p = layout.points[i]!;
        const b = layout.boxes[i]!;
        const key = numbers ? null : <kbd aria-hidden>{i + 1}</kbd>;
        return (
          <button key={o.id} type="button" role="menuitem" data-testid={`wheel-option-${o.id}`}
            className={`wheel-opt k-${f.kind} ${b.disc ? "disc" : "pill"} ${keys.index === i ? "on" : ""} ${sent === i ? "sent" : ""}`}
            style={{ left: p.x, top: p.y, width: b.w, height: b.h, ...(f.kind === "player" ? { ["--seat" as string]: f.color } : {}) }}
            tabIndex={keys.index === i || (keys.index < 0 && i === 0) ? 0 : -1}
            aria-label={numbers ? spoken(o.label) : `${spoken(o.label)} (${i + 1})`}
            disabled={sent !== null && sent !== i} aria-disabled={sent !== null}
            onPointerEnter={() => aim(i)} onFocus={() => aim(i)} onClick={() => pick(i)}>
            {f.kind === "player" && <><i className="wheel-chip" aria-hidden>{f.initial}</i><span className="wheel-label">{o.label}</span>{key}</>}
            {f.kind === "color" && <><span className="wheel-pip" aria-hidden><ManaText text={`{${f.symbol}}`} /></span><span className="wheel-label">{o.label}</span>{key}</>}
            {f.kind === "mana" && <><span className="wheel-pips" aria-hidden><ManaText text={o.label} /></span>{key}</>}
            {f.kind === "number" && <span className="wheel-num" aria-hidden>{o.label}</span>}
            {f.kind === "text" && <><span className="wheel-label">{o.label}</span>{key}</>}
          </button>
        );
      })}
    </div>
  );
}
