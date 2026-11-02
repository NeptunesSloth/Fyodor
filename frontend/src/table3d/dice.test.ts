import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { rollLine, rollSummary, type DiceShow } from "../game/dice";
import { DiceTray } from "./dice";
import { diceOf, tableEnv, throwRoll } from "./diceThrow";
import { poseAt } from "./physics";
import * as THREE from "three";

// the dice's engraving is drawn on a 2D canvas: a do-nothing one is enough here
function canvasStub() {
  const method = (k: string | symbol) => {
    if (k === "getImageData") return (_x: number, _y: number, w: number, h: number) => ({ data: new Uint8ClampedArray(w * h * 4) });
    if (k === "measureText") return () => ({ width: 10 });
    return () => ({ addColorStop() {} });
  };
  const ctx: unknown = new Proxy({}, { get: (_t, k) => method(k), set: () => true });
  return { width: 0, height: 0, getContext: () => ctx };
}

const barbarian: DiceShow = { key: "b1", actor: "p1", sides: 20, results: [17, 7], coin: false, ignored: [1] };

describe("a die the rules ignored (Barbarian Class: roll one more, ignore the lowest)", () => {
  it("is thrown and lands like the others, but is marked ignored, gets no natural-20 or -1 mark, and leaves the total", () => {
    const thrown = throwRoll(barbarian, tableEnv());
    expect(thrown.dice).toHaveLength(2);
    expect(thrown.dice.map((d) => [d.label, d.ignored])).toEqual([["17", false], ["7", true]]);
    // it rests on the table like any die
    const p = new THREE.Vector3();
    poseAt(thrown.dice[1]!.track, thrown.dice[1]!.track.count - 1, p, new THREE.Quaternion());
    expect(p.y).toBeLessThan(0.7);
    // no natural 20 / 1 for an ignored die; a kept one keeps its mark
    expect(diceOf({ sides: 20, results: [20, 1], coin: false, ignored: [1] }).map((d) => d.crit)).toEqual(["high", null]);
    expect(diceOf({ sides: 20, results: [1, 20], coin: false, ignored: [1] }).map((d) => d.crit)).toEqual(["low", null]);
    expect(rollSummary(barbarian)).toBe("17 (ignored 7)");
    expect(rollLine("Alice", barbarian)).toBe("Alice · d20: 17 (ignored 7)");
  });

  describe("on the table", () => {
    beforeEach(() => vi.stubGlobal("document", { createElement: canvasStub }));
    afterEach(() => vi.unstubAllGlobals());

    it("has its chip struck through and marked ignored, and the line counts only the kept roll", () => {
      const tray = new DiceTray({ look: "resin", envMap: null, shadows: false, transmission: false, sound: false });
      tray.throw({ ...barbarian, results: [20, 7] }, "#d4a852", "Alice", { x: 0, z: 0, rotY: 0 }, tableEnv(), 0);
      tray.update(10_000, false, 1);
      const [t] = tray.hud((p) => ({ x: p.x * 10, y: -p.z * 10, visible: true }));
      expect(t!.line).toBe("Alice · d20: 20 (ignored 7)");
      expect(t!.crit).toBe("high");
      expect(t!.chips.map((c) => [c.label, c.ignored, c.crit, c.shown])).toEqual([["20", false, "high", true], ["7", true, null, true]]);
      expect(tray.describe()[0]!.dice.map((d) => d.ignored)).toEqual([false, true]);
      tray.dispose();
    });

    it("clears a player's dice when they roll again, and everyone's at the end of the turn", () => {
      const tray = new DiceTray({ look: "resin", envMap: null, shadows: false, transmission: false, sound: false });
      const env = tableEnv();
      tray.throw({ key: "a", actor: "p1", sides: 6, results: [3], coin: false }, "#d4a852", "Alice", { x: 0, z: 5, rotY: 0 }, env, 0);
      tray.throw({ key: "b", actor: "p2", sides: 6, results: [4], coin: false }, "#5fa8d3", "Bob", { x: 0, z: -5, rotY: Math.PI }, env, 0);
      expect(tray.count).toBe(2);
      tray.clear("p1", 100);
      tray.update(1000, false, 1);
      expect(tray.describe().map((t) => t.key)).toEqual(["b"]);
      tray.clear(undefined, 1000);
      tray.update(2000, false, 1);
      expect(tray.count).toBe(0);
      tray.dispose();
    });
  });
});
