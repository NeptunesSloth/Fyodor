import { beforeEach, describe, expect, it, vi } from "vitest";
import type { DecisionView, GameView } from "../../types/game";

const { state } = vi.hoisted(() => ({ state: { view: null as unknown, actingAs: null as string | null } }));
vi.mock("../../state/gameStore", async (original) => ({
  ...(await original<object>()),
  useGame: Object.assign(() => null, { getState: () => state }),
}));
vi.mock("../../components/Toasts", () => ({ toast: vi.fn() }));

import { toast } from "../../components/Toasts";
import {
  blockDeclarations, blockDrop, blockHint, blockRefusal, blockSummary, liveBlocks, menaceShort, spotForZone, useBlockDraft, withBlock,
  withoutBlock,
} from "./blockDraft";

/** Bob blocks: Alice attacks with Serra Angel (flying) and Goblin War Drums-ish menace Goblin; Bob has bears, a Giant Spider (reach),
 * two Soldier tokens and a tapped Elf that isn't offered. */
const decision: DecisionView = {
  id: "d1", player: "p2", kind: "declare_blockers", prompt: "Declare blockers", source_id: null,
  options: [
    { id: "b:bears", label: "Grizzly Bears", card_id: "bears" },
    { id: "b:spider", label: "Giant Spider", card_id: "spider" },
    { id: "b:s1", label: "Soldier", card_id: "s1" },
    { id: "b:s2", label: "Soldier", card_id: "s2" },
    { id: "a:angel", label: "Serra Angel", card_id: "angel" },
    { id: "a:gob", label: "Goblin", card_id: "gob" },
  ],
  min_choices: 0, max_choices: 4,
  display: {
    kind: "blockers",
    stats: { bears: { pt: "2/2", keywords: [] }, spider: { pt: "2/4", keywords: ["reach"] }, s1: { pt: "1/1", keywords: [] },
      s2: { pt: "1/1", keywords: [] }, angel: { pt: "4/4", keywords: ["flying"] }, gob: { pt: "2/1", keywords: ["menace"] } },
  },
};

beforeEach(() => {
  state.view = {
    viewer: "p2", players: [{ id: "p1", name: "Alice", color: "#c33" }, { id: "p2", name: "Bob", color: "#36c" }],
    seat_order: ["p1", "p2"], game: { seats: {} },
    cards: {
      angel: { id: "angel", controller: "p1", zone: "p1:battlefield" }, gob: { id: "gob", controller: "p1", zone: "p1:battlefield" },
      bears: { id: "bears", controller: "p2", zone: "p2:battlefield" }, elf: { id: "elf", controller: "p2", zone: "p2:battlefield", tapped: true },
      land: { id: "land", controller: "p2", zone: "p2:battlefield" },
    },
    rules: { decision },
  } as unknown as GameView;
  state.actingAs = "p2";
  useBlockDraft.setState({ decision: null, plan: {}, hint: null });
  vi.mocked(toast).mockClear();
});

describe("the block plan (playtest nov 18)", () => {
  it("assigns, adds a second attacker, takes one back, and declares one line per pair", () => {
    let plan = withBlock({}, "b:spider", "a:angel");
    plan = withBlock(plan, "b:spider", "a:gob", true);
    expect(plan).toEqual({ "b:spider": ["a:angel", "a:gob"] });
    expect(blockDeclarations(plan)).toEqual([{ blocker_id: "spider", attacker_id: "angel" }, { blocker_id: "spider", attacker_id: "gob" }]);
    expect(withBlock(plan, "b:spider", "a:gob")).toEqual({ "b:spider": ["a:gob"] }); // (no Shift: instead)
    expect(withoutBlock(plan, "b:spider", "a:angel")).toEqual({ "b:spider": ["a:gob"] });
    expect(withoutBlock({ "b:bears": ["a:gob"] }, "b:bears", "a:gob")).toEqual({});
    expect(withBlock(plan, "b:spider", "")).toEqual({});
  });

  it("hints only flying (no flying or reach), and notes a menace attacker blocked by one", () => {
    expect(blockRefusal(decision, "b:bears", "a:angel")).toBe("flying");
    expect(blockRefusal(decision, "b:spider", "a:angel")).toBeNull();
    expect(blockRefusal(decision, "b:bears", "a:gob")).toBeNull(); // (menace is the whole declaration's: the server judges it)
    expect(blockRefusal({ ...decision, display: { kind: "blockers" } }, "b:bears", "a:angel")).toBeNull(); // an older table: no stats, no hint
    expect(menaceShort(decision, { "b:bears": ["a:gob"] })).toEqual(["a:gob"]);
    expect(menaceShort(decision, { "b:bears": ["a:gob"], "b:s1": ["a:gob"] })).toEqual([]);
  });

  it("summarises, numbering creatures of one name", () => {
    expect(blockSummary(decision, {})).toBe("");
    expect(blockSummary(decision, { "b:s1": ["a:gob"], "b:s2": ["a:gob"], "b:spider": ["a:angel"] })).toBe("3 blocking · Serra Angel, Goblin ×2");
  });
});

