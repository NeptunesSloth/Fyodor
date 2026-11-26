import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { perspective, useGame } from "../state/gameStore";
import { usePrefs } from "../state/prefs";
import { recapSections } from "./recapLog";
import "./ease.css";

const SHOWN_LINES = 6;

/**
 * -- turn recap -- beside the turn dial, after other players' turns: what they did since my last turn (recapLog.ts, from my own log),
 * one section per turn, and my life change. Collapsible; ✕ or Esc dismisses it, and it goes by itself once I act (a click on the table
 * or a key). Settings: Turn recap.
 */
export function TurnRecap() {
  const on = usePrefs((s) => s.turnRecap);
  const view = useGame((s) => s.view);
  const actingAs = useGame((s) => s.actingAs);
  const me = view && view.viewer !== "__spectator__" ? perspective(view, actingAs) : null;
  const [seen, setSeen] = useState<Record<string, number>>({}); // per seat (hot-seat): turns up to this one are dismissed
  const [folded, setFolded] = useState(false);
  const [open, setOpen] = useState<number | null>(null); // the section showing all its lines
  const box = useRef<HTMLElement | null>(null);
  const [at, setAt] = useState<{ right: number; bottom: number } | null>(null);
  const sections = useMemo(() => (view && me && on ? recapSections(view, me, seen[me] ?? 0) : []), [view, me, on, seen]);
  const last = sections[sections.length - 1]?.turn ?? 0;
  const shown = sections.length > 0;

  const dismiss = () => me && setSeen((s) => ({ ...s, [me]: last }));
  useEffect(() => {
    if (!shown) return;
    const since = performance.now();
    // I act: a click on the table (not on the recap), or a key that isn't moving focus about
    const down = (e: Event) => {
      if (performance.now() - since < 800 || box.current?.contains(e.target as Node)) return;
      if (e instanceof KeyboardEvent && (e.key === "Tab" || e.key === "Shift" || e.key === "Control" || e.key === "Alt" || e.key === "Meta")) return;
      dismiss();
    };
    window.addEventListener("pointerdown", down, true);
    window.addEventListener("keydown", down, true);
    return () => { window.removeEventListener("pointerdown", down, true); window.removeEventListener("keydown", down, true); };
  }); // (re-bound each render: `dismiss` reads the latest turn)
  useLayoutEffect(() => {
    if (!shown) return;
    const place = () => {
      const dial = document.querySelector(".turn-dial-wrap")?.getBoundingClientRect();
      setAt(dial && dial.width ? { right: Math.round(window.innerWidth - dial.left + 10), bottom: Math.round(window.innerHeight - dial.bottom) } : null);
    };
    place();
    window.addEventListener("resize", place);
    return () => window.removeEventListener("resize", place);
  }, [shown, view]);
  if (!shown || !view) return null;
  const total = sections.reduce((n, s) => n + s.lines.length, 0);
  const life = sections.reduce((n, s) => n + s.life, 0);
  const lifeText = life ? `you ${life < 0 ? "lost" : "gained"} ${Math.abs(life)} life` : "";
  return createPortal(
    <aside ref={box} className="turn-recap plaque-wrap" role="status" aria-live="polite" aria-label="While you waited" data-testid="turn-recap"
      style={at ? { right: at.right, bottom: at.bottom } : undefined}>
      <div className="plaque tr-plaque">
        <header className="tr-head">
          <button type="button" className="tr-fold" aria-expanded={!folded} onClick={() => setFolded(!folded)} title={folded ? "Show the recap" : "Fold the recap"}>
            <span aria-hidden>{folded ? "▸" : "▾"}</span> Since your turn
            {folded && <span className="tr-sum"> · {sections.map((s) => s.who).filter((w, i, a) => a.indexOf(w) === i).join(", ")}: {total} {total === 1 ? "action" : "actions"}{lifeText && ` · ${lifeText}`}</span>}
          </button>
          <button type="button" className="tr-close" aria-label="Dismiss the recap" title="Dismiss (Esc)" data-testid="turn-recap-close" onClick={dismiss}>✕</button>
        </header>
        {!folded && sections.map((s) => {
          const all = open === s.turn || s.lines.length <= SHOWN_LINES;
          const lines = all ? s.lines : s.lines.slice(0, SHOWN_LINES);
          return (
            <section key={s.turn} className="tr-sec">
              <h4><b>{s.who}</b> <span className="hint">· turn {s.turn}</span></h4>
              {lines.length > 0 && <p className="tr-lines">{lines.join(" · ")}</p>}
              {!all && <button type="button" className="tr-more" onClick={() => setOpen(s.turn)}>+{s.lines.length - SHOWN_LINES} more</button>}
              {s.life !== 0 && <p className={`tr-life ${s.life < 0 ? "down" : "up"}`}>You {s.life < 0 ? "lost" : "gained"} {Math.abs(s.life)} life</p>}
            </section>
          );
        })}
      </div>
    </aside>,
    document.body,
  );
}
