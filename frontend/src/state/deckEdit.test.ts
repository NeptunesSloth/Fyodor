import { describe, expect, it } from "vitest";
import type { DeckEntry } from "../types/decks";
import { addCard, changeQuantity, moveToSection, sectionCount, setCommander, setPrinting, typeGroup } from "./deckEdit";

const e = (name: string, section: DeckEntry["section"] = "main", quantity = 1, id = name.toLowerCase()): DeckEntry => ({
  section, quantity, name, printing_id: id, set_code: "tst", collector_number: "1",
});
const card = (name: string, id = name.toLowerCase()) => ({ id, name, set_code: "tst", collector_number: "1" });

describe("deck editing", () => {
  it("adds new cards and merges repeated adds", () => {
    let list = addCard([], card("Sol Ring"));
    list = addCard(list, card("Sol Ring"));
    expect(list).toHaveLength(1);
    expect(list[0]!.quantity).toBe(2);
    list = addCard(list, card("Sol Ring"), "sideboard");
    expect(list).toHaveLength(2);
  });

  it("removes an entry when quantity drops to zero", () => {
    expect(changeQuantity([e("Island", "main", 1)], 0, -1)).toEqual([]);
    expect(changeQuantity([e("Island", "main", 10)], 0, -3)[0]!.quantity).toBe(7);
  });

  it("moves part of a stack between sections and merges", () => {
    let list = [e("Bolt", "main", 4), e("Bolt", "sideboard", 1)];
    list = moveToSection(list, 0, "sideboard", 2);
    expect(sectionCount(list, "main")).toBe(2);
    expect(sectionCount(list, "sideboard")).toBe(3);
    expect(list).toHaveLength(2);
  });

  it("setCommander demotes the previous commander", () => {
    let list = [e("Krenko", "commander"), e("Atraxa"), e("Sol Ring")];
    list = setCommander(list, 1);
    expect(list.filter((x) => x.section === "commander").map((x) => x.name)).toEqual(["Atraxa"]);
    expect(list.find((x) => x.name === "Krenko")!.section).toBe("main");
  });

  it("setCommander can keep a partner", () => {
    const list = setCommander([e("Tymna", "commander"), e("Thrasios")], 1, true);
    expect(sectionCount(list, "commander")).toBe(2);
  });

  it("sets a printing without touching other rows", () => {
    const list = setPrinting([e("Sol Ring"), e("Island")], 0, { id: "x", name: "Sol Ring", set_code: "c21", collector_number: "263" });
    expect(list[0]!.set_code).toBe("c21");
    expect(list[1]!.set_code).toBe("tst");
  });

  it("groups by front-face type", () => {
    expect(typeGroup("Legendary Creature — Goblin")).toBe("Creature");
    expect(typeGroup("Artifact Creature — Golem")).toBe("Creature");
    expect(typeGroup("Instant // Instant")).toBe("Instant");
    expect(typeGroup("Basic Land — Island")).toBe("Land");
    expect(typeGroup("Sorcery // Land")).toBe("Sorcery");
    expect(typeGroup(null)).toBe("Other");
  });
});
