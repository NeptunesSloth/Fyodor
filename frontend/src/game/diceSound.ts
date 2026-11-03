/**
 * The dice's own sound, synthesised with WebAudio as they land (no audio files, nothing fetched). Each impact the
 * physics recorded (table3d/physics.ts) plays when the throw reaches it, as loud as it was hard: a felted thud for
 * the table, a bright resin knock die on die, a dull bump off the leather rail, a papery tap off a deck, and a ring
 * for a coin. It follows Settings → Sound (the Dice channel and Master, and mute): when that is silent, nothing is
 * created at all.
 */
import { channelOut } from "./sound";

export type ImpactWith = "table" | "die" | "wall" | "deck";

let noiseBuf: AudioBuffer | null = null;
function noise(ac: AudioContext): AudioBuffer {
  if (!noiseBuf || noiseBuf.sampleRate !== ac.sampleRate) {
    noiseBuf = ac.createBuffer(1, Math.round(ac.sampleRate * 0.4), ac.sampleRate);
    const d = noiseBuf.getChannelData(0);
    let s = 0x2545f491;
    for (let i = 0; i < d.length; i++) {
      s ^= s << 13; s ^= s >>> 17; s ^= s << 5;
      d[i] = ((s >>> 0) / 4294967296) * 2 - 1;
    }
  }
  return noiseBuf;
}

function burst(ac: AudioContext, out: AudioNode, t: number, dur: number, type: BiquadFilterType, freq: number, q: number, gain: number): void {
  const src = ac.createBufferSource();
  src.buffer = noise(ac);
  const f = ac.createBiquadFilter();
  f.type = type;
  f.frequency.value = freq;
  f.Q.value = q;
  const g = ac.createGain();
  g.gain.setValueAtTime(0, t);
  g.gain.linearRampToValueAtTime(gain, t + 0.002);
  g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
  src.connect(f).connect(g).connect(out);
  src.start(t, (t * 7.31) % 0.3, dur + 0.03);
}

function ping(ac: AudioContext, out: AudioNode, t: number, freq: number, dur: number, gain: number, drop = 1): void {
  const o = ac.createOscillator();
  o.type = "sine";
  o.frequency.setValueAtTime(freq, t);
  if (drop !== 1) o.frequency.exponentialRampToValueAtTime(freq * drop, t + dur);
  const g = ac.createGain();
  g.gain.setValueAtTime(0, t);
  g.gain.linearRampToValueAtTime(gain, t + 0.002);
  g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
  o.connect(g).connect(out);
  o.start(t);
  o.stop(t + dur + 0.03);
}

let voices: number[] = [];

/**
 * One impact. `speed`: closing speed along the contact normal (world units a second); `size`: the die's radius
 * (smaller dice sound higher); `coin`: the body that hit is a coin.
 */
export function diceClack(speed: number, hit: ImpactWith, size: number, coin = false): boolean {
  if (speed < 0.45) return false;
  // a crowd of dice: a dozen voices at most at once, the rest are lost in the clatter anyway
  const now = typeof performance !== "undefined" ? performance.now() : Date.now();
  voices = voices.filter((v) => now - v < 120);
  if (voices.length >= 12) return false;
  const ch = channelOut("dice");
  if (!ch) return false;
  voices.push(now);
  const { ac, out } = ch;
  const t = ac.currentTime + 0.005;
  const v = Math.min(1, Math.pow(speed / 7, 1.25));
  const pitch = Math.max(0.75, Math.min(1.35, 0.56 / Math.max(0.2, size)));
  if (coin) {
    if (hit === "die") burst(ac, out, t, 0.02, "highpass", 4200, 0.7, 0.35 * v);
    else burst(ac, out, t, 0.03, "bandpass", 2400, 1.5, 0.3 * v);
    // a struck disc: inharmonic partials, ringing longer the harder it landed
    const ring = 0.12 + 0.4 * v;
    ping(ac, out, t, 2210, ring, 0.05 * v);
    ping(ac, out, t, 3570, ring * 0.7, 0.035 * v);
    ping(ac, out, t, 5290, ring * 0.45, 0.02 * v);
    return true;
  }
  switch (hit) {
    case "die":
      // resin on resin: a short bright knock
      burst(ac, out, t, 0.018 + 0.012 * v, "bandpass", 3600 * pitch, 1.8, 0.55 * v);
      ping(ac, out, t, 2650 * pitch, 0.035, 0.06 * v);
      ping(ac, out, t, 4180 * pitch, 0.025, 0.04 * v);
      break;
    case "table":
      // felt over wood: a soft low thud with a little tick of the corner landing
      burst(ac, out, t, 0.05 + 0.03 * v, "lowpass", 650 * pitch, 0.8, 0.6 * v);
      ping(ac, out, t, 175 * pitch, 0.06, 0.12 * v, 0.6);
      burst(ac, out, t, 0.012, "bandpass", 2300 * pitch, 2, 0.12 * v);
      break;
    case "wall":
      burst(ac, out, t, 0.06, "lowpass", 380, 0.7, 0.5 * v);
      ping(ac, out, t, 120, 0.07, 0.1 * v, 0.7);
      break;
    case "deck":
      burst(ac, out, t, 0.035, "bandpass", 1500, 1.1, 0.45 * v);
      break;
  }
  return true;
}

/** A single soft settle (reduced motion: the dice appear at rest, so one quiet sound instead of the clatter). */
export function diceSettle(coin: boolean): boolean {
  return diceClack(2.2, "table", 0.5, coin);
}

/**
 * -- table toys -- the dice cannon going off (game/cannon.ts): a soft low pop and a puff of air, a toy's, not a gun's (quieter
 * than the dice that follow it). On the Dice channel; silent when that is.
 */
export function cannonBoom(): boolean {
  const ch = channelOut("dice");
  if (!ch) return false;
  const { ac, out } = ch;
  const t = ac.currentTime + 0.005;
  burst(ac, out, t, 0.32, "lowpass", 420, 0.7, 0.55);
  ping(ac, out, t, 92, 0.22, 0.32, 0.55);
  burst(ac, out, t + 0.01, 0.12, "bandpass", 1300, 0.8, 0.12);
  return true;
}
