import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { DecisionView, GameView } from "../../types/game";
import { answerByClick, DecisionPanel, legalClass } from "../rules/RulesHud";
import { useTargeting } from "./store";

// Server rendering reads a zustand store's initial state, so the stores the panel reads are plain values here.
const { state, fakeStore } = vi.hoisted(() => ({
  state: { game: { view: null as unknown, actingAs: null as string | null, selection: [] as string[], hover: null as string | null }, prefs: { choiceWheel: true, renderer: "2d" } },
  fakeStore: <T extends object>(read: () => T) => Object.assign((select: (s: T) => unknown) => select(read()), { getState: read }),
}));
vi.mock("../../state/gameStore", async (original) => ({ ...(await original<object>()), useGame: fakeStore(() => state.game) }));
vi.mock("../../state/prefs", async (original) => ({ ...(await original<object>()), usePrefs: fakeStore(() => state.prefs) }));

const goblin = (id: string, extra: object = {}) => ({ id, name: "Goblin", zone: "p2:battlefield", owner: "p2", controller: "p2", card_id: null, is_token: true, face: 0,
  token: { name: "Goblin", power: "1", toughness: "1", type_line: "Token Creature — Goblin" }, ...extra });

function show(decision: Partial<DecisionView>, highlights = "on"): string {
  state.game.view = {
    viewer: "p1", seat_order: ["p1", "p2"], game: { mode: "lan", host_seat: "p1", seats: { p1: {}, p2: {} } },
    players: [{ id: "p1", name: "Alice", color: "#c33", life: 40 }, { id: "p2", name: "Bob", color: "#36c", life: 31 }],
    turn: { active_player: "p1" },
    cards: { swords: { id: "swords", name: "Swords to Plowshares", zone: "p1:hand", owner: "p1", controller: "p1", card_id: null, face: 0 },
      g1: goblin("g1"), g2: goblin("g2", { tapped: true }), g3: goblin("g3") },
    zones: { "p1:hand": ["swords"], "p2:battlefield": ["g1", "g2", "g3"] }, stack: [], log: [],
    rules: { decision: { id: "d1", player: "p1", source_id: null, min_choices: 1, max_choices: 1, rememberable: false, cancelable: true, ...decision }, hints: {}, options: { highlights }, prefs: null },
  } as unknown as GameView;
  return renderToStaticMarkup(createElement(DecisionPanel));
}

const options = ["g1", "g2", "g3", "p2"].map((id) => ({ id, label: id === "p2" ? "Bob" : "Goblin", card_id: id === "p2" ? null : id, group: null }));

describe("the targeting bar replaces the panel for cards and players", () => {
  beforeEach(() => {
    vi.stubGlobal("window", { innerWidth: 1600, innerHeight: 900, addEventListener() {}, removeEventListener() {} });
    vi.stubGlobal("document", { documentElement: {}, querySelector: () => null, activeElement: null, body: { classList: { contains: () => false } }, createElement: () => ({ getContext: () => null }) });
    vi.stubGlobal("getComputedStyle", () => ({ zoom: "1" }));
  });
  afterEach(() => vi.unstubAllGlobals());

  it("shows the source, the words, a tray button per candidate (same test ids and names as the panel's) and Cancel", () => {
    const html = show({ kind: "choose_one", prompt: "Choose a target for Lightning Bolt", options });
    expect(html).toContain('data-targeting=""');
    expect(html).toContain('data-testid="decision-panel"');
    expect(html).toContain("Choose target creature or player");
    for (const o of options) expect(html).toContain(`data-testid="option-${o.id}"`);
    expect(html).toContain('aria-label="Goblin"');
    expect(html).toContain('aria-label="Bob"');
    expect(html).toContain('data-testid="option-cancel"');
    expect(html).not.toContain('data-testid="decision-done"'); // one choice answers at once
    expect(html).toContain("tapped"); // the tapped Goblin is told apart from the other two
    expect(html).toContain("tgt-fan"); // the two untapped ones fan as a pile
  });

  it("a multi-choice has its count and Done; with highlights off the list panel stays", () => {
    const multi = show({ kind: "choose_cards", prompt: "Choose up to 2 targets for Grind", min_choices: 0, max_choices: 2, options });
    expect(multi).toContain('data-testid="decision-done"');
    expect(multi).toContain("0 of 2 chosen");
    expect(multi).toContain("Done (none)");
    const off = show({ kind: "choose_one", prompt: "Choose a target for Lightning Bolt", options }, "off");
    expect(off).not.toContain("data-targeting");
    expect(off).toContain('data-testid="option-g1"');
  });

  it("a click on a candidate on the table chooses it in a multi-choice (then Done), and the candidates are marked legal", () => {
    show({ kind: "choose_cards", prompt: "Choose up to 2 targets for Grind", min_choices: 0, max_choices: 2, options });
    const v = state.game.view as GameView;
    expect(legalClass(v, "g1", "p1")).toBe("rules-target");
    useTargeting.getState().reset("d1");
    expect(answerByClick(v, "g1", "p1")).toBe(true);
    expect(answerByClick(v, "p2", "p1")).toBe(true);
    expect(useTargeting.getState().picked.map((p) => p.opt)).toEqual(["g1", "p2"]);
    expect(answerByClick(v, "g1", "p1")).toBe(true); // again: un-chosen
    expect(useTargeting.getState().picked.map((p) => p.opt)).toEqual(["p2"]);
    expect(answerByClick(v, "swords", "p1")).toBe(false); // not a candidate
  });
});
