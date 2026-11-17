import { describe, expect, it } from "vitest";
import { countedGroup, groupText } from "./logGroups";

const c = (name: string, card_id: string | null = name) => ({ card: { name, card_id } });

describe("a log line's cards, counted (playtest nov 16: 'Mountain, Mountain, …')", () => {
  it("counts the same card once, in first-seen order", () => {
    const g = [c("Mountain"), c("Lightning Bolt"), ...Array.from({ length: 41 }, () => c("Mountain"))];
    expect(groupText(g)).toBe("Mountain ×42, Lightning Bolt");
    expect(countedGroup(g).map((x) => x.n)).toEqual([42, 1]);
  });
  it("keeps different printings of a name apart only by printing (the hover shows each)", () => {
    expect(groupText([c("Island", "a"), c("Island", "b")])).toBe("Island, Island");
    expect(groupText([c("Opt")])).toBe("Opt");
  });
});
