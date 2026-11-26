import { useEffect, useRef, useState } from "react";
import { useGame } from "../state/gameStore";
import { Icon } from "../components/Icon";
import { motionMs, motionOn, onMotionSkip } from "./motion/timing";
import { DAY_NIGHT_MOMENT_MS, dayNightMoment, type DayNightMode, type DayNightMoment } from "./dayNight";
import "./daynight.css";

interface Shown extends DayNightMoment { key: number; x: number; y: number }

/**
 * -- day and night (CR 726) -- both tables: when it becomes day or night, the new sun or moon rises over a small horizon just
 * under the top bar's indicator (the old one sets) with the rules' words, then fades (≈1.4 s at 1×, click-through, any click or
 * key ends it). The 2D table's felt also turns a shade cooler and darker for the night (a layer under the cards, a CSS fade);
 * the 3D room eases its own light (table3d/dayNight.ts). Reduced motion: no moment, the felt changes at once. A table that
 * loads at night is simply night. Game state never waits on any of it.
 */
export function DayNightLayer({ three }: { three: boolean }) {
  const mode = useGame((s) => s.view?.table.day_night ?? null) as DayNightMode;
  const prev = useRef(mode);
  const [shown, setShown] = useState<Shown | null>(null);
  const tint = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const was = prev.current;
    prev.current = mode;
    const m = dayNightMoment(was, mode);
    const reduced = document.body.classList.contains("reduced-motion");
    if (!m || reduced || !motionOn()) {
      setShown(null);
      return;
    }
    // under the indicator (it is in the bar whenever day or night is on); the bar's right end if it isn't drawn
    const at = document.querySelector(".game-top .daynight")?.getBoundingClientRect();
    const x = at ? at.left + at.width / 2 : window.innerWidth - 220;
    const y = at ? at.bottom + 8 : 54;
    setShown({ ...m, key: performance.now(), x, y });
  }, [mode]);

  useEffect(() => {
    if (!shown) return;
    const done = window.setTimeout(() => setShown(null), motionMs(DAY_NIGHT_MOMENT_MS, false));
    const off = onMotionSkip(() => {
      setShown(null);
      // the wood and the felt jump to their end as well
      const table = tint.current?.parentElement;
      if (table) {
        table.classList.add("dn-instant");
        void table.offsetWidth;
        table.classList.remove("dn-instant");
      }
    });
    return () => {
      window.clearTimeout(done);
      off();
    };
  }, [shown]);

  return (
    <>
      {!three && <div ref={tint} className={`daynight-tint${mode === "night" ? " on" : ""}`} aria-hidden data-testid="daynight-tint" />}
      {shown && (
        <div key={shown.key} className={`daynight-moment to-${shown.to}`} style={{ left: shown.x, top: shown.y }} role="status" data-testid="daynight-moment">
          <div className="dnm-sky" aria-hidden>
            {shown.from && <span className={`dnm-glyph sets ${shown.from}`}><Icon name={shown.from === "day" ? "sun" : "moon"} size={22} /></span>}
            <span className={`dnm-glyph rises ${shown.to}`}><Icon name={shown.to === "day" ? "sun" : "moon"} size={22} /></span>
            <span className="dnm-horizon" />
          </div>
          <span className="dnm-line">{shown.line}</span>
        </div>
      )}
    </>
  );
}
