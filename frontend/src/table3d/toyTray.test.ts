import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ToyTrayScene, laneEnv, planTray, type TrayGroup } from "./toyTray";

// no WebGL here: a stand-in renderer that records what the tray asks of it
const made: { disposed: number; lost: number; renders: number }[] = [];
vi.mock("three", async (importOriginal) => {
  const THREE = await importOriginal<typeof import("three")>();
  class FakeRenderer {
    stats = { disposed: 0, lost: 0, renders: 0 };
    outputColorSpace = "";
    toneMapping = 0;
    constructor() {
      made.push(this.stats);
    }
    setPixelRatio() {}
    setClearColor() {}
    setSize() {}
    render() {
      this.stats.renders++;
    }
    dispose() {
      this.stats.disposed++;
    }
    forceContextLoss() {
      this.stats.lost++;
    }
  }
  return { ...THREE, WebGLRenderer: FakeRenderer };
});

const group = (sides: number, n: number, coin = false) => ({ sides, coin, results: Array.from({ length: n }, () => 1) });

describe("the 3D dice & toys tray: lanes", () => {
  it("gives each kind of die its own lane, side by side inside the tray", () => {
    for (const groups of [[group(6, 3), group(20, 1)], [group(4, 4), group(6, 4), group(8, 4)], [group(20, 8), group(6, 2, true)], [group(12, 1)]]) {
      const plan = planTray(groups);
      plan.lanes.forEach((lane, i) => {
        expect(lane.x - lane.width / 2).toBeGreaterThan(plan.bounds.minX);
        expect(lane.x + lane.width / 2).toBeLessThan(plan.bounds.maxX);
        if (i) expect(lane.x - lane.width / 2).toBeGreaterThan(plan.lanes[i - 1]!.x + plan.lanes[i - 1]!.width / 2);
        // thrown from the near rim toward the far one, inside the tray
        const env = laneEnv(plan, lane, []);
        expect(env.hand.z + lane.radius).toBeLessThan(plan.bounds.maxZ);
        expect(env.land.maxZ).toBeLessThan(env.hand.z);
        expect(env.land.minX + lane.x).toBeGreaterThan(plan.bounds.minX);
        expect(env.land.maxX + lane.x).toBeLessThan(plan.bounds.maxX);
      });
    }
  });

  it("widens for a big pool and stays put for a small one", () => {
    expect(planTray([group(20, 1)]).width).toBe(planTray([group(6, 2), group(20, 1)]).width);
    expect(planTray([group(6, 4), group(8, 4), group(10, 4)]).width).toBeGreaterThan(planTray([group(20, 1)]).width);
  });
});

describe("the 3D dice & toys tray: a throw", () => {
  let frames: FrameRequestCallback[] = [];
  beforeEach(() => {
    made.length = 0;
    frames = [];
    // the dice print their numbers on a 2D canvas: a do-nothing one is enough here
    const canvasStub = () => {
      const c = { width: 0, height: 0, getContext: () => ctx2d };
      const method = (k: string | symbol) => {
        if (k === "getImageData") return (_x: number, _y: number, w: number, h: number) => ({ data: new Uint8ClampedArray(w * h * 4) });
        if (k === "measureText") return () => ({ width: 10 });
        return () => ({ addColorStop() {} });
      };
      const ctx2d: unknown = new Proxy({}, { get: (_t, k) => method(k), set: () => true });
      return c;
    };
    vi.stubGlobal("document", { createElement: canvasStub });
    vi.stubGlobal("window", { devicePixelRatio: 1 });
    vi.stubGlobal("requestAnimationFrame", (f: FrameRequestCallback) => frames.push(f));
    vi.stubGlobal("cancelAnimationFrame", () => {});
  });
  afterEach(() => vi.unstubAllGlobals());

  const canvas = { clientWidth: 560, clientHeight: 210 } as HTMLCanvasElement;
  const throwOf = (key: string, ...gs: [number, number, boolean?][]): TrayGroup[] =>
    gs.map(([sides, n, coin], i) => ({ key: `${key}:${i}`, sides, coin: !!coin, results: Array.from({ length: n }, (_, k) => (coin ? k % 2 : 1 + (k % sides))) }));

  it("lands every die in the tray, none resting inside another, then stops drawing", () => {
    const tray = new ToyTrayScene(canvas);
    for (const key of ["a", "b", "c", "d", "e"]) {
      const groups = throwOf(key, [6, 3], [20, 1], [8, 2], [2, 2, true]);
      let settled = 0;
      tray.onSettled = () => settled++;
      tray.throw(groups, { reduced: true, speed: 1, color: "#d7ae63" });
      while (frames.length) frames.shift()!(0);
      expect(settled).toBe(1);
      const at = tray.positions();
      expect(at).toHaveLength(8);
      const plan = planTray(groups);
      for (const p of at) {
        expect(p.x).toBeGreaterThan(plan.bounds.minX);
        expect(p.x).toBeLessThan(plan.bounds.maxX);
        expect(p.z).toBeGreaterThan(plan.bounds.minZ);
        expect(p.z).toBeLessThan(plan.bounds.maxZ);
        expect(p.y).toBeLessThan(0.6);
      }
      for (let i = 0; i < at.length; i++) {
        for (let j = i + 1; j < at.length; j++) expect(at[i]!.distanceTo(at[j]!), `${key}: dice ${i} and ${j}`).toBeGreaterThan(0.4);
      }
    }
    tray.dispose();
  });

  it("clears the last throw for the next one, and frees its renderer and WebGL context on close", () => {
    const tray = new ToyTrayScene(canvas);
    tray.throw(throwOf("x", [6, 4]), { reduced: true, speed: 1, color: "#d7ae63" });
    tray.throw(throwOf("y", [12, 2]), { reduced: true, speed: 1, color: "#d7ae63" });
    expect(tray.positions()).toHaveLength(2);
    tray.dispose();
    expect(tray.positions()).toHaveLength(0);
    expect(made.at(-1)).toMatchObject({ disposed: 1, lost: 1 });
  });
});
