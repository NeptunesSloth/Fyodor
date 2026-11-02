import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { usePrefs } from "../state/prefs";
import { diceClack, diceSettle } from "./diceSound";

/** A stand-in AudioContext that counts what it is asked to make. */
function fakeAudio() {
  const made = { contexts: 0, nodes: 0 };
  const param = () => ({ value: 0, setValueAtTime() {}, linearRampToValueAtTime() {}, exponentialRampToValueAtTime() {} });
  const node = () => {
    made.nodes++;
    const n = { gain: param(), frequency: param(), Q: param(), type: "", buffer: null, connect: () => n, start() {}, stop() {} };
    return n;
  };
  class Ctx {
    state = "running";
    currentTime = 0;
    sampleRate = 8000;
    destination = {};
    constructor() { made.contexts++; }
    resume() { return Promise.resolve(); }
    createGain = node;
    createBiquadFilter = node;
    createOscillator = node;
    createBufferSource = node;
    createBuffer(_c: number, n: number) { return { sampleRate: 8000, getChannelData: () => new Float32Array(n) }; }
  }
  return { made, Ctx };
}

describe("the dice's own sound", () => {
  let audio: ReturnType<typeof fakeAudio>;
  beforeEach(() => {
    audio = fakeAudio();
    vi.stubGlobal("window", { AudioContext: audio.Ctx });
    vi.stubGlobal("AudioContext", audio.Ctx);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    usePrefs.getState().set({ sound: { ...usePrefs.getState().sound, muted: false, dice: 0.8, master: 0.6 } });
  });

  it("is silent when sound is muted: no audio is created at all", () => {
    usePrefs.getState().set({ sound: { ...usePrefs.getState().sound, muted: true } });
    expect(diceClack(6, "table", 0.5)).toBe(false);
    expect(diceClack(6, "die", 0.5)).toBe(false);
    expect(diceSettle(true)).toBe(false);
    expect(audio.made.nodes).toBe(0);
  });

  it("is silent when the Dice or Master volume is at zero", () => {
    usePrefs.getState().set({ sound: { ...usePrefs.getState().sound, muted: false, dice: 0 } });
    expect(diceClack(6, "table", 0.5)).toBe(false);
    usePrefs.getState().set({ sound: { ...usePrefs.getState().sound, dice: 0.8, master: 0 } });
    expect(diceClack(6, "table", 0.5)).toBe(false);
    expect(audio.made.nodes).toBe(0);
  });

  it("clacks when it can be heard, the table, a die, a rail, a deck and a coin each its own way; too soft to hear is skipped", () => {
    usePrefs.getState().set({ sound: { ...usePrefs.getState().sound, muted: false, dice: 0.8, master: 0.6 } });
    expect(diceClack(0.2, "table", 0.5)).toBe(false);
    const counts = (["table", "die", "wall", "deck"] as const).map((hit) => {
      const before = audio.made.nodes;
      expect(diceClack(5, hit, 0.5)).toBe(true);
      return audio.made.nodes - before;
    });
    expect(new Set(counts).size).toBeGreaterThan(1);
    expect(diceClack(5, "table", 0.33, true)).toBe(true);
  });
});
