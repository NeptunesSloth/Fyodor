/**
 * -- day and night (CR 726) -- the 3D room's light at night: the key light turns a cool moonlit blue and a little dimmer, the
 * sky fill cools, the warm pool over the table dims and the back rim (moonlight through the window) lifts. Day is the plane's
 * own light. A change eases over about a second (ease-in-out, the player's animation speed); reduced motion, a table that loads
 * already at night, a rebuilt room and a skip (any click or key) snap straight to it. Only the four main lights change: no
 * new light, shadow or pass, and nothing is done on a frame while the light is settled. The server decides day and night;
 * this only shows it.
 */
import * as THREE from "three";
import type { Environment } from "./environment";
import { motionMs, motionOn, onMotionSkip } from "../game/motion/timing";

export type DayNightMode = "day" | "night" | null;

/** How long the light takes to turn (ms at 1× speed). */
export const DAY_NIGHT_MS = 1000;

/** Night's light. Colours are mixed toward these by the given amount; intensities are multiplied (floors keep cards readable). */
export const NIGHT = {
  moon: "#a4b8e8", // the key light's colour at night
  sky: "#7d90c2", // the hemisphere's sky at night
  keyMix: 0.55,
  skyMix: 0.5,
  rimMix: 0.65,
  key: 0.8,
  hemi: 0.85,
  pool: 0.6,
  rim: 1.3,
} as const;

/** The cubic ease-in-out of an on-screen morph (docs/GAME_UI_MOTION_RESEARCH.md §3), t in [0, 1]. */
export function easeInOut(t: number): number {
  const x = Math.min(1, Math.max(0, t));
  return x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2;
}

/** An intensity at night mix ``f`` (0 = day, 1 = night) for a night multiplier ``k``. */
export function nightIntensity(base: number, k: number, f: number): number {
  return base * (1 + (k - 1) * f);
}

/** Where the mix is ``now`` into a turn from ``from`` to ``to`` that started at ``start`` and lasts ``ms``. */
export function mixAt(from: number, to: number, start: number, ms: number, now: number): number {
  if (ms <= 0) return to;
  const p = (now - start) / ms;
  return p >= 1 ? to : from + (to - from) * easeInOut(p);
}

type Lights = Environment["lights"];
interface Base { key: THREE.Color; sky: THREE.Color; rim: THREE.Color; keyI: number; hemiI: number; poolI: number; rimI: number }

const MOON = new THREE.Color(NIGHT.moon);
const SKY = new THREE.Color(NIGHT.sky);

export class DayNightLight {
  private lights: Lights | null = null;
  private base: Base | null = null;
  private f = 0;
  private from = 0;
  private to = 0;
  private start = 0;
  private ms = 0;
  private seen = false;
  private unskip: (() => void) | null = null;

  /** Whether the light is still turning (the loop calls ``update`` only then). */
  get active(): boolean {
    return this.f !== this.to;
  }

  /** A (re)built room: remember its day light and show the current mode at once. */
  attach(env: Environment | null): void {
    this.lights = env?.lights ?? null;
    const l = this.lights;
    this.base = l ? { key: l.key.color.clone(), sky: l.hemi.color.clone(), rim: l.rim.color.clone(), keyI: l.key.intensity, hemiI: l.hemi.intensity, poolI: l.pool.intensity, rimI: l.rim.intensity } : null;
    this.f = this.to;
    this.apply();
  }

  /** The table's mode from the view: the first one (a table loading at night) snaps, a change turns at the table's speed. */
  show(mode: DayNightMode): void {
    const first = !this.seen;
    this.seen = true;
    const still = first || !motionOn() || (typeof document !== "undefined" && document.body.classList.contains("reduced-motion"));
    this.set(mode, still ? 0 : motionMs(DAY_NIGHT_MS, false), performance.now());
  }

  /** The table's mode; ``ms`` 0 snaps (reduced motion, a first view). */
  set(mode: DayNightMode, ms: number, now: number): void {
    const target = mode === "night" ? 1 : 0;
    if (target === this.to) return;
    this.from = this.f;
    this.to = target;
    this.start = now;
    this.ms = ms;
    if (ms <= 0) this.finish();
    else if (!this.unskip) this.unskip = onMotionSkip(() => this.finish());
  }

  update(now: number, reduced: boolean): void {
    if (!this.active) return;
    this.f = reduced ? this.to : mixAt(this.from, this.to, this.start, this.ms, now);
    this.apply();
    if (!this.active) this.settled();
  }

  /** Jump to the end (a skip). */
  finish(): void {
    this.f = this.to;
    this.apply();
    this.settled();
  }

  private settled(): void {
    this.unskip?.();
    this.unskip = null;
  }

  private apply(): void {
    const l = this.lights, b = this.base;
    if (!l || !b) return;
    const f = this.f;
    l.key.color.copy(b.key).lerp(MOON, NIGHT.keyMix * f);
    l.hemi.color.copy(b.sky).lerp(SKY, NIGHT.skyMix * f);
    l.rim.color.copy(b.rim).lerp(MOON, NIGHT.rimMix * f);
    l.key.intensity = nightIntensity(b.keyI, NIGHT.key, f);
    l.hemi.intensity = nightIntensity(b.hemiI, NIGHT.hemi, f);
    l.pool.intensity = nightIntensity(b.poolI, NIGHT.pool, f);
    l.rim.intensity = nightIntensity(b.rimI, NIGHT.rim, f);
  }
}
