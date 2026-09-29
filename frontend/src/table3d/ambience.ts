/**
 * Ambient sound for each plane, synthesised with WebAudio (no audio files, works offline):
 * filtered noise for wind, fire and crowds, and sparse tones for bells, birds and chimes.
 * Quiet by default and controlled by Settings → Sound → Ambient.
 */
import type { Ambience } from "../theme/planes";

function noiseBuffer(ctx: AudioContext, brown: boolean): AudioBuffer {
  const len = ctx.sampleRate * 4;
  const buf = ctx.createBuffer(1, len, ctx.sampleRate);
  const d = buf.getChannelData(0);
  let last = 0;
  for (let i = 0; i < len; i++) {
    const w = Math.random() * 2 - 1;
    if (brown) {
      last = (last + 0.02 * w) / 1.02;
      d[i] = last * 3.5;
    } else d[i] = w;
  }
  return buf;
}

interface Recipe { noise: "brown" | "white"; filter: BiquadFilterType; freq: number; q: number; gain: number; sway: number; blips?: { every: number; freq: [number, number]; dur: number; gain: number; type: OscillatorType } }

const RECIPES: Record<Ambience, Recipe> = {
  hearth: { noise: "brown", filter: "lowpass", freq: 500, q: 0.7, gain: 0.5, sway: 0.2, blips: { every: 0.35, freq: [1800, 4200], dur: 0.012, gain: 0.08, type: "square" } },
  city: { noise: "brown", filter: "bandpass", freq: 380, q: 0.6, gain: 0.55, sway: 0.15, blips: { every: 9, freq: [520, 660], dur: 1.6, gain: 0.05, type: "sine" } },
  night: { noise: "white", filter: "bandpass", freq: 700, q: 0.9, gain: 0.18, sway: 0.5, blips: { every: 1.4, freq: [4200, 4600], dur: 0.05, gain: 0.02, type: "sine" } },
  temple: { noise: "brown", filter: "lowpass", freq: 300, q: 0.5, gain: 0.3, sway: 0.1, blips: { every: 5, freq: [220, 330], dur: 3.5, gain: 0.04, type: "sine" } },
  wilds: { noise: "white", filter: "bandpass", freq: 500, q: 0.7, gain: 0.2, sway: 0.6, blips: { every: 2.5, freq: [2400, 3600], dur: 0.12, gain: 0.03, type: "sine" } },
  shrine: { noise: "white", filter: "bandpass", freq: 600, q: 0.8, gain: 0.14, sway: 0.4, blips: { every: 3, freq: [1300, 2600], dur: 1.2, gain: 0.03, type: "triangle" } },
  desert: { noise: "white", filter: "highpass", freq: 1200, q: 0.5, gain: 0.12, sway: 0.7 },
  jungle: { noise: "white", filter: "bandpass", freq: 3800, q: 2, gain: 0.06, sway: 0.3, blips: { every: 1.8, freq: [1800, 3200], dur: 0.15, gain: 0.03, type: "sine" } },
  machine: { noise: "brown", filter: "lowpass", freq: 160, q: 3, gain: 0.6, sway: 0.1, blips: { every: 4, freq: [90, 140], dur: 0.25, gain: 0.08, type: "sawtooth" } },
  meadow: { noise: "white", filter: "bandpass", freq: 450, q: 0.6, gain: 0.14, sway: 0.5, blips: { every: 2, freq: [2800, 4000], dur: 0.1, gain: 0.03, type: "sine" } },
};

/** Start the ambience; returns a stop function. */
export function startAmbience(kind: Ambience, volume: number): () => void {
  const Ctx = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!Ctx) return () => undefined;
  let ctx: AudioContext;
  try {
    ctx = new Ctx();
  } catch {
    return () => undefined;
  }
  const r = RECIPES[kind];
  const master = ctx.createGain();
  master.gain.value = 0;
  master.gain.linearRampToValueAtTime(Math.min(1, volume) * 0.35, ctx.currentTime + 2.5);
  master.connect(ctx.destination);
  const src = ctx.createBufferSource();
  src.buffer = noiseBuffer(ctx, r.noise === "brown");
  src.loop = true;
  const filter = ctx.createBiquadFilter();
  filter.type = r.filter;
  filter.frequency.value = r.freq;
  filter.Q.value = r.q;
  const bed = ctx.createGain();
  bed.gain.value = r.gain;
  const lfo = ctx.createOscillator();
  lfo.frequency.value = 0.07;
  const lfoGain = ctx.createGain();
  lfoGain.gain.value = r.gain * r.sway;
  lfo.connect(lfoGain).connect(bed.gain);
  src.connect(filter).connect(bed).connect(master);
  src.start();
  lfo.start();
  let timer = 0;
  const blip = () => {
    const b = r.blips;
    if (!b) return;
    const o = ctx.createOscillator();
    o.type = b.type;
    o.frequency.value = b.freq[0] + Math.random() * (b.freq[1] - b.freq[0]);
    const g = ctx.createGain();
    const t = ctx.currentTime;
    g.gain.setValueAtTime(0, t);
    g.gain.linearRampToValueAtTime(b.gain, t + Math.min(0.02, b.dur / 3));
    g.gain.exponentialRampToValueAtTime(0.0001, t + b.dur);
    o.connect(g).connect(master);
    o.start(t);
    o.stop(t + b.dur + 0.05);
    timer = window.setTimeout(blip, (b.every * (0.4 + Math.random() * 1.2)) * 1000);
  };
  if (r.blips) timer = window.setTimeout(blip, 1500);
  // browsers start audio only after a user gesture
  const resume = () => void ctx.resume();
  window.addEventListener("pointerdown", resume, { once: true });
  return () => {
    window.clearTimeout(timer);
    window.removeEventListener("pointerdown", resume);
    try {
      master.gain.linearRampToValueAtTime(0, ctx.currentTime + 0.4);
      window.setTimeout(() => void ctx.close(), 500);
    } catch {
      void ctx.close();
    }
  };
}
