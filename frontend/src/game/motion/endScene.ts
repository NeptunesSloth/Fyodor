/**
 * END-OF-GAME TABLE SCENE (docs/3D_DIRECTION.md §7a): while the result spotlight shows, the table itself reacts. It dims
 * and takes a slight colour cast, the camera eases a few percent toward the board (or away from it), one light pulse
 * crosses the battlefield and a handful of motes rise. Victory is warm gold, defeat a restrained dark red, a draw a
 * neutral silver; the eliminated player alone gets a shorter, quieter dark version. It is not a cinematic: 1–3 s,
 * then the table is exactly as it was and the result panel takes over.
 *
 * This file is the pure half (unit-tested) plus the one cue both tables follow: GameNight starts the scene
 * (``playEndScene``) from the server's result, the 3D table plays it in its frame loop (table3d/endScene3d.ts) and the
 * 2D table with WAAPI over the table (EndScene2D.tsx).
 *
 * Presentation only: nothing here reads or changes game state, and nothing depends on sound. Table input is held
 * back only while the scene holds (never past ``MAX_HOLD``), and any click or key press ends it at once
 * (timing.ts ``onMotionSkip``). Reduced motion keeps the dim (a fade) and the result text, and drops the camera,
 * the pulse and the motes.
 */
import { easeInOut, easeOut } from "../../table3d/flights3d";
import { play, type SoundName } from "../sound";
import { motionOn, motionPrefs, onMotionSkip } from "./timing";

const clock = (): number => (typeof performance !== "undefined" ? performance.now() : Date.now());

/** What the result spotlight says to this viewer. */
export type ResultWord = "victory" | "defeat" | "draw" | "none" | "winner";
/** How the table reacts for this viewer: ``watch`` is someone else's win seen from outside the game (a spectator). */
export type EndKind = "victory" | "defeat" | "draw" | "watch" | "eliminated";

export interface EndPulse {
  /** The pulse's colour: light added to the table (``light``), or a shadow passing over it. */
  color: string;
  light: boolean;
  /** When it starts and how long it takes to cross the table (ms at 1×). */
  at: number;
  dur: number;
  /** Its peak opacity. */
  strength: number;
}

export interface EndMotes {
  count: number;
  color: string;
  /** The first mote appears ``at`` ms in, the rest ``stagger`` ms apart; each lives about ``life`` ms. */
  at: number;
  stagger: number;
  life: number;
  /** How far a mote rises over its life (in card lengths on the 3D table; the 2D table scales it to pixels). */
  rise: number;
}

export interface EndLook {
  /** How long the scene holds, with input held back (ms at 1×): the spotlight's length. */
  hold: number;
  /** How long the table takes to settle back afterward. */
  release: number;
  /** The table's light at full dim (1 = unchanged), its colour cast (multiplied, linear 0–1) and how long it takes to settle in. */
  dim: number;
  tint: readonly [number, number, number];
  dimIn: number;
  pulse: EndPulse | null;
  motes: EndMotes | null;
  /** The camera: a fraction of its distance toward (+) or away from (−) what it looks at, a little rise, and how long it takes. */
  push: number;
  lift: number;
  camIn: number;
  /** The short sting that goes with it (game/sound.ts; silent when sound is off). */
  sting: SoundName;
}

