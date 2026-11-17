import { describe, expect, it } from "vitest";
import { SPECTATOR, type GameView, type NightProposal } from "../types/game";
import { DUMMIES_WIN, describeResult, overByRules, proposalSeat, showEliminated, stillIn, testEnding } from "./nightEnding";

const SEATS = ["p1", "p2", "p3"];

function view(over: { viewer?: string; mode?: "lan" | "local"; rules?: Record<string, unknown> | null; proposal?: Partial<NightProposal> | null; result?: unknown; left?: string[] } = {}): GameView {
  const rules = over.rules === null ? null : { conceded: [], lost: {}, winner: null, draw_reason: null, ...(over.rules ?? {}) };
  const proposal = over.proposal ? { by: "p1", by_name: "Ann", result_type: "single", winners: ["p1"], winner_names: ["Ann"], agreed: [], ...over.proposal } : null;
  return {
    viewer: over.viewer ?? "p1",
    seat_order: SEATS,
    players: SEATS.map((id, i) => ({ id, name: ["Ann", "Ben", "Cat"][i], left: (over.left ?? []).includes(id) })),
    rules,
    game: { id: "g", mode: over.mode ?? "lan", seats: { p1: {}, p2: {}, p3: {} }, night: { number: 1, proposal, result: over.result ?? null } },
  } as unknown as GameView;
}

const rulesResult = { by: "", by_name: "The rules", rules: "Ben lost (0 or less life)", voters: ["p1", "p2"] };

describe("who is still in", () => {
  it("drops players who lost, conceded or left the table", () => {
    expect(stillIn(view({ rules: { lost: { p2: "0 or less life" } } }))).toEqual(["p1", "p3"]);
    expect(stillIn(view({ rules: { conceded: ["p3"] }, left: ["p1"] }))).toEqual(["p2"]);
    expect(stillIn(view({ rules: null }))).toEqual(SEATS);
  });
  it("knows when the rules ended the game: a winner or a draw", () => {
    expect(overByRules(view())).toBe(false);
    expect(overByRules(view({ rules: { winner: "p1" } }))).toBe(true);
    expect(overByRules(view({ rules: { draw_reason: "Every player still in the game lost at the same time (104.4a)" } }))).toBe(true);
    expect(overByRules(view({ rules: null }))).toBe(false);
  });
});

describe("the eliminated flow", () => {
  it("shows for a player the engine eliminated while the game goes on", () => {
    for (const why of ["0 or less life", "10 poison counters", "21 combat damage from one commander", "drew from an empty library", "an effect"]) {
      expect(showEliminated(view({ viewer: "p2", rules: { lost: { p2: why } } }), "p2")).toBe(true);
    }
    expect(showEliminated(view({ viewer: "p2", rules: { conceded: ["p2"] } }), "p2")).toBe(true);
    expect(showEliminated(view({ viewer: "p1", rules: { lost: { p2: "0 or less life" } } }), "p1")).toBe(false);
  });
  it("gives way to the result once the rules ended the game or a result is recorded", () => {
    expect(showEliminated(view({ viewer: "p2", rules: { lost: { p2: "0 or less life", p3: "0 or less life" }, winner: "p1" } }), "p2")).toBe(false);
    expect(showEliminated(view({ viewer: "p2", rules: { lost: { p2: "x" }, draw_reason: "loop" } }), "p2")).toBe(false);
    expect(showEliminated(view({ viewer: "p2", rules: { lost: { p2: "x" } }, result: { result_type: "single", winners: ["p1"] } }), "p2")).toBe(false);
  });
  it("never shows for a spectator", () => {
    expect(showEliminated(view({ viewer: "__spectator__", rules: { lost: { p1: "x" } } }), "p1")).toBe(false);
  });
});

