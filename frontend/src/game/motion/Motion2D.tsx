/**
 * TABLE MOTION on the 2D table (docs/GAME_UI_MOTION_RESEARCH.md §2–5): cards fly from where they really were to where they went,
 * attackers and blockers lunge, damage and life numbers rise, the life total rolls, a library riffles when it is shuffled.
 *
 * Display only. The store has already applied each view; this reads the events between two views (tableEvents.ts) and plays
 * them over the table in a layer of its own (pointer-events: none), so nothing waits on it and every input still lands. A ghost
 * card leaves from where the old page drew the card (measured as the event arrives, before React commits the new view) and lands
 * where the new page draws it (measured on the next frame, after the commit); the real card is hidden there until it lands and is
 * always shown again (on landing, on a skip, on unmount, or after a timeout). Any click or key press finishes everything at once.
 * WAAPI on transform and opacity only (lunges use the individual ``translate`` property, which composes with a card's tap rotation).
 */
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal, flushSync } from "react-dom";
import type { GameCard, GameView } from "../../types/game";
import { GameCardFace } from "../GameCardFace";
import { onTableEvents, zoneName, type TableEvent } from "./tableEvents";
import { MOTION, motionMs, motionOn, motionPrefs, onMotionSkip } from "./timing";
import {
  cardIn, lungeOffset, planMotion, rollMs, rollValue, spotSelectors, staggerMs, transformFrom, travelMs,
  type Box, type FlightPlan, type MotionPlan, type Spot,
} from "./flights2d";
import "./motion2d.css";

const EASE_OUT = "cubic-bezier(0.23, 1, 0.32, 1)";
const EASE_IN_OUT = "cubic-bezier(0.77, 0, 0.175, 1)";
const SETTLE = 90; // the landing overshoot settles in this long (paper: 1.03, research doc §4)

declare global {
  interface Window {
    /** Test hook (e2e/motion2d-shots.spec.ts): hold every new animation at ``ms`` so a frame can be captured; null lets them run. */
    __fyodorMotion2d?: { freeze: (ms: number | null) => void; running: () => number };
  }
}

function reducedNow(): boolean {
  if (motionPrefs().reduced || document.body.classList.contains("reduced-motion")) return true;
  return typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** A duration at the player's speed; reduced motion (the setting, low graphics or the system's) shortens travel. */
function dur(ms: number, travel = true): number {
  const base = motionMs(ms, travel);
  return travel && reducedNow() && !motionPrefs().reduced ? Math.round(base * 0.4) : base;
}

function pageZoom(): number {
  const z = parseFloat(getComputedStyle(document.documentElement).zoom || "1");
  return Number.isFinite(z) && z > 0 ? z : 1;
}

function rotationOf(el: Element): number {
  const t = getComputedStyle(el).transform;
  if (!t || t === "none") return 0;
  try {
    const m = new DOMMatrixReadOnly(t);
    return Math.round((Math.atan2(m.b, m.a) * 180) / Math.PI);
  } catch {
    return 0;
  }
}

/** Where an element is drawn, in the layer's pixels, with its untransformed size (a tapped card's box is turned a quarter). */
function boxOf(el: HTMLElement, zoom: number): Box {
  const r = el.getBoundingClientRect();
  const rot = rotationOf(el);
  let w = r.width / zoom;
  let h = r.height / zoom;
  if (rot % 90 !== 0) {
    w = el.offsetWidth;
    h = el.offsetHeight;
  } else if (Math.abs(rot / 90) % 2 === 1) {
    [w, h] = [h, w];
  }
  return { cx: (r.left + r.width / 2) / zoom, cy: (r.top + r.height / 2) / zoom, w, h, rot };
}

const CARD_ELEMENTS = ".table-card, .hand-card, .command-card, .zb-card, .pile-card, .chain-thumb";

interface Found {
  el: HTMLElement;
  box: Box;
  /** The element is a card (or a pile's top card): a ghost can be the same size. */
  card: boolean;
}

