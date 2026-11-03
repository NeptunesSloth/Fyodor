/**
 * Subtle tabletop sounds, synthesised with WebAudio (no audio files, works offline).
 * Card slides, a soft tap, dice on felt, a coin ring, a riffle for shuffles — never arcade beeps.
 * Gameplay never depends on sound; everything is silent until the page has had a user gesture.
 */
import { usePrefs } from "../state/prefs";

export type SoundName =
  | "card" | "place" | "tap" | "flip" | "shuffle" | "draw" | "dice" | "coin" | "token" | "counter" | "response" | "turn" | "bag" | "ping"
  // the end-of-game stings (game/motion/endScene.ts): short, soft, and never needed (every one has its scene)
  | "victory" | "defeat" | "drawn" | "eliminated";
type Channel = "cards" | "dice" | "ui" | "ambient";

const CHANNEL: Record<SoundName, Channel> = {
  card: "cards", place: "cards", tap: "cards", flip: "cards", shuffle: "cards", draw: "cards", token: "cards", counter: "cards",
  dice: "dice", coin: "dice", bag: "dice",
  response: "ui", turn: "ui", ping: "ui",
  victory: "ui", defeat: "ui", drawn: "ui", eliminated: "ui",
};

let ctx: AudioContext | null = null;
let noiseBuf: AudioBuffer | null = null;

function audio(): AudioContext | null {
  if (typeof window === "undefined" || !("AudioContext" in window)) return null;
  if (!ctx) {
    try {
      ctx = new AudioContext();
    } catch {
      return null;
    }
  }
  if (ctx.state === "suspended") void ctx.resume().catch(() => undefined);
  return ctx;
}

function noise(ac: AudioContext): AudioBuffer {
  if (!noiseBuf) {
    noiseBuf = ac.createBuffer(1, ac.sampleRate * 0.6, ac.sampleRate);
    const d = noiseBuf.getChannelData(0);
    for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
  }
  return noiseBuf;
}

/** A filtered noise burst: the basis of card and felt sounds. */
function burst(ac: AudioContext, out: AudioNode, t: number, dur: number, freq: number, q: number, gain: number) {
  const src = ac.createBufferSource();
  src.buffer = noise(ac);
  const f = ac.createBiquadFilter();
  f.type = "bandpass";
  f.frequency.value = freq;
  f.Q.value = q;
  const g = ac.createGain();
  g.gain.setValueAtTime(0, t);
  g.gain.linearRampToValueAtTime(gain, t + 0.005);
  g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
  src.connect(f).connect(g).connect(out);
  src.start(t, Math.random() * 0.3, dur + 0.05);
}

function tone(ac: AudioContext, out: AudioNode, t: number, freq: number, dur: number, gain: number, type: OscillatorType = "sine") {
  const o = ac.createOscillator();
  o.type = type;
  o.frequency.value = freq;
  const g = ac.createGain();
  g.gain.setValueAtTime(0, t);
  g.gain.linearRampToValueAtTime(gain, t + 0.004);
  g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
  o.connect(g).connect(out);
  o.start(t);
  o.stop(t + dur + 0.05);
}

let last: Record<string, number> = {};

/**
 * A gain node on one of the sound channels at the player's volume, or null when that channel is muted or silent (or
 * there is no audio): nothing is created then. For sounds built elsewhere (game/diceSound.ts).
 */
export function channelOut(channel: Channel): { ac: AudioContext; out: GainNode } | null {
  const s = usePrefs.getState().sound;
  const level = s.muted ? 0 : s.master * s[channel];
  if (level <= 0.001) return null;
  const ac = audio();
  if (!ac || ac.state !== "running") return null;
  const out = ac.createGain();
  out.gain.value = level * 0.7;
  out.connect(ac.destination);
  return { ac, out };
}