describe("the proposal bar", () => {
  it("is empty without a proposal or once the result is recorded", () => {
    expect(proposalSeat(view(), "p1")).toBeNull();
    expect(proposalSeat(view({ proposal: rulesResult, result: { result_type: "single" } }), "p1")).toBeNull();
  });

  it("asks each player who was in the game when it ended to confirm the rules result", () => {
    const over = { rules: { lost: { p2: "0 or less life", p3: "10 poison counters" }, winner: "p1" }, proposal: rulesResult };
    const ann = proposalSeat(view(over), "p1")!;
    expect(ann).toEqual({ what: "Ann wins", rules: "Ben lost (0 or less life)", waiting: ["p1", "p2"], mustAnswer: true, canWithdraw: false });
    // Ben lost in the deciding action but was in the game when it ended: he confirms too
    expect(proposalSeat(view({ ...over, viewer: "p2" }), "p2")!.mustAnswer).toBe(true);
    // Cat was out before: she watches
    expect(proposalSeat(view({ ...over, viewer: "p3" }), "p3")!.mustAnswer).toBe(false);
    // once Ann confirmed, she waits for Ben
    const confirmed = proposalSeat(view({ ...over, proposal: { ...rulesResult, agreed: ["p1"] } }), "p1")!;
    expect(confirmed.mustAnswer).toBe(false);
    expect(confirmed.waiting).toEqual(["p2"]);
    expect(proposalSeat(view({ ...over, viewer: "__spectator__" }), "p1")!.mustAnswer).toBe(false);
  });

  it("lets the one person at a hot-seat table settle the rules result from any seat", () => {
    const v = view({ mode: "local", rules: { lost: { p2: "x", p3: "y" }, winner: "p1" }, proposal: rulesResult });
    expect(proposalSeat(v, "p3")!.mustAnswer).toBe(true);
  });

  it("reads a rules draw", () => {
    const v = view({ rules: { lost: { p1: "x", p2: "y" }, draw_reason: "104.4a" }, proposal: { ...rulesResult, result_type: "draw", winners: [], winner_names: [], rules: "104.4a" } });
    expect(proposalSeat(v, "p1")!.what).toBe("a draw");
  });

  it("keeps a player's own proposal exactly as before: every player still in agrees, the proposer may withdraw", () => {
    const v = view({ rules: { lost: { p3: "x" } }, proposal: { by: "p1", winners: ["p2"], winner_names: ["Ben"], agreed: ["p1"] } });
    expect(proposalSeat(v, "p1")).toEqual({ what: "Ben wins", rules: null, waiting: ["p2"], mustAnswer: false, canWithdraw: true });
    expect(proposalSeat(view({ ...{ rules: { lost: { p3: "x" } } }, viewer: "p2", proposal: { by: "p1", agreed: ["p1"] } }), "p2")!.mustAnswer).toBe(true);
    expect(proposalSeat(view({ rules: { lost: { p3: "x" } }, viewer: "p3", proposal: { by: "p1", agreed: ["p1"] } }), "p3")!.mustAnswer).toBe(false);
    expect(proposalSeat(view({ rules: null, proposal: { by: "p2" } }), "p1")!.mustAnswer).toBe(true);
  });

  it("describes every result type", () => {
    expect(describeResult({ result_type: "single", winner_names: ["Ann"] })).toBe("Ann wins");
    expect(describeResult({ result_type: "multiple", winner_names: ["Ann", "Ben"] })).toBe("Ann and Ben win");
    expect(describeResult({ result_type: "draw", winner_names: [] })).toBe("a draw");
    expect(describeResult({ result_type: "no_result", winner_names: [] })).toBe("no result");
  });
});