function locate(spot: Spot, zoom: number): Found | null {
  for (const sel of spotSelectors(spot)) {
    const el = document.querySelector<HTMLElement>(sel);
    if (!el) continue;
    const box = boxOf(el, zoom);
    if (box.w < 2 || box.h < 2) continue; // not drawn (a narrow seat hides its hand)
    return { el, box, card: el.matches(CARD_ELEMENTS) };
  }
  return null;
}

/** The nth newest card back in a hand (another player's draw lands on it). */
function nthInHand(zone: string, nth: number, zoom: number): Found | null {
  const all = document.querySelectorAll<HTMLElement>(`[data-drop="${zone.replace(/["\\]/g, "\\$&")}"] .hand-card`);
  const el = all[all.length - 1 - nth];
  if (!el) return null;
  const box = boxOf(el, zoom);
  return box.w < 2 || box.h < 2 ? null : { el, box, card: true };
}

function point(found: Found | null): { x: number; y: number } | null {
  return found ? { x: found.box.cx, y: found.box.cy } : null;
}

/** A back in a player's sleeve (GameCardFace draws a hidden card as exactly that). */
function backOf(owner: string | null): GameCard {
  return { id: "m2d-back", owner: owner ?? "", controller: owner ?? "", zone: "", face_down: true, hidden: true };
}

interface Ghost {
  key: string;
  card: string | null;
  box: Box;
  front: GameCard | null;
  owner: string | null;
  /** It turns over on the way (out of a hidden zone face up, into one face down); flipFrames say when. */
  flip: boolean;
  frames: Keyframe[];
  flipFrames: Keyframe[] | null;
  duration: number;
  delay: number;
  /** It waits, landed, until the last card of its group lands on the same pile (so a pile never shows a gap mid-mill). */
  endDelay: number;
  /** The pile it lands on, if it lands on one. */
  pile: HTMLElement | null;
  /** The real elements hidden until it lands. */
  hides: HTMLElement[];
}

interface Riffle {
  key: string;
  box: Box;
  owner: string | null;
}

interface Float {
  key: string;
  x: number;
  y: number;
  text: string;
  tone: "loss" | "gain";
  life: boolean;
  delay: number;
}

interface Roll {
  key: string;
  player: string;
  from: number;
  to: number;
  el: HTMLElement;
  box: Box;
}

// -- the running motion, so a skip can finish it and nothing is ever left hidden --
const running = new Set<Animation>();
const finishers = new Set<() => void>();
const hiddenCount = new Map<HTMLElement, number>();
/** A ghost in the air, by key: lands it now (a newer flight of the same card starts where this one lands). */
const landNow = new Map<string, () => void>();
let frozenAt: number | null = null;

function track(a: Animation | null | undefined): void {
  if (!a) return;
  running.add(a);
  const drop = () => running.delete(a);
  a.finished.then(drop, drop);
  if (frozenAt != null) {
    a.pause();
    const t = a.effect?.getComputedTiming();
    const end = Number(t?.endTime ?? frozenAt);
    a.currentTime = Math.min(frozenAt, Number.isFinite(end) ? end : frozenAt);
  }
}

/** The real card waits unseen under its ghost: transparent, not ``visibility: hidden``, so a click on it still lands on it. */
function hide(el: HTMLElement): void {
  const n = hiddenCount.get(el) ?? 0;
  if (n === 0) el.style.opacity = "0";
  hiddenCount.set(el, n + 1);
}

function show(el: HTMLElement): void {
  const n = (hiddenCount.get(el) ?? 0) - 1;
  if (n > 0) {
    hiddenCount.set(el, n);
    return;
  }
  hiddenCount.delete(el);
  el.style.opacity = "";
}

function finishAll(): void {
  for (const a of [...running]) {
    try {
      a.finish();
    } catch {
      a.cancel();
    }
  }
  for (const f of [...finishers]) f();
}

