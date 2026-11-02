/**
 * END-OF-GAME TABLE SCENE on the 2D table (the beats are endScene.ts; the 3D table's is table3d/endScene3d.ts): over the
 * table only, under the result's spotlight, the table darkens toward the result's colour (a tinted veil, deeper at the
 * edges), one soft ring of light (or shadow) spreads over the battlefields, and a handful of motes rise.
 *
 * Display only, in a layer of its own that never takes input (pointer-events: none). WAAPI on transform and opacity
 * only, at the player's animation speed; the whole layer fades out when the scene lets go, and is gone when it has.
 * Reduced motion (the setting, low graphics or the system's) keeps only the dim.
 */
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { endMs, endSceneFrozen, moteAt, moteFrame, moteTiming, onEndScene, type EndCue, type EndLook } from "./endScene";
import { motionPrefs } from "./timing";
import "./endScene2d.css";

const EASE_OUT = "cubic-bezier(0.23, 1, 0.32, 1)";
const EASE_IN_OUT = "cubic-bezier(0.77, 0, 0.175, 1)";
/** How far a mote rises over its life on the 2D table, per unit of the look's ``rise`` (px). */
const RISE_PX = 46;

function reducedNow(): boolean {
  if (motionPrefs().reduced || document.body.classList.contains("reduced-motion")) return true;
  return typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/**
 * The 2D table's dim: a wash of the kind's colour, darkest at the edges (the 3D table multiplies its light; a page can't
 * multiply what lies under a layer of its own, so the 2D table lays a dark, tinted veil over it instead).
 */
function wash(look: EndLook): { centre: string; edge: string } {
  const c = look.tint.map((t) => Math.round(255 * 0.16 * t ** 6)).join(" ");
  const a = 1 - look.dim;
  return { centre: `rgb(${c} / ${(a * 0.65).toFixed(3)})`, edge: `rgb(${c} / ${Math.min(0.6, a * 1.9).toFixed(3)})` };
}

/** The table's box on screen (the 2D table's main area; the whole window if it isn't there). */
function tableBox(): { left: number; top: number; width: number; height: number } {
  const el = document.querySelector("main.table");
  const r = el?.getBoundingClientRect();
  if (r && r.width > 0 && r.height > 0) return { left: r.left, top: r.top, width: r.width, height: r.height };
  return { left: 0, top: 0, width: window.innerWidth, height: window.innerHeight };
}

export function EndScene2D() {
  const [cue, setCue] = useState<EndCue | null>(null);
  useEffect(() => onEndScene(setCue), []);
  // in place (not portalled): it must sit under the spotlight, over the table
  if (!cue || typeof document === "undefined") return null;
  return <Scene key={cue.id} cue={cue} />;
}

function Scene({ cue }: { cue: EndCue }) {
  const layer = useRef<HTMLDivElement>(null);
  const anims = useRef<Animation[]>([]);
  const [box] = useState(tableBox);
  const [reduced] = useState(reducedNow);
  const look = cue.look;
  const pulse = !reduced ? look.pulse : null;
  const motes = !reduced && look.motes ? Array.from({ length: look.motes.count }, (_, i) => i) : [];
  const { centre, edge } = wash(look);

  // the scene's animations, started once (a remount for every new scene)
  useLayoutEffect(() => {
    const root = layer.current;
    if (!root) return;
    const ms = (x: number) => endMs(cue, x);
    const list: Animation[] = [];
    const shade = root.querySelector<HTMLElement>(".es2d-shade");
    if (shade) list.push(shade.animate([{ opacity: 0 }, { opacity: 1 }], { duration: ms(look.dimIn), easing: EASE_OUT, fill: "both" }));
    const ring = root.querySelector<HTMLElement>(".es2d-pulse");
    if (ring && look.pulse) {
      const p = look.pulse;
      const timing = { delay: ms(p.at), duration: ms(p.dur), fill: "both" as const };
      list.push(ring.animate([{ transform: "translate(-50%, -50%) scale(0.3)" }, { transform: "translate(-50%, -50%) scale(1.15)" }], { ...timing, easing: EASE_OUT }));
      list.push(ring.animate([
        { opacity: 0, easing: EASE_OUT },
        { opacity: p.strength, offset: 0.3, easing: EASE_IN_OUT },
        { opacity: 0 },
      ], timing));
    }
    const out = moteFrame();
    root.querySelectorAll<HTMLElement>(".es2d-mote").forEach((el, i) => {
      const m = look.motes!;
      const { start, life } = moteTiming(look, i);
      const x0 = moteAt(look, i, start, 1, false, out).x;
      moteAt(look, i, start + life * 0.999, 1, false, out); // where it ends up
      const dx = (out.x - x0) * box.width * 0.42;
      const rise = out.rise * m.rise * RISE_PX;
      const timing = { delay: ms(start), duration: ms(life), fill: "both" as const };
      list.push(el.animate([{ transform: "translate(-50%, -50%)" }, { transform: `translate(calc(-50% + ${dx.toFixed(1)}px), calc(-50% - ${rise.toFixed(1)}px))` }], { ...timing, easing: "linear" }));
      list.push(el.animate([{ opacity: 0, easing: EASE_OUT }, { opacity: 1, offset: 0.25, easing: EASE_IN_OUT }, { opacity: 0 }], timing));
    });
    anims.current = list;
    return () => {
      for (const a of list) a.cancel();
      anims.current = [];
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // a screenshot holds it at a scene time; letting go fades the whole layer out
  useLayoutEffect(() => {
    const frozen = endSceneFrozen();
    for (const a of anims.current) {
      if (frozen == null) {
        if (a.playState === "paused") a.play();
        continue;
      }
      a.pause();
      a.currentTime = endMs(cue, frozen);
    }
  }, [cue]);
  const released = !!cue.release;
  useLayoutEffect(() => {
    const root = layer.current;
    if (!released || !root || !cue.release) return;
    const a = root.animate([{ opacity: 1 }, { opacity: 0 }], { duration: endMs(cue, cue.release.dur), easing: EASE_OUT, fill: "forwards" });
    return () => a.cancel();
  }, [released]); // eslint-disable-line react-hooks/exhaustive-deps

  const seed = moteFrame();
  return (
    <div ref={layer} className={`es2d-layer ${cue.kind}`} aria-hidden data-testid="end-scene-2d"
      style={{ left: box.left, top: box.top, width: box.width, height: box.height }}>
      <div className="es2d-shade" style={{ background: `radial-gradient(ellipse 70% 65% at 50% 48%, ${centre}, ${edge})` }} />
      {pulse && (
        <div className="es2d-pulse"
          style={{ width: box.width, height: box.height, "--es2d-color": pulse.color } as React.CSSProperties} />
      )}
      {motes.map((i) => {
        const { start } = moteTiming(look, i);
        moteAt(look, i, start, 1, false, seed); // where it starts
        const px = 5 + 3 * (seed.size - 0.7) / 0.6;
        return (
          <span key={i} className="es2d-mote"
            style={{
              left: `${50 + seed.x * 42}%`, top: `${50 + seed.z * 42}%`, width: px, height: px,
              "--es2d-color": look.motes!.color, opacity: 0,
            } as React.CSSProperties} />
        );
      })}
    </div>
  );
}
