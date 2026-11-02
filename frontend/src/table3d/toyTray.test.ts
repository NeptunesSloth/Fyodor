import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { dieShape } from "./dice";
import { ToyTrayScene, planTray, type TrayGroup } from "./toyTray";

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
const radius = (g: { sides: number; coin: boolean }) => (g.coin ? 0.3 : dieShape(g.sides).radius);

/** Where DiceTray (table3d/dice.ts) puts die i of n as it leaves the hand: four abreast, rows behind. */
function spawn(plan: ReturnType<typeof planTray>, lane: number, r: number, i: number, n: number) {
  const { from } = plan.lanes[lane]!;
  const step = r * 2 + 0.15;
  const row = Math.floor(i / 4);
  const inRow = Math.min(4, n - row * 4);
  return { x: from.x + ((i % 4) - (inRow - 1) / 2) * step, z: from.z + row * step };
}

describe("the 3D dice & toys tray: lanes", () => {
  it("gives each kind of die its own lane, inside the tray, as the dice leave the hand", () => {
    for (const groups of [[group(6, 3), group(20, 1)], [group(4, 4), group(6, 4), group(8, 4)], [group(20, 8), group(6, 2, true)], [group(12, 1)]]) {
      const plan = planTray(groups);
      const spans = groups.map((g, lane) => {
        const r = radius(g);
        const xs = g.results.map((_, i) => spawn(plan, lane, r, i, g.results.length));
        for (const p of xs) {
          expect(p.x - r).toBeGreaterThan(plan.bounds.minX);
          expect(p.x + r).toBeLessThan(plan.bounds.maxX);
          expect(p.z + r).toBeLessThan(plan.bounds.maxZ);
          expect(p.z - r).toBeGreaterThan(plan.bounds.minZ);
        }
        // thrown straight down its lane, toward the far rim
        const target = plan.lanes[lane]!.land(0, 1);
        expect(target.x).toBeCloseTo(plan.lanes[lane]!.from.x);
        expect(target.z).toBeLessThan(plan.lanes[lane]!.from.z);
        return [Math.min(...xs.map((p) => p.x)) - r, Math.max(...xs.map((p) => p.x)) + r] as const;
      });
      for (let i = 1; i < spans.length; i++) expect(spans[i]![0]).toBeGreaterThan(spans[i - 1]![1]);
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
    const ctx2d = new Proxy({}, { get: () => () => ({ addColorStop() {} }), set: () => true });
    vi.stubGlobal("document", { createElement: () => ({ width: 0, height: 0, getContext: () => ctx2d }) });
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