export function Motion2D() {
  const [ghosts, setGhosts] = useState<Ghost[]>([]);
  const [riffles, setRiffles] = useState<Riffle[]>([]);
  const [floats, setFloats] = useState<Float[]>([]);
  const [rolls, setRolls] = useState<Roll[]>([]);
  const flying = useRef(new Map<string, string>()); // card id → its ghost's key
  const seq = useRef(0);

  useEffect(() => {
    const key = (p: string) => `${p}${++seq.current}`;
    const play = (events: TableEvent[], next: GameView, prev: GameView) => {
      if (!motionOn()) return;
      const plan = planMotion(events, next, prev);
      if (!plan.flights.length && !plan.appear.length && !plan.vanish.length && !plan.shuffles.length && !plan.lunges.length
        && !plan.floaters.length && !plan.lives.length) return;
      // a card already in the air lands now (where this flight starts)
      for (const f of plan.flights) if (f.id && flying.current.has(f.id)) landNow.get(flying.current.get(f.id)!)?.();
      const zoom = pageZoom();
      // where the cards leave from: the page still shows the last view
      const sources = plan.flights.map((f) => locate(f.from, zoom));
      const gone = plan.vanish.map((v) => locate({ zone: v.zone, card: v.id }, zoom));
      requestAnimationFrame(() => {
        try {
          land(plan, next, sources, gone, zoom);
        } catch (err) {
          console.error("table motion", err); // (display only)
        }
      });
    };

    const land = (plan: MotionPlan, next: GameView, sources: (Found | null)[], gone: (Found | null)[], zoom: number) => {
      const reduced = reducedNow();
      const made: Ghost[] = [];
      plan.flights.forEach((f, i) => {
        const g = flight(f, next, sources[i] ?? null, zoom, reduced, key("g"));
        if (g) made.push(g);
      });
      plan.vanish.forEach((v, i) => {
        const at = gone[i];
        if (!at) return;
        made.push({ key: key("v"), card: null, box: at.box, front: v.card, owner: v.card.owner, flip: false,
          frames: [
            { transform: `rotate(${at.box.rot}deg) scale(1)`, opacity: 1, easing: EASE_OUT },
            { transform: `rotate(${at.box.rot}deg) scale(0.95)`, opacity: 0 },
          ],
          flipFrames: null, duration: dur(160), delay: 0, endDelay: 0, pile: null, hides: [] });
      });
      const riffled: Riffle[] = [];
      for (const zone of plan.shuffles) {
        const at = locate({ zone }, zoom);
        if (at) riffled.push({ key: key("r"), box: at.box, owner: zone.split(":")[0] ?? null });
      }
      const floated: Float[] = [];
      plan.floaters.forEach((fl, i) => {
        const at = "card" in fl ? locate({ zone: next.cards[fl.card]?.zone ?? "", card: fl.card }, zoom)
          : locateHeart(fl.player, zoom);
        if (!at) return;
        const life = "player" in fl;
        // a life change rises off the top of the heart; damage from the upper part of the creature, over its art
        floated.push({ key: key("f"), x: at.box.cx, y: life ? at.box.cy - at.box.h * 0.5 : at.box.cy - at.box.h * 0.18, text: fl.text,
          tone: fl.tone, life, delay: Math.round(i * staggerMs(plan.floaters.length)) });
      });
      const rolled: Roll[] = [];
      for (const l of plan.lives) {
        const el = document.querySelector<HTMLElement>(`[data-testid="life-${l.player.replace(/["\\]/g, "\\$&")}"]`);
        if (!el) continue;
        const box = boxOf(el, zoom);
        if (box.w < 1) continue;
        rolled.push({ key: key("l"), player: l.player, from: l.from, to: l.to, el, box });
      }
      // cards landing on one pile all finish with its last one (the pile's real top card waits hidden under them until then)
      const ends = new Map<HTMLElement, number>();
      for (const g of made) if (g.pile) ends.set(g.pile, Math.max(ends.get(g.pile) ?? 0, g.delay + g.duration));
      for (const g of made) if (g.pile) g.endDelay = (ends.get(g.pile) ?? 0) - (g.delay + g.duration);
      if (made.length || riffled.length || floated.length || rolled.length) {
        for (const g of made) {
          for (const el of g.hides) hide(el);
          if (g.card) flying.current.set(g.card, g.key);
        }
        try {
          flushSync(() => {
            if (made.length) setGhosts((all) => [...all, ...made]);
            if (riffled.length) setRiffles((all) => [...all, ...riffled]);
            if (floated.length) setFloats((all) => [...all, ...floated]);
            if (rolled.length) setRolls((all) => [...all.filter((r) => !rolled.some((n) => n.player === r.player)), ...rolled]);
          });
        } catch (err) {
          for (const g of made) for (const el of g.hides) show(el); // (never leave a real card hidden)
          throw err;
        }
      }
      appear(plan.appear, next, zoom, reduced);
      if (!reduced) lunge(plan.lunges, next, zoom);
    };

    /** One card's flight: measured and set up so it starts on this frame, before the page paints the new view. */
    const flight = (f: FlightPlan, next: GameView, src: Found | null, zoom: number, reduced: boolean, k: string): Ghost | null => {
      if (!src) return null;
      let dst: Found | null = null;
      if (f.nth != null && zoneName(f.to.zone) === "hand") dst = nthInHand(f.to.zone, f.nth, zoom);
      dst ??= locate(f.to, zoom);
      if (!dst) return null;
      const bfH = Number(document.querySelector<HTMLElement>(`[data-drop="${f.to.zone}"]`)?.dataset.cardh ?? NaN);
      const to = dst.card ? dst.box : cardIn(dst.box, Number.isFinite(bfH) ? bfH : src.card ? src.box.h : undefined);
      const from = src.card ? src.box : cardIn(src.box, to.h);
      const hides: HTMLElement[] = [];
      if (dst.card && f.id) {
        // the real card waits under the ghost: its own element, or the pile it tops
        const own = dst.el.closest("[data-card-id]")?.getAttribute("data-card-id") === f.id;
        const zone = next.zones[f.to.zone];
        const tops = Array.isArray(zone) && zone[zone.length - 1] === f.id && dst.el.matches(".pile-card");
        if (own || tops) hides.push(dst.el);
      } else if (f.nth != null && dst.el.matches(".hand-card")) {
        hides.push(dst.el);
      }
      const settle = reduced ? 0 : SETTLE;
      const base = f.kind === "draw" ? MOTION.drawTravel : MOTION.cardTravel;
      const travel = dur(travelMs(base, Math.hypot(from.cx - to.cx, from.cy - to.cy), settle));
      const settleMs = dur(settle);
      const duration = travel + settleMs;
      const arrive = duration > 0 ? travel / duration : 1;
      const land = `translate(0px, 0px) rotate(${to.rot}deg) scale(1)`;
      const startScale = f.emerge ? 0.6 : 1;
      const fadeIn = f.emerge || !src.card;
      const fadeOut = !dst.card;
      const frames: Keyframe[] = settle
        ? [
          { transform: transformFrom(from, to, startScale), opacity: fadeIn ? 0 : 1, easing: EASE_OUT },
          ...(fadeIn ? [{ opacity: 1, offset: arrive * 0.3 }] : []),
          { transform: `translate(0px, 0px) rotate(${to.rot}deg) scale(1.03)`, opacity: fadeOut ? 0.6 : 1, offset: arrive, easing: EASE_OUT },
          { transform: land, opacity: fadeOut ? 0 : 1 },
        ]
        : [
          { transform: transformFrom(from, to, startScale), opacity: fadeIn ? 0 : 1, easing: EASE_OUT },
          { transform: land, opacity: fadeOut ? 0 : 1 },
        ];
      const front = f.end ?? f.start;
      const flip = !!front && !(f.start && f.end);
      const first = f.start || !front ? "front" : "back";
      // the turn happens on the way in: it leaves the hidden zone face down and is face up as it lands (or the reverse)
      const turnAt = reduced ? [0.5, 0.5] : first === "back" ? [arrive * 0.3, arrive * 0.95] : [arrive * 0.15, arrive * 0.75];
      const flipFrames: Keyframe[] | null = !flip ? null : first === "back"
        ? [{ transform: "rotateY(180deg)" }, { transform: "rotateY(180deg)", offset: turnAt[0], easing: EASE_IN_OUT }, { transform: "rotateY(0deg)", offset: turnAt[1] }, { transform: "rotateY(0deg)" }]
        : [{ transform: "rotateY(0deg)" }, { transform: "rotateY(0deg)", offset: turnAt[0], easing: EASE_IN_OUT }, { transform: "rotateY(180deg)", offset: turnAt[1] }, { transform: "rotateY(180deg)" }];
      const pile = dst.el.matches(".pile-card") ? dst.el : null;
      return { key: k, card: f.id, box: to, front, owner: f.owner, flip, frames, flipFrames, duration, delay: dur(f.delay), endDelay: 0, pile, hides };
    };

    const locateHeart = (player: string, zoom: number): Found | null => {
      const el = document.querySelector<HTMLElement>(`[data-testid="heart-${player.replace(/["\\]/g, "\\$&")}"]`)
        ?? document.querySelector<HTMLElement>(`.t3d-seat[data-player-id="${player.replace(/["\\]/g, "\\$&")}"]`);
      if (!el) return null;
      const box = boxOf(el, zoom);
      return box.w < 1 ? null : { el, box, card: false };
    };

    /** A token or copy made on the table settles in where it is. */
    const appear = (ids: string[], next: GameView, zoom: number, reduced: boolean) => {
      const gap = staggerMs(Math.min(ids.length, MOTION.maxFlights));
      ids.slice(0, MOTION.maxFlights).forEach((id, i) => {
        const at = locate({ zone: next.cards[id]?.zone ?? "", card: id }, zoom);
        if (!at || !at.card) return;
        const frames: Keyframe[] = reduced ? [{ opacity: 0 }, { opacity: 1 }] : [{ opacity: 0, scale: "0.95" }, { opacity: 1, scale: "1" }];
        track(at.el.animate(frames, { duration: dur(200, false), delay: dur(i * gap), easing: EASE_OUT, fill: "backwards" }));
      });
    };

    /** Attackers step toward what they attack, blockers toward their attacker, and come back (the layout never changes). */
    const lunge = (lunges: MotionPlan["lunges"], next: GameView, zoom: number) => {
      const gap = staggerMs(lunges.length);
      lunges.forEach((l, i) => {
        const at = locate({ zone: next.cards[l.id]?.zone ?? "", card: l.id }, zoom);
        if (!at || !at.card) return;
        const target = "player" in l.toward
          ? point(locate({ zone: `${l.toward.player}:battlefield` }, zoom)) ?? point(locateHeart(l.toward.player, zoom))
          : point(locate({ zone: next.cards[l.toward.card]?.zone ?? "", card: l.toward.card }, zoom));
        if (!target) return;
        const { dx, dy } = lungeOffset({ x: at.box.cx, y: at.box.cy }, target, at.box.h);
        if (!dx && !dy) return;
        const out = dur(MOTION.lunge);
        const back = dur(Math.round(MOTION.lunge * 0.6)); // (the way back is quicker: exits 30–50% shorter, research doc §4)
        track(at.el.animate(
          [
            { translate: "0px 0px", easing: EASE_OUT },
            { translate: `${dx}px ${dy}px`, offset: out / (out + back), easing: EASE_IN_OUT },
            { translate: "0px 0px" },
          ],
          { duration: out + back, delay: dur(i * gap) },
        ));
      });
    };

    const offEvents = onTableEvents(play);
    const offSkip = onMotionSkip(finishAll);
    const flyingNow = flying.current;
    window.__fyodorMotion2d = {
      freeze: (ms) => {
        frozenAt = ms;
        for (const a of running) {
          if (ms == null) a.play();
          else {
            a.pause();
            a.currentTime = Math.min(ms, Number(a.effect?.getComputedTiming().endTime ?? ms));
          }
        }
      },
      running: () => running.size,
    };
    return () => {
      offEvents();
      offSkip();
      finishAll();
      for (const el of [...hiddenCount.keys()]) {
        hiddenCount.delete(el);
        el.style.opacity = "";
      }
      flyingNow.clear();
      delete window.__fyodorMotion2d;
    };
  }, []);

  const doneGhost = (g: Ghost) => {
    for (const el of g.hides) show(el);
    if (g.card && flying.current.get(g.card) === g.key) flying.current.delete(g.card);
    setGhosts((all) => all.filter((x) => x.key !== g.key));
  };

  return createPortal(
    <div className="m2d-layer" aria-hidden data-testid="motion2d">
      {ghosts.map((g) => <GhostCard key={g.key} ghost={g} onDone={doneGhost} />)}
      {riffles.map((r) => <RiffleBacks key={r.key} riffle={r} onDone={() => setRiffles((all) => all.filter((x) => x.key !== r.key))} />)}
      {floats.map((f) => <Floater key={f.key} float={f} onDone={() => setFloats((all) => all.filter((x) => x.key !== f.key))} />)}
      {rolls.map((r) => <LifeRoll key={r.key} roll={r} onDone={() => setRolls((all) => all.filter((x) => x.key !== r.key))} />)}
    </div>,
    document.body,
  );
}

