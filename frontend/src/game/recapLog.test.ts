import { describe, expect, it } from "vitest";
import type { GameView, LogEntryView } from "../types/game";
import { recapSections } from "./recapLog";

let seq = 0;
const line = (turn: number, actor: string | null, kind: string, t: string): LogEntryView =>
  ({ seq: ++seq, ts: 0, turn, phase: "main1", actor, kind, parts: [{ t }] }) as LogEntryView;

const view = (now: number, active: string, log: LogEntryView[]) => ({
  turn: { number: now, active_player: active, phase: "main1" },
  players: [{ id: "p1", name: "Alice", life_history: [{ turn: 3, before: 40, after: 35 }] }, { id: "p2", name: "Bob", life_history: [] }, { id: "p3", name: "Cy", life_history: [] }],
  log,
}) as unknown as GameView;

const LOG = [
  line(1, "p3", "turn", "Turn 1: Alice"),
  line(1, "p1", "action", "Alice played Mountain"),
  line(2, "p1", "turn", "Turn 2: Bob"),
  line(2, "p2", "action", "Bob drew a card"),
  line(2, "p2", "action", "Bob played Forest"),
  line(3, "p2", "turn", "Turn 3: Cy"),
  line(3, "p3", "phase", "— Precombat main —"),
  line(3, "p3", "action", "Cy cast Llanowar Elves"),
  line(3, "p3", "mana", "Cy paid {G} for Llanowar Elves (tapped Forest)"),
  line(3, "p3", "action", "Cy tapped Grizzly Bears"),
  line(3, "p3", "action", "Cy attacks Alice with Grizzly Bears"),
  line(3, "p1", "action", "Alice declared no blockers"),
  line(3, "p3", "combat", "Combat damage: Alice takes 5"),
  line(4, "p3", "turn", "Turn 4: Alice"),
];

describe("turn recap", () => {
  it("gathers the other players' turns since mine, one section each, with my life change", () => {
    const s = recapSections(view(4, "p1", LOG), "p1");
    expect(s.map((x) => [x.turn, x.who])).toEqual([[2, "Bob"], [3, "Cy"]]);
    expect(s[0]!.lines).toEqual(["played Forest"]);
    expect(s[1]!.lines).toEqual(["cast Llanowar Elves", "attacks Alice with Grizzly Bears", "Combat damage: Alice takes 5"]);
    expect(s[1]!.life).toBe(-5);
  });

  it("shows a finished turn while another player's is on, and nothing already dismissed", () => {
    expect(recapSections(view(3, "p3", LOG.slice(0, 6)), "p1").map((x) => x.who)).toEqual(["Bob"]);
    expect(recapSections(view(4, "p1", LOG), "p1", 3)).toEqual([]);
  });
});