describe("the test-table ending (target dummies)", () => {
  // Ann tests her deck against Ben and Cat, two target dummies
  const table = (rules: Record<string, unknown>, extra: { viewer?: string; dummies?: string[] } = {}) => {
    const v = view({ rules, viewer: extra.viewer });
    const dummies = extra.dummies ?? ["p2", "p3"];
    return { ...v, turn: { number: 3 }, players: v.players.map((p) => ({ ...p, dummy: dummies.includes(p.id) })) } as unknown as GameView;
  };

  it("shows nothing while the test goes on, to a spectator, or at a table with no dummy", () => {
    expect(testEnding(table({}), "p1")).toBeNull();
    expect(testEnding(table({ lost: { p1: "0 or less life" } }, { viewer: SPECTATOR }), "p1")).toBeNull();
    expect(testEnding(table({ lost: { p1: "0 or less life" } }, { dummies: [] }), "p1")).toBeNull();
    expect(testEnding(view({ rules: null }), "p1")).toBeNull();
  });

  it("says how you lost, and who won when the rules ended it", () => {
    const one = testEnding(table({ lost: { p1: "0 or less life" }, winner: "p2" }, { dummies: ["p2"] }), "p1")!;
    expect(one).toMatchObject({ kind: "lost", title: "You lost", line: "You lost: 0 or less life. Ben wins." });
    const standing = testEnding(table({ lost: { p1: "0 or less life" } }), "p1")!; // (two dummies: no winner, the test is still over)
    expect(standing.line).toBe("You lost: 0 or less life. The dummies are still standing.");
    expect(testEnding(table({ conceded: ["p1"] }), "p1")!.line).toBe("You conceded. The dummies are still standing.");
    // the server ends a test with only dummies left (app/rules/dummy_ending.py): no endless turns of theirs; it reads as their win
    const over = testEnding(table({ lost: { p1: "0 or less life" }, draw_reason: DUMMIES_WIN }), "p1")!;
    expect(over).toMatchObject({ kind: "lost", line: "You lost: 0 or less life. Only target dummies are left in the game: the dummies win." });
  });

  it("names the dummy defeated, or a draw, and keys each ending apart", () => {
    expect(testEnding(table({ winner: "p1", lost: { p2: "0 or less life" } }, { dummies: ["p2"] }), "p1")!.title).toBe("Ben defeated");
    expect(testEnding(table({ winner: "p1" }), "p1")!.title).toBe("Target dummies defeated");
    expect(testEnding(table({ draw_reason: "Every player lost at once" }), "p1")).toMatchObject({ kind: "draw", line: "Every player lost at once." });
    const a = testEnding(table({ lost: { p1: "0 or less life" } }), "p1")!.key;
    const b = testEnding(table({ lost: { p1: "drew from an empty library" } }), "p1")!.key;
    expect(a).not.toBe(b);
  });

  it("covers a test opponent the server plays for too", () => {
    const withBot = (rules: Record<string, unknown>) => {
      const v = table(rules, { dummies: [] });
      return { ...v, players: v.players.map((p) => ({ ...p, bot: p.id === "p2" ? "simple" : null })) } as unknown as GameView;
    };
    expect(testEnding(withBot({}), "p1")).toBeNull();
    expect(testEnding(withBot({ lost: { p1: "0 or less life" }, winner: "p2" }), "p1")).toMatchObject({ kind: "lost", line: "You lost: 0 or less life. Ben wins." });
    expect(testEnding(withBot({ winner: "p1", lost: { p2: "0 or less life" } }), "p1")).toMatchObject({ kind: "won", title: "Ben defeated",
      line: "Every opponent is out. Start over deals a new game." });
    expect(testEnding(withBot({ conceded: ["p1"] }), "p1")!.line).toBe("You conceded. Your opponents are still standing.");
  });

  it("leaves a LAN game night with a bot the host seated to the night's own result flow (-- LAN bots --)", () => {
    // (the bot holds its seat with the server's token: claimed; a Sandbox opponent's seat is open)
    const night = (rules: Record<string, unknown>) => {
      const v = table(rules, { dummies: [] });
      return { ...v, players: v.players.map((p) => ({ ...p, bot: p.id === "p2" ? "simple" : null })),
        game: { ...v.game, seats: { p1: { claimed: true }, p2: { claimed: true }, p3: { claimed: true } } } } as unknown as GameView;
    };
    expect(testEnding(night({ lost: { p1: "0 or less life" }, winner: "p2" }), "p1")).toBeNull();
    expect(testEnding(night({ conceded: ["p1"] }), "p1")).toBeNull();
    expect(showEliminated(night({ conceded: ["p1"] }), "p1")).toBe(true); // (out while the others play on: the hub, as at any night)
  });

  it("takes the place of the Eliminated hub", () => {
    expect(showEliminated(table({ lost: { p1: "0 or less life" } }), "p1")).toBe(false);
    expect(showEliminated(table({ lost: { p1: "0 or less life" } }, { dummies: [] }), "p1")).toBe(true);
  });
});