/** Runs ``onDone`` once: when the animations end or are finished by a skip, when the ghost goes, or after a timeout (never stuck). */
function useOnce(onDone: () => void, within: number): () => void {
  const done = useRef(false);
  const latest = useRef(onDone);
  latest.current = onDone;
  const fire = useRef(() => {
    if (done.current) return;
    done.current = true;
    latest.current();
  }).current;
  useEffect(() => {
    const t = window.setTimeout(() => frozenAt == null && fire(), within + 1500);
    return () => window.clearTimeout(t);
  }, [fire, within]);
  return fire;
}

function GhostCard({ ghost, onDone }: { ghost: Ghost; onDone: (g: Ghost) => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const flipRef = useRef<HTMLDivElement>(null);
  const done = useOnce(() => onDone(ghost), ghost.delay + ghost.duration + ghost.endDelay);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return done();
    let alive = true; // (a cleanup, e.g. StrictMode's second run, cancels without landing: the fallback timeout still lands it)
    const timing: KeyframeAnimationOptions = { duration: ghost.duration, delay: ghost.delay, endDelay: ghost.endDelay, fill: "both" };
    const a = el.animate(ghost.frames, timing);
    const b = ghost.flipFrames && flipRef.current ? flipRef.current.animate(ghost.flipFrames, timing) : null;
    track(a);
    track(b);
    const land = () => {
      if (!alive) return;
      b?.finish();
      done();
    };
    a.finished.then(land, () => {});
    landNow.set(ghost.key, () => a.finish());
    return () => {
      alive = false;
      landNow.delete(ghost.key);
      a.cancel();
      b?.cancel();
    };
  }, []);
  const { box } = ghost;
  return (
    <div ref={ref} className="m2d-ghost" style={{ left: box.cx - box.w / 2, top: box.cy - box.h / 2, width: box.w, height: box.h }}>
      <div ref={flipRef} className="m2d-flip">
        {ghost.front && <div className="m2d-face"><GameCardFace card={ghost.front} /></div>}
        {(!ghost.front || ghost.flip) && (
          <div className={`m2d-face ${ghost.flip ? "m2d-back" : ""}`}><GameCardFace card={backOf(ghost.owner)} /></div>
        )}
      </div>
    </div>
  );
}

