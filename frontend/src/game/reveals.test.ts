import { describe, expect, it } from "vitest";
import type { LogEntryView } from "../types/game";
import { freshReveals, revealOf } from "./reveals";

const card = (name: string) => ({ card: { name, card_id: `print-${name}` } });
const entry = (seq: number, extra: Partial<LogEntryView> = {}, hidden = 0): LogEntryView => ({
  seq, ts: seq, turn: 1, phase: "main1", actor: "p1", kind: "action",
  parts: [{ t: "Alice" }, { t: " revealed cards from the top of their library (Nissa, Resurgent Animist): " },
    { group: [card("Lightning Bolt"), card("Island"), card("Llanowar Elves")], hidden }, { t: " — found " }, card("Llanowar Elves")],
  ...extra,
});

describe("public reveals from the log", () => {
  it("reads the cards a line names, the source and the card found", () => {
    const r = revealOf(entry(1, { reveal: { player: "p1", source: "Nissa, Resurgent Animist", until: true, found: true } }));
    expect(r?.cards.map((c) => c.name)).toEqual(["Lightning Bolt", "Island", "Llanowar Elves"]);
    expect(r?.found?.name).toBe("Llanowar Elves");
    expect(r?.source).toBe("Nissa, Resurgent Animist");
  });

  it("ignores lines that aren't reveals, and claims no card found when some aren't named to this viewer", () => {
    expect(revealOf(entry(1))).toBeNull();
    const r = revealOf(entry(1, { reveal: { player: "p1", source: null, until: true, found: true } }, 2));
    expect(r?.found).toBeNull();
    expect(r?.hidden).toBe(2);
  });

  it("shows each reveal once", () => {
    const seen = new Set<string>();
    const log = [entry(1, { reveal: { player: "p1", source: null, until: false, found: false } }), entry(2)];
    expect(freshReveals(log, seen)).toHaveLength(1);
    expect(freshReveals(log, seen)).toHaveLength(0);
  });
});
