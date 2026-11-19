import { describe, expect, it } from "vitest";
import type { GameResult, Outcome, ResultPlayer } from "../services/pod";
import { OUTCOME_WORD, groupByNight, nightKey, podSummary, signatureCommanders, splitBot } from "./podStatsBits";

const seat = (name: string, commanders: string[], outcome: Outcome = "loss"): ResultPlayer =>
  ({ seat: name.toLowerCase(), player_id: `id-${name}`, name, deck_key: null, deck_name: null, commanders, outcome });
/** A local date and time as the API's ISO string. */
const at = (day: number, hour: number) => new Date(2026, 10, day, hour, 30).toISOString();
const game = (n: number, recorded: string, players: ResultPlayer[], over: Partial<GameResult> = {}): GameResult => ({
  id: `r${n}`, number: n, game_id: `g${n}`, result_type: "single", table_name: "", format: "commander", started_at: null,
  recorded_at: recorded, duration_seconds: null, turns: 5, notes: "", players,
  winners: players.filter((p) => p.outcome === "win").map((p) => p.name), ...over,
});

describe("signatureCommanders", () => {
  it("picks each player's most played commander, a tie going to the most recent", () => {
    const results = [
      game(4, at(3, 21), [seat("Ann", ["Krenko, Mob Boss"], "win"), seat("Ben", ["Atraxa, Praetors' Voice"])]),
      game(3, at(3, 20), [seat("Ann", ["Meren of Clan Nel Toth"]), seat("Ben", ["Kraum, Ludevic's Opus", "Tymna the Weaver"], "win")]),
      game(2, at(2, 20), [seat("Ann", ["Meren of Clan Nel Toth"], "win"), seat("Ben", ["Kraum, Ludevic's Opus", "Tymna the Weaver"])]),
      game(1, at(2, 19), [seat("Ann", ["Krenko, Mob Boss"], "win"), seat("Cy", [])]),
    ];
    const sig = signatureCommanders(results);
    expect(sig.get("id-Ann")).toEqual(["Krenko, Mob Boss"]); // 2 and 2: Krenko was played last
    expect(sig.get("id-Ben")).toEqual(["Kraum, Ludevic's Opus", "Tymna the Weaver"]); // partners stay together
    expect(sig.has("id-Cy")).toBe(false); // never had a commander recorded
  });
});

describe("game nights", () => {
  it("counts a game after midnight for the night before", () => {
    expect(nightKey(at(2, 23))).toBe("2026-11-02");
    expect(nightKey(at(3, 1))).toBe("2026-11-02");
    expect(nightKey(at(3, 6))).toBe("2026-11-03");
  });

  it("groups results into nights, newest first, with the night's wins", () => {
    const nights = groupByNight([
      game(5, at(9, 22), [seat("Ann", [], "win"), seat("Ben", [])]),
      game(4, at(3, 2), [seat("Ann", []), seat("Ben", [], "win")]),
      game(3, at(2, 23), [seat("Ann", []), seat("Ben", [], "win")]),
      game(2, at(2, 21), [seat("Ann", [], "draw"), seat("Ben", [], "draw")], { result_type: "draw", winners: [] }),
      game(1, at(2, 20), [seat("Ann", [], "win"), seat("Ben", [])]),
    ]);
    expect(nights.map((n) => [n.key, n.games.map((g) => g.number)])).toEqual([["2026-11-09", [5]], ["2026-11-02", [4, 3, 2, 1]]]);
    expect(nights[1]!.tally).toEqual([["Ben", 2], ["Ann", 1]]); // a draw counts for nobody
    expect(nights[1]!.label).toContain("2026");
  });
});

describe("podSummary and outcome words", () => {
  it("says how many games and players, and when the last game was", () => {
    const results = [game(2, at(2, 22), [seat("Ann", []), seat("Ben", [])]), game(1, at(2, 20), [seat("Ann", []), seat("Cy", [])])];
    expect(podSummary(results)).toEqual({ games: "2 games", players: 3, last: results[0]!.recorded_at });
    expect(podSummary(results, 2).games).toBe("2+ games"); // the list was cut at its limit
    expect(podSummary([]).last).toBeNull();
    expect(OUTCOME_WORD.win).toBe("Won");
  });
});

describe("splitBot", () => {
  it("shows a recorded bot once, marked as a bot; people's names stay as they are", () => {
    expect(splitBot("Bot (bot)")).toEqual({ name: "Bot", bot: true });
    expect(splitBot("Bot 2 (bot)")).toEqual({ name: "Bot 2", bot: true });
    expect(splitBot("Alice")).toEqual({ name: "Alice", bot: false });
    expect(splitBot("(bot)")).toEqual({ name: "(bot)", bot: false });
    expect(splitBot("Robert (Bob)")).toEqual({ name: "Robert (Bob)", bot: false });
  });
});