describe("drag onto an attacker (playtest nov 18)", () => {
  it("a drop on an attacker blocks it (Shift: as well), refuses flying, and a drop home unassigns", () => {
    expect(blockDrop(["bears"], "gob", false)).toBe(true);
    expect(useBlockDraft.getState().plan).toEqual({ "b:bears": ["a:gob"] });
    expect(liveBlocks(state.view as GameView)).toEqual({ "b:bears": ["a:gob"] });
    expect(blockDrop(["bears"], "angel", true)).toBe(true); // flying: refused, named in a toast
    expect(useBlockDraft.getState().plan).toEqual({ "b:bears": ["a:gob"] });
    expect(toast).toHaveBeenCalledWith("Grizzly Bears (flying) can't block Serra Angel", "info");
    expect(blockDrop(["spider"], "angel", false)).toBe(true);
    expect(blockDrop(["spider"], "gob", true)).toBe(true);
    expect(useBlockDraft.getState().plan["b:spider"]).toEqual(["a:angel", "a:gob"]);
    expect(blockDrop(["spider"], "home", false)).toBe(true);
    expect(useBlockDraft.getState().plan).toEqual({ "b:bears": ["a:gob"] });
    expect(blockDrop(["s1"], "home", false)).toBe(false); // not blocking: a plain move in the row
    expect(blockDrop(["s1"], "board", false)).toBe(true); // a near miss on the attacker's board: nothing moves
  });

  it("a gang block: several dragged creatures onto one attacker", () => {
    expect(blockDrop(["s1", "s2", "bears"], "angel", false)).toBe(true);
    expect(useBlockDraft.getState().plan).toEqual({});
    expect(blockHint(["s1", "s2", "spider"], "angel", false)).toEqual({ text: "Block Serra Angel with 1", kind: "block" });
    expect(blockDrop(["s1", "s2"], "gob", false)).toBe(true);
    expect(useBlockDraft.getState().plan).toEqual({ "b:s1": ["a:gob"], "b:s2": ["a:gob"] });
  });

  it("captions: block, also block, can't (flying, tapped), home", () => {
    expect(blockHint(["bears"], "gob", false)).toEqual({ text: "Block Goblin", kind: "block" });
    expect(blockHint(["bears"], "angel", false)).toEqual({ text: "Can't block Serra Angel: flying", kind: "refuse" });
    expect(blockHint(["bears"], null, false)).toEqual({ text: "Drag onto an attacker to block", kind: "home" });
    blockDrop(["spider"], "gob", false);
    expect(blockHint(["spider"], "angel", true)).toEqual({ text: "Also block Serra Angel", kind: "block" });
    expect(blockHint(["spider"], "angel", false)).toEqual({ text: "Block Serra Angel", kind: "block" });
    expect(blockHint(["spider"], "home", false)).toEqual({ text: "Back in your row: doesn't block", kind: "home" });
    expect(blockHint(["elf"], "angel", false)).toEqual({ text: "Can't block: tapped", kind: "refuse" });
    expect(blockDrop(["elf"], "angel", false)).toBe(true); // (not onto Alice's board)
    expect(blockDrop(["land"], "board", false)).toBe(false); // not a creature on an attacker: the drag as always
  });

  it("is only the deciding player's, and only for this decision", () => {
    state.actingAs = "p1";
    expect(blockDrop(["bears"], "gob", false)).toBe(false);
    expect(blockHint(["bears"], "gob", false)).toBeNull();
    useBlockDraft.setState({ decision: "old", plan: { "b:bears": ["a:gob"] } });
    expect(liveBlocks(state.view as GameView)).toEqual({});
  });

  it("names the spot for a zone: my board home, the attacker's board, elsewhere nothing", () => {
    const v = state.view as GameView;
    expect(spotForZone(v, decision, "p2:battlefield")).toBe("home");
    expect(spotForZone(v, decision, "p1:battlefield")).toBe("board");
    expect(spotForZone(v, decision, "p1:graveyard")).toBeNull();
    expect(spotForZone(v, decision, null)).toBeNull();
  });
});
