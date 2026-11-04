/**
 * The room's living light, as pure functions of time (no three.js, no WebGL), so they are unit-tested and the GPU
 * copies (env/shaders.ts) agree with them: a flame's flicker, a hanging lantern's sway, a hearth's slow breathing.
 */

/** A hash of an integer to [0, 1). */
export function hash1(n: number): number {
  const s = Math.sin(n * 127.1 + 311.7) * 43758.5453123;
  return s - Math.floor(s);
}

/** Smooth 1D value noise in [0, 1] (cubic between hashed integers). */
export function noise1(x: number): number {
  const i = Math.floor(x);
  const f = x - i;
  const u = f * f * (3 - 2 * f);
  return hash1(i) * (1 - u) + hash1(i + 1) * u;
}

/**
 * A flame's brightness at time `t` (seconds), around 1: two octaves of noise for the restless flutter and a slow
 * swell, never below 1 − amount or above 1 + amount. `phase` keeps neighbouring flames out of step.
 */
export function flicker(t: number, phase: number, amount: number): number {
  const n = noise1(t * 6.3 + phase * 17.0) * 0.55 + noise1(t * 13.7 + phase * 5.0) * 0.25 + noise1(t * 1.3 + phase) * 0.2; // 0..1
  return 1 + (n * 2 - 1) * amount;
}

/**
 * A lantern hanging on a chain: its tilt (radians) about x and z at time `t`, a slow pendulum of period about 4–5 s
 * with a little drift, never more than `amp`.
 */
export function sway(t: number, phase: number, amp: number): [number, number] {
  const a = Math.sin(t * 1.35 + phase) * 0.75 + Math.sin(t * 0.53 + phase * 2.1) * 0.25;
  const b = Math.sin(t * 1.05 + phase * 1.7) * 0.6 + Math.sin(t * 0.41 + phase * 0.6) * 0.4;
  return [a * amp, b * amp * 0.6];
}

/** A hearth's glow: deeper and slower than a candle (embers breathing), with the flames' flutter on top. */
export function hearth(t: number, phase: number, amount: number): number {
  const slow = noise1(t * 0.7 + phase) * 2 - 1;
  return flicker(t, phase, amount * 0.6) + slow * amount * 0.4;
}