/** A shuffle: the top of the library splits in two and riffles back together (≤ MOTION.shuffle). */
function RiffleBacks({ riffle, onDone }: { riffle: Riffle; onDone: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const total = dur(MOTION.shuffle);
  const done = useOnce(onDone, total);
  useLayoutEffect(() => {
    const cards = ref.current ? [...ref.current.children] as HTMLElement[] : [];
    if (!cards.length) return done();
    const reduced = reducedNow();
    const spread = riffle.box.w * (reduced ? 0.12 : 0.36);
    const rise = riffle.box.h * (reduced ? 0 : 0.1);
    const tilt = reduced ? 0 : 6;
    const each = Math.round(total * 0.82);
    const step = Math.round((total - each) / Math.max(1, cards.length - 1));
    const anims = cards.map((el, i) => {
      const side = i % 2 === 0 ? -1 : 1;
      const lift = -(i * 1.5);
      return el.animate(
        [
          { transform: `translate(0px, ${lift}px) rotate(0deg)`, easing: EASE_OUT },
          { transform: `translate(${side * spread}px, ${lift - rise}px) rotate(${side * tilt}deg)`, offset: 0.42, easing: EASE_IN_OUT },
          { transform: `translate(0px, ${lift}px) rotate(0deg)` },
        ],
        { duration: each, delay: i * step, fill: "both" },
      );
    });
    anims.forEach(track);
    let alive = true;
    Promise.all(anims.map((a) => a.finished)).then(() => alive && done(), () => {});
    return () => {
      alive = false;
      anims.forEach((a) => a.cancel());
    };
  }, []);
  const { box } = riffle;
  const back = backOf(riffle.owner);
  return (
    <div ref={ref} className="m2d-riffle" style={{ left: box.cx - box.w / 2, top: box.cy - box.h / 2, width: box.w, height: box.h }}>
      {[0, 1, 2, 3].map((i) => <div key={i} className="m2d-face"><GameCardFace card={back} /></div>)}
    </div>
  );
}

/** "−3" over a creature, "+5" by a life total: it rises a little and fades (reduced motion: it only fades). */
function Floater({ float, onDone }: { float: Float; onDone: () => void }) {
  const ref = useRef<HTMLSpanElement>(null);
  const duration = dur(MOTION.floater, false);
  const done = useOnce(onDone, float.delay + duration);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return done();
    const still = reducedNow();
    const at = (y: number, s = 1) => (still ? "translate(-50%, -50%)" : `translate(-50%, -50%) translateY(${y}px) scale(${s})`);
    const a = el.animate(
      [
        { transform: at(6, 0.96), opacity: 0, easing: EASE_OUT },
        { transform: at(-4), opacity: 1, offset: 0.14, easing: EASE_OUT },
        { transform: at(-14), opacity: 1, offset: 0.62, easing: EASE_OUT },
        { transform: at(-24), opacity: 0 },
      ],
      { duration, delay: float.delay, fill: "both" },
    );
    track(a);
    let alive = true;
    a.finished.then(() => alive && done(), () => {});
    return () => {
      alive = false;
      a.cancel();
    };
  }, []);
  return (
    <span ref={ref} className={`m2d-float ${float.tone} ${float.life ? "life" : ""}`} style={{ left: float.x, top: float.y }}>
      {float.text}
    </span>
  );
}

