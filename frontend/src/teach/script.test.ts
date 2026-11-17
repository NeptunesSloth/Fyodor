import { describe, expect, it } from "vitest";
import { addAbility, emptyScript, find, fromEntry, hasWork, insert, move, newNode, order, remove, removeAbility, setValue, toEntry } from "./script";
import { vocabulary } from "./testVocabulary";
import type { Entry } from "./types";

const voc = vocabulary();
const piece = (id: string) => voc.pieces.find((p) => p.id === id)!;

const DIVE: Entry = { kind: "keyword", name: "Dive", param: true, reminder: "Mill N, maybe keep one.", abilities: [{ hat: { id: "etb" },
  body: [{ id: "mill", values: { n: "N" } }, { id: "may", body: [{ id: "from_milled", values: { n: "N", card: "card_creature" } }] }] }] };

describe("the serialiser", () => {
  it("round-trips an entry without uids", () => {
    const script = fromEntry(DIVE);
    expect(toEntry(script, voc)).toEqual(DIVE);
    expect(JSON.stringify(toEntry(script, voc))).not.toContain("uid");
  });
  it("fills a new piece with its defaults and keeps only known settings", () => {
    const draw = newNode(piece("draw"));
    expect(draw.values).toEqual({ n: 1 });
    let s = emptyScript();
    s = insert(s, { ability: 0, index: [] }, newNode(piece("etb")));
    s = insert(s, { ability: 0, index: [0] }, { ...draw, values: { n: 2, evil: "x" } });
    expect(toEntry(s, voc).abilities[0]).toEqual({ hat: { id: "etb" }, body: [{ id: "draw", values: { n: 2 } }] });
  });
  it("skips an ability with no hat and writes a card line", () => {
    const s = fromEntry({ kind: "card", oracle_id: "abc", line: "Whenever X attacks, do Y.", card_name: "X", type_line: "Creature — Elf",
      abilities: [{ hat: { id: "attacks" }, body: [{ id: "draw", values: { n: 1 } }] }] });
    const two = addAbility(s);
    const entry = toEntry(two, voc);
    expect(entry.kind).toBe("card");
    expect(entry.abilities).toHaveLength(1);
    if (entry.kind === "card") expect([entry.oracle_id, entry.line, entry.card_name, entry.type_line]).toEqual(["abc", "Whenever X attacks, do Y.", "X", "Creature — Elf"]);
  });
});

describe("editing", () => {
  it("inserts, moves and removes along paths", () => {
    let s = fromEntry(DIVE);
    const draw = newNode(piece("draw"));
    s = insert(s, { ability: 0, index: [2] }, draw);
    expect(s.abilities[0]!.body.map((n) => n.id)).toEqual(["mill", "may", "draw"]);
    s = move(s, { ability: 0, index: [2] }, { ability: 0, index: [0] });
    expect(s.abilities[0]!.body.map((n) => n.id)).toEqual(["draw", "mill", "may"]);
    s = move(s, { ability: 0, index: [0] }, { ability: 0, index: [3] }); // (down past the end: the gap closes)
    expect(s.abilities[0]!.body.map((n) => n.id)).toEqual(["mill", "may", "draw"]);
    expect(find(s, draw.uid)).toEqual({ ability: 0, index: [2] });
    s = remove(s, { ability: 0, index: [1, 0] }); // the piece inside "you may"
    expect(s.abilities[0]!.body[1]!.body).toEqual([]);
    s = setValue(s, { ability: 0, index: [0] }, "n", 3);
    expect(s.abilities[0]!.body[0]!.values).toEqual({ n: 3 });
    s = remove(s, { ability: 0, index: [] });
    expect(s.abilities[0]!.hat).toBeNull();
    expect(hasWork(s)).toBe(false);
  });
  it("never moves a container into itself", () => {
    const s = fromEntry(DIVE);
    expect(move(s, { ability: 0, index: [1] }, { ability: 0, index: [1, 0] })).toBe(s);
  });
  it("lists pieces in reading order and always keeps one ability", () => {
    const s = fromEntry(DIVE);
    expect(order(s).map((o) => o.path.index)).toEqual([[], [0], [1], [1, 0]]);
    const none = removeAbility(s, 0);
    expect(none.abilities).toHaveLength(1);
    expect(none.abilities[0]!.hat).toBeNull();
  });
});