/** Each kind's beats (docs/3D_DIRECTION.md §7a table). Durations are at 1×; the player's animation speed scales them. */
export const END_LOOKS: Record<EndKind, EndLook> = {
  victory: {
    hold: 2600, release: 600, dim: 0.8, tint: [1, 0.93, 0.8], dimIn: 450,
    pulse: { color: "#e2b866", light: true, at: 180, dur: 1000, strength: 0.22 },
    motes: { count: 14, color: "#e9c47c", at: 320, stagger: 50, life: 1300, rise: 1.1 },
    push: 0.03, lift: 0.01, camIn: 1800, sting: "victory",
  },
  defeat: {
    hold: 2400, release: 600, dim: 0.7, tint: [1, 0.86, 0.83], dimIn: 500,
    pulse: { color: "#5a140c", light: false, at: 200, dur: 900, strength: 0.5 },
    motes: { count: 9, color: "#b4462c", at: 380, stagger: 70, life: 1200, rise: 0.8 },
    push: -0.03, lift: 0, camIn: 1700, sting: "defeat",
  },
  draw: {
    hold: 2200, release: 500, dim: 0.84, tint: [0.93, 0.96, 1], dimIn: 400,
    pulse: { color: "#c9ced6", light: true, at: 180, dur: 850, strength: 0.15 },
    motes: { count: 7, color: "#d5dae1", at: 320, stagger: 60, life: 1200, rise: 0.7 },
    push: 0.006, lift: 0, camIn: 1500, sting: "drawn",
  },
  watch: {
    hold: 2600, release: 600, dim: 0.86, tint: [1, 0.97, 0.92], dimIn: 450,
    pulse: { color: "#d6c08f", light: true, at: 180, dur: 950, strength: 0.14 },
    motes: { count: 6, color: "#dcc796", at: 320, stagger: 60, life: 1300, rise: 0.8 },
    push: 0, lift: 0, camIn: 1500, sting: "drawn",
  },
  eliminated: {
    hold: 1600, release: 400, dim: 0.76, tint: [0.96, 0.9, 0.9], dimIn: 300,
    pulse: { color: "#1a0a08", light: false, at: 120, dur: 650, strength: 0.4 },
    motes: null,
    push: -0.02, lift: 0, camIn: 1100, sting: "eliminated",
  },
};

/** The spotlight's hold for a result with no table reaction ("no result"). */
const PLAIN_HOLD = 2600;
/** Input is never held back longer than this (ms, real time), whatever the animation speed. */
export const MAX_HOLD = 3000;
/** A skipped scene settles back this quickly (ms at 1×). */
export const SKIP_RELEASE = 180;

/** What the spotlight says to this viewer, from the server's result: their own win or loss, or someone else's win. */
export function resultWord(result: { result_type: string; winners: string[] }, me: string, seated: boolean): ResultWord {
  if (result.result_type === "draw") return "draw";
  if (result.result_type === "no_result") return "none";
  if (!seated) return "winner";
  return result.winners.includes(me) ? "victory" : "defeat";
}

/** The table's reaction to that word (null: none, for a game that ended with no result). */
export function endKindFor(word: ResultWord): EndKind | null {
  return word === "none" ? null : word === "winner" ? "watch" : word;
}

/** How long the scene holds (real ms): the kind's beat at the player's speed, never past ``MAX_HOLD``. */
export function holdMs(kind: EndKind | null, speed: number): number {
  const base = kind ? END_LOOKS[kind].hold : PLAIN_HOLD;
  return Math.min(MAX_HOLD, Math.round(base / (speed > 0 ? speed : 1)));
}

/** The scene at one moment (scene time ``t``, ms at 1×), filled into ``out`` (no allocation per frame). */
export interface EndFrame {
  /** 0–1: how much of the dim and colour cast is on. */
  dim: number;
  /** The camera's push (fraction of its distance: + toward the board, − away) and rise. */
  push: number;
  lift: number;
  /** The pulse: how far it has spread (0–1) and how strong it is now (0: not showing). */
  spread: number;
  pulse: number;
  /** 0–1: how much of the scene is still on (1 until it is released, then down to 0). */
  fade: number;
  /** Settled back: the table is as it was, and everything can be hidden. */
  done: boolean;
}

export const endFrame = (): EndFrame => ({ dim: 0, push: 0, lift: 0, spread: 0, pulse: 0, fade: 1, done: false });

const clamp01 = (x: number) => (x <= 0 ? 0 : x >= 1 ? 1 : x);

/**
 * The scene at ``t`` (ms at 1× since it started). ``release``: when the scene let go and how long it takes to settle
 * back (null while it holds). Reduced motion keeps only the dim.
 */