/** The life total counts to its new value (300–600 ms) over the real number, which waits hidden underneath. */
function LifeRoll({ roll, onDone }: { roll: Roll; onDone: () => void }) {
  const ref = useRef<HTMLSpanElement>(null);
  const duration = dur(rollMs(roll.to - roll.from), false);
  const done = useOnce(onDone, duration);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return done();
    const real = roll.el;
    const cs = getComputedStyle(real);
    Object.assign(el.style, { font: cs.font, color: cs.color, letterSpacing: cs.letterSpacing, textShadow: cs.textShadow, fontVariantNumeric: "tabular-nums" });
    el.textContent = String(roll.from);
    hide(real);
    let raf = 0;
    let over = false;
    const t0 = performance.now();
    const stop = () => {
      if (over) return false;
      over = true;
      cancelAnimationFrame(raf);
      finishers.delete(finish);
      show(real);
      return true;
    };
    const finish = () => {
      if (!stop()) return;
      el.textContent = String(roll.to);
      done();
    };
    const tick = (now: number) => {
      const t = frozenAt != null ? Math.min(1, frozenAt / Math.max(1, duration)) : Math.min(1, (now - t0) / Math.max(1, duration));
      const eased = 1 - (1 - t) ** 4; // (a strong ease-out: the count moves at once and settles on the total)
      el.textContent = String(rollValue(roll.from, roll.to, eased));
      if (t >= 1) finish();
      else raf = requestAnimationFrame(tick);
    };
    finishers.add(finish);
    raf = requestAnimationFrame(tick);
    // a small punch as it starts counting (paper weight: no bounce); not with reduced motion
    const punch = reducedNow() ? null : el.animate([{ transform: "scale(1.15)", easing: EASE_OUT }, { transform: "scale(1)" }], { duration: dur(240) });
    track(punch);
    return () => {
      stop(); // (unmounted or StrictMode's second run: the real number is shown again; nothing is left hidden)
      punch?.cancel();
    };
  }, []);
  const { box } = roll;
  return <span ref={ref} className="m2d-roll" style={{ left: box.cx - box.w / 2, top: box.cy - box.h / 2, width: box.w, height: box.h }} />;
}
