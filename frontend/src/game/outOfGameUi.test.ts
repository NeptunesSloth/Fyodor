import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createElement, type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { GameView } from "../types/game";
import { Hand } from "./Hand";
import { SeatButtons } from "./SeatButtons";
import { SeatPlate } from "./SeatPlate";
import { runSeatAction } from "./seatActions";

// Server rendering reads a zustand store's initial state, so the store these read is a plain value here (as turnDial.test.ts).
const { state, fakeStore, sent } = vi.hoisted(() => ({
  state: { game: { view: null as unknown, actingAs: null as string | null, selection: [] as string[], openBrowser: () => undefined } },
  fakeStore: <T extends object>(read: () => T) => Object.assign((select: (s: T) => unknown) => select(read()), { getState: read }),
  sent: [] as unknown[],
}));
vi.mock("../state/gameStore", async (original) => ({ ...(await original<object>()), useGame: fakeStore(() => state.game) }));
vi.mock("./seatIcons", async (original) => ({ ...(await original<object>()), seatIconUrl: (id: string) => `icon:${id}` }));
vi.mock("./actions", async (original) => ({
  ...(await original<object>()),
  send: (a: unknown) => { sent.push(a); return Promise.resolve(true); },
  draw: (player: string, count: number) => { sent.push({ type: "draw", player, count }); return Promise.resolve(true); },
}));

/** Ann (p1) and Bob (p2) still in; Cat (p3) conceded. `viewer`: whose browser this is. */
function table(viewer: string, conceded: string[] = ["p3"]): void {
  state.game.view = {
    viewer, seat_order: ["p1", "p2", "p3"],
    game: { id: "g", mode: "lan", host_seat: "p1", seats: { p1: {}, p2: {}, p3: {} }, night: { number: 1, result: null }, settings: {} },
    players: ["Ann", "Bob", "Cat"].map((name, i) => ({
      id: `p${i + 1}`, name, color: ["#c33", "#36c", "#3a3"][i], life: 40, resources: {}, commander_damage: {}, hand_count: 0,
      commanders: [{ key: `c${i + 1}`, name: `${name}'s commander` }],
    })),
    turn: { number: 4, active_player: "p1", phase: "main1" }, cards: {}, zones: {}, stack: [], log: [], searches: {},
    table: {},
    rules: { paused: false, conceded, lost: {}, priority: "p1", decision: null, controlled_by: null, acting_as: null, prefs: null, hints: {}, options: {} },
  } as unknown as GameView;
}

const html = (el: unknown, props: Record<string, unknown>) => renderToStaticMarkup(createElement(el as (p: Record<string, unknown>) => ReactNode, props));

describe("the 2D table stops inviting a player who is out to act", () => {
  beforeEach(() => {
    vi.stubGlobal("window", { innerWidth: 1600, innerHeight: 900, addEventListener() {}, removeEventListener() {}, setTimeout, clearTimeout });
    vi.stubGlobal("document", { documentElement: {}, querySelector: () => null, activeElement: null, body: { classList: { contains: () => false } } });
    sent.length = 0;
  });
  afterEach(() => vi.unstubAllGlobals());

  it("an empty hand no longer says \"press D to draw\" to a player who is out", () => {
    table("p3");
    expect(html(Hand, { player: "p3", me: "p3" })).not.toContain("press D to draw");
    table("p1");
    expect(html(Hand, { player: "p1", me: "p1" })).toContain("Hand is empty — press D to draw");
  });

  it("no Untap, Draw, Scry, Mill, Reveal or Mulligan buttons by the mat of a player who is out", () => {
    table("p3");
    expect(html(SeatButtons, {})).toBe("");
    table("p1");
    const still = html(SeatButtons, {});
    for (const id of ["untap", "draw", "scry", "mill", "reveal", "mulligan"]) expect(still).toContain(`data-testid="seat-btn-${id}"`);
  });

  it("a seat button pressed anyway (the 3D table's, a typed count) sends nothing", () => {
    table("p3");
    for (const id of ["untap", "draw", "scry", "mill", "reveal", "mulligan"] as const) runSeatAction(id, 2, "p3");
    expect(sent).toEqual([]);
    table("p1");
    runSeatAction("draw", 2, "p1");
    expect(sent).toEqual([{ type: "draw", player: "p1", count: 2 }]);
  });

  it("the plaques' life and counters read as values to a player who is out, not as controls", () => {
    table("p3");
    for (const player of ["p1", "p3"]) {
      const plate = html(SeatPlate, { player, me: "p3", open: false, onToggle: () => undefined, variant: "2d" });
      expect(plate).toMatch(new RegExp(`<button[^>]*data-testid="heart-${player}"[^>]*disabled`));
      expect(plate).toMatch(new RegExp(`<button[^>]*data-testid="poison-${player}"[^>]*disabled`));
      expect(plate).toMatch(new RegExp(`<button[^>]*data-testid="life-plus-${player}"[^>]*disabled`));
      expect(plate).not.toContain("Click to add 1");
      expect(plate).not.toContain("Click the left half");
      expect(plate).toMatch(new RegExp(`data-testid="seat-${player}"`)); // the way into the player panel stays
      expect(plate).not.toMatch(new RegExp(`<button[^>]*data-testid="seat-${player}"[^>]*disabled`));
    }
    table("p1");
    const live = html(SeatPlate, { player: "p3", me: "p1", open: false, onToggle: () => undefined, variant: "2d" });
    expect(live).not.toMatch(/<button[^>]*disabled/);
    expect(live).toContain("Click to add 1");
  });
});