export function play(name: SoundName): void {
  const prefs = usePrefs.getState();
  const s = prefs.sound;
  const level = s.muted ? 0 : s.master * s[CHANNEL[name]];
  if (level <= 0.001) return;
  const now = performance.now();
  if (now - (last[name] ?? 0) < 60) return; // don't stack identical sounds
  last = { ...last, [name]: now };
  const ac = audio();
  if (!ac || ac.state !== "running") return;
  const out = ac.createGain();
  out.gain.value = level * 0.7;
  out.connect(ac.destination);
  const t = ac.currentTime + 0.01;
  switch (name) {
    case "card":
    case "draw":
      burst(ac, out, t, 0.09, 2600, 0.8, 0.35);
      break;
    case "place":
      burst(ac, out, t, 0.06, 900, 1.2, 0.5);
      burst(ac, out, t + 0.012, 0.05, 2200, 1, 0.2);
      break;
    case "tap":
      burst(ac, out, t, 0.05, 1500, 2, 0.35);
      break;
    case "flip":
      burst(ac, out, t, 0.05, 3000, 1, 0.25);
      burst(ac, out, t + 0.07, 0.05, 2400, 1, 0.25);
      break;
    case "shuffle":
      for (let i = 0; i < 12; i++) burst(ac, out, t + i * 0.035, 0.04, 2800 + Math.random() * 800, 1.5, 0.18);
      break;
    case "token":
    case "counter":
      tone(ac, out, t, name === "token" ? 520 : 780, 0.08, 0.08, "triangle");
      burst(ac, out, t, 0.03, 1800, 3, 0.15);
      break;
    case "dice":
    case "bag":
      for (let i = 0; i < 5; i++) burst(ac, out, t + i * (0.05 + Math.random() * 0.04), 0.04, 1200 + Math.random() * 1400, 4, 0.3 - i * 0.04);
      break;
    case "coin":
      tone(ac, out, t, 1850, 0.5, 0.06);
      tone(ac, out, t, 2780, 0.35, 0.03);
      break;
    case "response":
      tone(ac, out, t, 660, 0.25, 0.05);
      break;
    case "turn":
      tone(ac, out, t, 392, 0.4, 0.04);
      tone(ac, out, t + 0.12, 523, 0.5, 0.035);
      break;
    case "ping": // a small bell: "look here"
      tone(ac, out, t, 1318, 0.22, 0.045, "triangle");
      tone(ac, out, t + 0.07, 1760, 0.3, 0.03, "triangle");
      break;
    case "victory": // a warm rising fifth, like a brass bell struck twice
      tone(ac, out, t, 392, 0.9, 0.045, "triangle");
      tone(ac, out, t + 0.16, 587, 1.1, 0.04, "triangle");
      tone(ac, out, t + 0.16, 1174, 0.7, 0.012);
      break;
    case "defeat": // a low falling step, quiet
      tone(ac, out, t, 220, 0.9, 0.045, "triangle");
      tone(ac, out, t + 0.2, 185, 1.1, 0.04, "triangle");
      break;
    case "drawn": // one neutral bell
      tone(ac, out, t, 523, 0.9, 0.035);
      tone(ac, out, t, 784, 0.6, 0.015);
      break;
    case "eliminated": // a single low note, shorter than defeat
      tone(ac, out, t, 196, 0.6, 0.035, "triangle");
      break;
  }
}

/** Map a new log line to a sound (cosmetic only). */
export function soundForLog(kind: string, text: string): SoundName | null {
  if (kind === "turn") return "turn";
  if (kind === "dice") return null; // the thrown dice make their own sound as they land (game/diceSound.ts)
  if (/shuffled/.test(text)) return "shuffle";
  if (/rolled|a d\d+/.test(text)) return "dice";
  if (/flipped a coin|coin/.test(text)) return "coin";
  if (/ drew /.test(text)) return "draw";
  if (/ untapped| tapped/.test(text)) return "tap";
  if (/ created /.test(text)) return "token";
  if (/counter/.test(text)) return "counter";
  if (/turned .* face|transform|turned over/.test(text)) return "flip";
  if (/ played | cast | put .* onto the battlefield/.test(text)) return "place";
  if (/wants to .* any responses/.test(text)) return "response";
  if (/ moved | discarded | milled| exiled/.test(text)) return "card";
  return null;
}
