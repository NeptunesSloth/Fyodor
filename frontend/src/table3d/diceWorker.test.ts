import * as THREE from "three";
import { describe, expect, it } from "vitest";
import type { DiceShow } from "../game/dice";
import { DiceTray } from "./dice";
import { cannonEnv, cannonLaunch, tableEnv, throwRoll, type Launcher, type ThrowEnv } from "./diceThrow";
import { fromReply, launcherName, runJob, toJob, transferables } from "./diceThrowJob";
import { canThrowOffThread, throwOffThread } from "./diceWorker";

// the dice's engraving is drawn on a 2D canvas: a do-nothing one is enough here
function documentStub() {
  const method = (k: string | symbol) => {
    if (k === "getImageData") return (_x: number, _y: number, w: number, h: number) => ({ data: new Uint8ClampedArray(w * h * 4) });
    if (k === "measureText") return () => ({ width: 10 });
    return () => ({ addColorStop() {} });
  };
  const ctx: unknown = new Proxy({}, { get: (_t, k) => method(k), set: () => true });
  return { createElement: () => ({ width: 0, height: 0, getContext: () => ctx }) };
}

const twelve: DiceShow = { key: "w12", actor: "p1", sides: 6, results: [1, 2, 3, 4, 5, 6, 6, 5, 4, 3, 2, 1], coin: false };
const piles = [{ x: 6.1, z: 2.4, w: 0.84, d: 1.17, h: 0.4 }];

describe("the dice worker's throw (diceThrowJob.ts)", () => {
  it("comes back with exactly the frames, turns and impacts the main thread's throw has", () => {
    const cases: [DiceShow, ThrowEnv, Launcher | undefined][] = [
      [twelve, tableEnv(piles), undefined],
      [{ ...twelve, key: "w3", sides: 20, results: [20, 1, 7] }, tableEnv(), undefined],
      [{ ...twelve, key: "wc", sides: 100, results: [42] }, cannonEnv(piles, 2), cannonLaunch],
    ];
    for (const [show, env, launcher] of cases) {
      const here = throwRoll(show, env, launcher);
      // (structured clone, as postMessage does: only plain data survives the trip)
      const job = structuredClone(toJob(7, show, env, launcherName(launcher)!));
      const reply = runJob(job);
      expect(reply.id).toBe(7);
      const back = fromReply(structuredClone(reply, { transfer: transferables(reply) }));
      expect(back.dice).toHaveLength(here.dice.length);
      back.dice.forEach((d, i) => {
        const h = here.dice[i]!;
        expect([d.kind, d.face, d.label, d.result, d.ignored, d.crit, d.rest]).toEqual([h.kind, h.face, h.label, h.result, h.ignored, h.crit, h.rest]);
        expect(d.track.count).toBe(h.track.count);
        expect(d.track.rest).toBe(h.track.rest);
        expect(Array.from(d.track.frames.subarray(0, d.track.count * 7))).toEqual(Array.from(h.track.frames.subarray(0, h.track.count * 7)));
        // the symmetry that shows the server's number on top
        expect(d.turn).toBeInstanceOf(THREE.Quaternion);
        expect(d.turn.toArray()).toEqual(h.turn.toArray());
      });
      expect(back.impacts).toEqual(here.impacts);
      expect([back.seconds, back.attempts, back.snapped]).toEqual([here.seconds, here.attempts, here.snapped]);
    }
  });

  it("names only the launchers the worker knows (any other throw stays on the main thread)", () => {
    expect(launcherName(undefined)).toBe("hand");
    expect(launcherName(cannonLaunch)).toBe("cannon");
    expect(launcherName(() => [])).toBeNull();
  });

  it("without a Worker (here, as in old browsers) declines, and the tray throws on the main thread at once", () => {
    expect(typeof Worker).toBe("undefined");
    expect(canThrowOffThread()).toBe(false);
    expect(throwOffThread(twelve, tableEnv(), undefined, () => undefined)).toBe(false);
    const g = globalThis as { document?: unknown };
    const had = g.document;
    g.document = documentStub();
    try {
      const tray = new DiceTray({ look: "resin", envMap: null, shadows: false, sound: false });
      const { settles } = tray.throw(twelve, "#d4a852", "Alice", { x: 0, z: 0, rotY: 0 }, tableEnv(), 0);
      expect(settles).toBeGreaterThan(0);
      expect(tray.describe()[0]!.dice).toHaveLength(12);
      tray.dispose();
    } finally {
      g.document = had;
    }
  });
});
