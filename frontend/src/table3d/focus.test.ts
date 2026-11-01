import { describe, expect, it } from "vitest";
import type { GameCard } from "../types/game";
import { matchHotkey, collisions } from "../game/hotkeys";
import { cameraKey, combatCardIds, frameBox, isCloseUp, type CamKeyContext } from "./focus";
import type { CameraPreset } from "./TableScene";

const ctx = (extra: Partial<CamKeyContext> = {}): CamKeyContext => ({
  me: "p1", players: ["p1", "p2", "p3"], hover: null, onTable: (id) => id.startsWith("bf"), stack: false, combat: false, ...extra,
});
const press = (id: string, cur: CameraPreset, back: CameraPreset, c: CamKeyContext) => cameraKey(id, cur, back, c);

describe("camera keys", () => {
  it("binds C, K and X to the card, stack and combat close-ups without stealing a key", () => {
    const key = (k: string) => matchHotkey({ key: k, ctrlKey: false, metaKey: false, shiftKey: false });
    expect([key("c"), key("k"), key("x")]).toEqual(["cam_focus", "cam_stack", "cam_combat"]);
    expect(key("f")).toBe("turn_over"); // F still turns a card over (UI_REFERENCE_STUDY §22)
    expect(collisions()).toEqual([]);
  });
  it("C zooms to the hovered card on the table and C again returns to the view you had", () => {
    const zoomed = press("cam_focus", { focus: "p2" }, "seat", ctx({ hover: "bf1" }));
    expect(zoomed).toEqual({ preset: { card: "bf1" }, back: { focus: "p2" } });
    expect(press("cam_focus", zoomed.preset, zoomed.back, ctx({ hover: "bf2" }))).toEqual({ preset: { focus: "p2" }, back: { focus: "p2" } });
  });
  it("C does nothing without a hovered card on the table (a hand card isn't one)", () => {
    expect(press("cam_focus", "seat", "seat", ctx()).preset).toBe("seat");
    expect(press("cam_focus", "seat", "seat", ctx({ hover: "hand1" })).preset).toBe("seat");
  });
  it("K and X frame the stack and the fight only when there is one", () => {
    expect(press("cam_stack", "seat", "seat", ctx()).preset).toBe("seat");
    expect(press("cam_stack", "overview", "seat", ctx({ stack: true }))).toEqual({ preset: { stack: true }, back: "overview" });
    expect(press("cam_combat", "seat", "seat", ctx()).preset).toBe("seat");
    expect(press("cam_combat", "seat", "seat", ctx({ combat: true })).preset).toEqual({ combat: true });
  });
  it("hopping between close-ups keeps the view you started from; Esc returns to it", () => {
    const a = press("cam_stack", "overview", "seat", ctx({ stack: true, combat: true }));
    const b = press("cam_combat", a.preset, a.back, ctx({ stack: true, combat: true }));
    expect(b).toEqual({ preset: { combat: true }, back: "overview" });
    expect(press("cam_combat", b.preset, b.back, ctx({ combat: true })).preset).toBe("overview");
    expect(press("escape", b.preset, b.back, ctx()).preset).toBe("overview");
    expect(press("escape", { focus: "p2" }, "seat", ctx()).preset).toEqual({ focus: "p2" }); // Esc only leaves a close-up
  });
  it("keeps the seat keys as they were", () => {
    expect(press("cam_player", "seat", "seat", ctx({ digit: 3 })).preset).toEqual({ focus: "p3" });
    expect(press("cam_player", "seat", "seat", ctx({ digit: 6 })).preset).toBe("seat");
    expect(press("cam_table", { card: "bf1" }, "seat", ctx()).preset).toBe("overview");
    expect(press("cam_reset", "overview", "seat", ctx()).preset).toBe("seat");
    expect(press("cam_focus_player", "seat", "seat", ctx({ player: "p2" })).preset).toEqual({ focus: "p2" });
    expect(press("cam_focus_player", "overview", "seat", ctx({ player: "p1" })).preset).toBe("seat");
  });
  it("knows its close-ups", () => {
    expect([{ card: "x" }, { stack: true }, { combat: true }].every((p) => isCloseUp(p as CameraPreset))).toBe(true);
    expect(["seat", "overview", { focus: "p2" }].some((p) => isCloseUp(p as CameraPreset))).toBe(false);
  });
});

describe("combatCardIds", () => {
  const card = (id: string, extra: Partial<GameCard>): GameCard => ({ id, owner: "p1", controller: "p1", zone: "p1:battlefield", face_down: false, hidden: true, ...extra }) as GameCard;
  it("collects attackers and blockers on the battlefield, nothing else", () => {
    const cards = {
      a: card("a", { attacking: { kind: "player", id: "p2" } }),
      b: card("b", { blocking: "a", zone: "p2:battlefield" }),
      c: card("c", {}),
      d: card("d", { attacking_without_target: "p2" }),
      gone: card("gone", { attacking: { kind: "player", id: "p2" }, zone: "p1:graveyard" }),
    };
    expect(combatCardIds({ cards })).toEqual(["a", "b", "d"]);
  });
});

describe("frameBox", () => {
  it("looks at the middle of the area from the viewer's side, and backs off for a bigger area", () => {
    const small = frameBox({ minX: -1, maxX: 1, minZ: -1, maxZ: 1 }, [0, 1]);
    expect(small.look).toEqual([0, 0, 0]);
    expect(small.pos[2]).toBeGreaterThan(0); // on my side (+z)
    expect(small.pos[1]).toBeGreaterThan(0);
    const big = frameBox({ minX: -6, maxX: 6, minZ: 2, maxZ: 4 }, [0, 1], { y: 1 });
    expect(big.look).toEqual([0, 1, 3]);
    const d = (f: typeof big) => Math.hypot(f.pos[0] - f.look[0], f.pos[1] - f.look[1], f.pos[2] - f.look[2]);
    expect(d(big)).toBeGreaterThan(d(small));
    expect(d(small)).toBeCloseTo(5.8); // one card: as close as C's card close-up
  });
});
