import * as THREE from "three";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import type { DiceShow } from "../game/dice";
import { DiceTray } from "./dice";
import { tableEnv, throwRoll } from "./diceThrow";
import { runJob, transferables, type ThrowJob } from "./diceThrowJob";
import { poseAt } from "./physics";

/** A stand-in for the dice worker: answers on a later task, as a real one does, through a structured clone. */
class FakeWorker {
  static made = 0;
  /** Answer every job with an error (a throw the worker couldn't do). */
  static failing = false;
  onmessage: ((e: { data: unknown }) => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(public url: URL) {
    FakeWorker.made++;
    setTimeout(() => this.onmessage?.({ data: { ready: true } }), 0);
  }
  postMessage(job: ThrowJob): void {
    const copy = structuredClone(job);
    setTimeout(() => {
      if (FakeWorker.failing) return this.onmessage?.({ data: { id: copy.id, error: "no" } });
      const reply = runJob(copy);
      this.onmessage?.({ data: structuredClone(reply, { transfer: transferables(reply) }) });
    }, 5);
  }
  terminate(): void {}
}

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

const g = globalThis as { Worker?: unknown; document?: unknown };
beforeAll(() => {
  g.Worker = FakeWorker;
  g.document = documentStub();
});
afterAll(() => {
  delete g.Worker;
  delete g.document;
});

const show: DiceShow = { key: "async12", actor: "p1", sides: 8, results: [8, 7, 6, 5, 4, 3, 2, 1, 1, 2, 3, 4], coin: false };

const tick = (ms = 0) => new Promise((r) => setTimeout(r, ms));

describe("a throw simulated on the dice worker", () => {
  it("before the worker is ready (it is still loading), is thrown at once here, and starts the worker for the next", async () => {
    const tray = new DiceTray({ look: "resin", envMap: null, shadows: false, sound: false });
    tray.throw({ ...show, key: "early" }, "#d4a852", "Alice", { x: 0, z: 0, rotY: 0 }, tableEnv(), 0);
    expect(tray.describe()[0]!.dice).toHaveLength(12);
    expect(FakeWorker.made).toBe(1);
    await tick();
    tray.dispose();
  });

  it("waits hidden for its tracks, then plays from the hand on the tray's own loop and lands where the main thread's would", async () => {
    const tray = new DiceTray({ look: "resin", envMap: null, shadows: false, sound: false });
    const frame = { x: 2, z: 1, rotY: 0.5 };
    tray.throw(show, "#d4a852", "Alice", frame, tableEnv(), 0);
    expect(FakeWorker.made).toBe(1);
    // nothing on the table yet, but the loop keeps drawing until it's back
    expect(tray.describe()).toHaveLength(0);
    expect(tray.count).toBe(1);
    expect(tray.hud(() => ({ x: 0, y: 0, visible: true }))).toHaveLength(0);
    expect(tray.update(50, false, 1)).toBe(true);
    await tick(60);
    expect(tray.describe()[0]!.dice).toHaveLength(12);
    // its clock starts at the first update after it's back: the dice are in the hand, not mid-flight
    tray.update(1000, false, 1);
    const here = throwRoll(show, tableEnv());
    const root = new THREE.Object3D();
    root.position.set(frame.x, 0, frame.z);
    root.rotation.set(0, frame.rotY, 0);
    root.updateMatrixWorld(true);
    const p = new THREE.Vector3();
    const q = new THREE.Quaternion();
    tray.positions().forEach((at, i) => {
      poseAt(here.dice[i]!.track, 0, p, q);
      expect(at.distanceTo(p.applyMatrix4(root.matrixWorld))).toBeLessThan(1e-5);
    });
    // and comes to rest just where the main thread's throw does
    tray.update(1000 + here.seconds * 1000 + 50, false, 1);
    tray.positions().forEach((at, i) => {
      const d = here.dice[i]!;
      poseAt(d.track, d.track.count - 1, p, q);
      expect(at.distanceTo(p.applyMatrix4(root.matrixWorld))).toBeLessThan(1e-5);
    });
    expect(tray.describe()[0]!.dice.map((d) => d.label)).toEqual(show.results.map(String));
    tray.dispose();
  });

  it("cleared before it comes back, it never shows", async () => {
    const tray = new DiceTray({ look: "resin", envMap: null, shadows: false, sound: false });
    tray.throw({ ...show, key: "gone" }, "#d4a852", "Alice", { x: 0, z: 0, rotY: 0 }, tableEnv(), 0);
    tray.clear("p1", 1);
    tray.update(2, false, 1);
    expect(tray.count).toBe(0);
    await tick(60);
    tray.update(100, false, 1);
    expect(tray.count).toBe(0);
    expect(tray.group.children).toHaveLength(0);
    tray.dispose();
  });

  it("one the worker couldn't throw is thrown here instead, the same throw", async () => {
    FakeWorker.failing = true;
    const tray = new DiceTray({ look: "resin", envMap: null, shadows: false, sound: false });
    tray.throw({ ...show, key: "fail" }, "#d4a852", "Alice", { x: 0, z: 0, rotY: 0 }, tableEnv(), 0);
    expect(tray.describe()).toHaveLength(0);
    await tick(60);
    FakeWorker.failing = false;
    const here = throwRoll({ ...show, key: "fail" }, tableEnv());
    tray.update(0, false, 1);
    tray.update(here.seconds * 1000 + 50, false, 1);
    expect(tray.restPositions("fail")).toHaveLength(12);
    const p = new THREE.Vector3();
    tray.positions().forEach((at, i) => {
      poseAt(here.dice[i]!.track, here.dice[i]!.track.count - 1, p, new THREE.Quaternion());
      expect(at.distanceTo(p)).toBeLessThan(1e-5);
    });
    tray.dispose();
  });

  it("a tray that throws at once (the toy tray: each kind lands round the dice before it) never waits for the worker", () => {
    const made = FakeWorker.made;
    const tray = new DiceTray({ look: "resin", envMap: null, shadows: false, sound: false, offThread: false });
    tray.throw({ ...show, key: "now" }, "#d4a852", "Alice", { x: 0, z: 0, rotY: 0 }, tableEnv(), 0);
    expect(tray.describe()[0]!.dice).toHaveLength(12);
    expect(tray.restPositions("now")).toHaveLength(12);
    expect(FakeWorker.made).toBe(made);
    tray.dispose();
  });
});
