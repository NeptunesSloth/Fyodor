import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { DecisionView, GameView } from "../../types/game";
import { DecisionPanel } from "./RulesHud";

// Server rendering reads a zustand store's initial state, so the two stores the panel reads are plain values here.
const { state, fakeStore } = vi.hoisted(() => ({
  state: { game: { view: null as unknown, actingAs: null as string | null }, prefs: { choiceWheel: true } },
  fakeStore: <T extends object>(read: () => T) => Object.assign((select: (s: T) => unknown) => select(read()), { getState: read }),
}));
vi.mock("../../state/gameStore", async (original) => ({ ...(await original<object>()), useGame: fakeStore(() => state.game) }));
vi.mock("../../state/prefs", async (original) => ({ ...(await original<object>()), usePrefs: fakeStore(() => state.prefs) }));

const COLORS = ["White", "Blue", "Black", "Red", "Green"].map((c) => ({ id: c, label: c, card_id: null }));

function show(decision: DecisionView, viewer = "p1"): string {
  state.game.view = {
    viewer, seat_order: ["p1", "p2"], game: { mode: "lan", host_seat: "p1", seats: { p1: {}, p2: {} } },
    players: [{ id: "p1", name: "Alice", color: "#c33" }, { id: "p2", name: "Bob", color: "#36c" }],
    turn: { active_player: "p1" }, cards: {}, zones: {}, stack: [], log: [],
    rules: { decision, hints: {}, options: {}, prefs: null },
  } as unknown as GameView;
  return renderToStaticMarkup(createElement(DecisionPanel));
}

const colorChoice = (patch: Partial<DecisionView> = {}): DecisionView => ({
  id: "d1", player: "p1", kind: "choose_one", prompt: "Prism: choose a color", source_id: null, options: COLORS,
  min_choices: 1, max_choices: 1, rememberable: false, cancelable: false, public_choice: true, ...patch,
});

describe("DecisionPanel and the public choice wheel", () => {
  beforeEach(() => {
    vi.stubGlobal("window", { innerWidth: 1600, innerHeight: 900, addEventListener() {}, removeEventListener() {} });
    vi.stubGlobal("document", { documentElement: {}, querySelector: () => null, activeElement: null });
    vi.stubGlobal("getComputedStyle", () => ({ zoom: "1" }));
    state.prefs.choiceWheel = true;
  });
  afterEach(() => vi.unstubAllGlobals());

  it("shows a public choice on the wheel, centered, with the prompt and the way back to the list", () => {
    const html = show(colorChoice());
    expect(html).toContain('data-testid="choice-wheel"');
    expect(html).toContain("left:800px;top:450px"); // no pointer seen yet: the middle of the screen
    expect(html).toContain('data-testid="wheel-option-Blue"');
    expect(html).toContain("Prism: choose a color");
    expect(html).toContain('data-testid="wheel-list"');
    expect(html).not.toContain('data-testid="decision-panel"');
  });

  it("keeps the list when the wheel is turned off in Settings", () => {
    state.prefs.choiceWheel = false;
    const html = show(colorChoice());
    expect(html).not.toContain("choice-wheel");
    expect(html).toContain('data-testid="option-Blue"');
  });

  it("keeps the list for a choice that isn't public or isn't a single pick", () => {
    expect(show(colorChoice({ public_choice: false }))).toContain('data-testid="decision-panel"');
    expect(show(colorChoice({ kind: "choose_cards", max_choices: 2 }))).toContain('data-testid="decision-panel"');
  });

  it("shows other players only who is choosing", () => {
    const html = show({ id: "d1", player: "p1", kind: "waiting", prompt: "Alice is making a choice", source_id: null,
      public: { type: "PLAYER_MAKING_CHOICE", chooser: "Alice" } }, "p2");
    expect(html).toContain('data-testid="decision-waiting"');
    expect(html).not.toContain("choice-wheel");
  });
});