export function endAt(look: EndLook, t: number, release: { at: number; dur: number } | null, reduced: boolean, out: EndFrame): EndFrame {
  const r = release ? clamp01((t - release.at) / Math.max(1, release.dur)) : 0;
  const fade = 1 - easeOut(r); // the dim, the pulse and the motes fade out (an exit)
  const back = 1 - easeInOut(r); // the camera glides back (a move on screen)
  out.fade = fade;
  out.done = !!release && r >= 1;
  out.dim = easeOut(clamp01(t / Math.max(1, look.dimIn))) * fade;
  const cam = reduced ? 0 : easeInOut(clamp01(t / Math.max(1, look.camIn))) * back;
  out.push = cam ? look.push * cam : 0;
  out.lift = cam ? look.lift * cam : 0;
  out.spread = 0;
  out.pulse = 0;
  const p = look.pulse;
  if (p && !reduced) {
    const q = (t - p.at) / p.dur;
    if (q > 0 && q < 1) {
      out.spread = easeOut(q);
      // up quickly, then a long falloff as it crosses the table
      out.pulse = p.strength * (q < 0.3 ? easeOut(q / 0.3) : 1 - easeInOut((q - 0.3) / 0.7)) * fade;
    }
  }
  return out;
}

/** One mote at one moment: where it is across the table (−1…1 each way), how high it has risen (0–1 of the rise), how visible. */
export interface MoteFrame { x: number; z: number; rise: number; alpha: number; size: number }
export const moteFrame = (): MoteFrame => ({ x: 0, z: 0, rise: 0, alpha: 0, size: 1 });

/** A repeatable 0–1 value for mote ``i`` (the same scene looks the same on every screen and in every test). */
export function hash01(i: number, salt: number): number {
  const s = Math.sin(i * 12.9898 + salt * 78.233) * 43758.5453;
  return s - Math.floor(s);
}

/** When mote ``i`` appears and how long it lives (ms at 1×). */
export function moteTiming(look: EndLook, i: number): { start: number; life: number } {
  const m = look.motes;
  if (!m) return { start: 0, life: 0 };
  return { start: m.at + i * m.stagger, life: m.life * (0.8 + 0.4 * hash01(i, 5)) };
}

/**
 * Mote ``i`` at ``t``: spread over the battlefields (never on the very middle, where the result's word sits), rising
 * at a steady pace, in quickly and out slowly. Reduced motion, or a mote not yet born or already gone: alpha 0.
 */
export function moteAt(look: EndLook, i: number, t: number, fade: number, reduced: boolean, out: MoteFrame): MoteFrame {
  out.alpha = 0;
  const m = look.motes;
  if (!m || reduced || i >= m.count) return out;
  const q = (t - (m.at + i * m.stagger)) / (m.life * (0.8 + 0.4 * hash01(i, 5))); // (moteTiming, without allocating)
  const angle = hash01(i, 1) * Math.PI * 2;
  const radius = 0.3 + 0.62 * Math.sqrt(hash01(i, 2));
  out.x = Math.cos(angle) * radius + (hash01(i, 4) - 0.5) * 0.08 * clamp01(q);
  out.z = Math.sin(angle) * radius;
  out.size = 0.7 + 0.6 * hash01(i, 3);
  out.rise = clamp01(q) * (0.6 + 0.4 * hash01(i, 6)); // constant motion: linear
  if (q <= 0 || q >= 1) return out;
  out.alpha = (q < 0.25 ? easeOut(q / 0.25) : 1 - easeInOut((q - 0.25) / 0.75)) * fade;
  return out;
}

// --------------------------------------------------------------------------- the cue both tables follow

/** The scene now playing: its kind and look, when it started (performance.now) and at what speed, and when it let go. */
export interface EndCue {
  id: number;
  kind: EndKind;
  look: EndLook;
  t0: number;
  speed: number;
  /** Scene time it let go at, and how long it takes to settle back (ms at 1×); null while it holds. */
  release: { at: number; dur: number } | null;
}

type Listener = (cue: EndCue | null) => void;
const listeners = new Set<Listener>();
let cue: EndCue | null = null;
let nextId = 1;
/** Tests and screenshots: hold every scene at this scene time (ms at 1×); null runs live. */
let frozen: number | null = null;

function notify(): void {
  for (const l of [...listeners]) {
    try {
      l(cue);
    } catch {
      /* (display only) */
    }
  }
}

/** Follow the cue (called at once with the current one). Returns the unsubscribe. */
export function onEndScene(listener: Listener): () => void {
  listeners.add(listener);
  listener(cue);
  return () => listeners.delete(listener);
}

/** Scene time now (ms at 1×): frozen for a screenshot, or the real time since it started at its speed. */
export function endSceneTime(c: EndCue, now: number): number {
  return frozen ?? (now - c.t0) * c.speed;
}

/** The scene time screenshots hold the scene at (null: live). */
export function endSceneFrozen(): number | null {
  return frozen;
}

export function freezeEndScene(ms: number | null): void {
  frozen = ms;
  if (cue) {
    cue = { ...cue }; // a new object, so a React follower re-renders
    notify();
  }
}

/** Let the scene go: the table settles back over the kind's release (or quickly, for a skip), then the cue clears. */
function release(id: number, quick: boolean, now: number): void {
  if (!cue || cue.id !== id || cue.release) return;
  const dur = quick ? SKIP_RELEASE : cue.look.release;
  cue = { ...cue, release: { at: endSceneTime(cue, now), dur } };
  notify();
  // a frozen scene lets go at once when it is released (the screenshot spec unfreezes after)
  const left = frozen != null ? 0 : dur / cue.speed;
  setTimeout(() => {
    if (cue?.id === id) {
      cue = null;
      notify();
    }
  }, left + 50);
}

export interface EndPlay {
  /** End it now (a click on the spotlight, a skip, unmounting, the result taken back): the table settles back quickly. */
  stop(): void;
}

/**
 * Start the scene for ``kind`` (null: no table reaction, only the hold), play its sting, and hold until it ends: after
 * ``holdMs`` (unless frozen), or at once on a key press. While it holds, no key reaches the table underneath (its
 * shortcuts, the camera); the spotlight over the table takes the pointer, and its click calls ``stop``. Any click or key
 * (timing.ts ``onMotionSkip``) settles the table back at once. ``onEnd`` runs once when the scene ends by itself or by a
 * key, not when ``stop`` is called.
 */
export function playEndScene(kind: EndKind | null, onEnd: () => void): EndPlay {
  const { speed } = motionPrefs();
  let id = 0;
  if (kind && motionOn()) {
    id = nextId++;
    cue = { id, kind, look: END_LOOKS[kind], t0: clock(), speed, release: null };
    notify();
  }
  let over = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  // the sting lands with the light pulse (its impact frame), not before it; a scene already over stays silent
  const sting = kind ? setTimeout(() => {
    if (!over) play(END_LOOKS[kind].sting);
  }, Math.round((END_LOOKS[kind].pulse?.at ?? 0) / speed)) : undefined;
  const onKey = (e: KeyboardEvent) => {
    e.stopPropagation();
    if (e.key === " " || e.key === "Escape" || e.key === "Enter") e.preventDefault();
    finish(true, true);
  };
  const unskip = onMotionSkip(() => {
    if (id) release(id, true, clock());
  });
  const finish = (quick: boolean, tell: boolean) => {
    if (over) return;
    over = true;
    if (timer !== undefined) clearTimeout(timer);
    if (sting !== undefined) clearTimeout(sting);
    unskip();
    if (typeof window !== "undefined") window.removeEventListener("keydown", onKey, true);
    if (id) release(id, quick, clock());
    if (tell) onEnd();
  };
  const tick = () => {
    // a frozen scene (a screenshot) waits; otherwise it lets go on time
    if (frozen != null) timer = setTimeout(tick, 200);
    else finish(false, true);
  };
  timer = setTimeout(tick, holdMs(kind, speed));
  if (typeof window !== "undefined") window.addEventListener("keydown", onKey, true);
  return { stop: () => finish(true, false) };
}

/** A duration of the scene in real ms at the player's speed (the 2D table's WAAPI timings). */
export function endMs(c: EndCue, ms: number): number {
  return Math.round(ms / (c.speed > 0 ? c.speed : 1));
}

declare global {
  interface Window {
    /** Test hook (e2e/endscene-shots.spec.ts): hold the end scene at a scene time (ms at 1×), and what is playing. */
    __fyodorEndScene?: { freeze: (ms: number | null) => void; state: () => { kind: EndKind; released: boolean } | null };
  }
}
if (typeof window !== "undefined") {
  window.__fyodorEndScene = {
    freeze: freezeEndScene,
    state: () => (cue ? { kind: cue.kind, released: !!cue.release } : null),
  };
}
