import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { abilityText, actionPhrase, actionSentences, compileEntry, keywordLine, render, selfWord } from "./sentence";
import type { Entry, Vocabulary } from "./types";
import { vocabulary } from "./testVocabulary";

interface Case { name: string; entry: Entry; lines: string[]; lines_n2?: string[]; lines_artifact: string[]; phrase?: string; said?: string; said_target?: string }

const fixture = JSON.parse(readFileSync(new URL("../../../backend/tests/fixtures/teach_sentences.json", import.meta.url), "utf8")) as Case[];
const voc: Vocabulary = vocabulary();

describe("sentence readback matches the backend word for word", () => {
  it("covers every piece", () => {
    expect(fixture.length).toBeGreaterThan(250);
    const used = new Set<string>();
    const walk = (b: { id: string; body?: { id: string }[] }) => { used.add(b.id); b.body?.forEach(walk); };
    for (const c of fixture) for (const a of c.entry.abilities) { walk(a.hat); a.body.forEach(walk); }
    for (const p of voc.pieces) expect(used.has(p.id), `piece ${p.id} is in the matrix`).toBe(true);
  });

  for (const c of fixture) {
    it(c.name, () => {
      expect(compileEntry(c.entry, voc, { me: "this creature" })).toEqual(c.lines);
      expect(compileEntry(c.entry, voc, { me: "this artifact" })).toEqual(c.lines_artifact);
      if (c.lines_n2) expect(compileEntry(c.entry, voc, { n: 2, me: "this creature" })).toEqual(c.lines_n2);
      if (c.entry.kind === "action") {
        expect(actionPhrase(c.entry)).toBe(c.phrase);
        expect(actionSentences(c.entry, voc, { me: "it" })).toBe(c.said);
        expect(actionSentences(c.entry, voc, { me: "target creature", n: c.entry.param ? 2 : null })).toBe(c.said_target);
      }
    });
  }
  it("has the real dive as an action", () => {
    expect(fixture.some((c) => c.entry.kind === "action" && c.entry.name === "dive" && c.said === "it can't be blocked until it deals combat damage while attacking")).toBe(true);
  });
});

describe("render", () => {
  it("writes numbers in the asked form", () => {
    expect(render("draw {n:a} card{n:s}", { n: 1 }, voc)).toBe("draw a card");
    expect(render("draw {n:a} card{n:s}", { n: 3 }, voc)).toBe("draw three cards");
    expect(render("mill {n:a} card{n:s}", { n: "N" }, voc)).toBe("mill N cards");
    expect(render("mill {n:a} card{n:s}", { n: "N" }, voc, { n: 2 })).toBe("mill two cards");
    expect(render("{p:signed}/{t:signed}", { p: "N", t: "-N" }, voc)).toBe("+N/-N");
    expect(render("{p:signed}/{t:signed}", { p: "N", t: "-N" }, voc, { n: 3 })).toBe("+3/-3");
    expect(render("{n:mana} less", { n: 2 }, voc)).toBe("{2} less");
    expect(render("{mana}", { mana: "{N}{U}" }, voc, { n: 4 })).toBe("{4}{U}");
  });
  it("speaks options and the card's own name", () => {
    expect(render("{who} get{who:vs} +1/+1", { who: "t_creatures_yours" }, voc)).toBe("creatures you control get +1/+1");
    expect(render("{who} get{who:vs} +1/+1", { who: "t_self" }, voc, { me: "this land" })).toBe("this land gets +1/+1");
    expect(render("{self} deals {n} damage to {to}", { n: 2, to: "t_any" }, voc)).toBe("this creature deals 2 damage to any target");
  });
  it("leaves an unknown token alone", () => {
    expect(render("{self} does {what}", {}, voc)).toBe("this creature does {what}");
  });
});

describe("abilityText", () => {
  it("shows an unfinished ability with an ellipsis", () => {
    expect(abilityText({ hat: { id: "etb" }, body: [] }, voc)).toBe("When this creature enters, …");
    expect(abilityText({ hat: { id: "etb" }, body: [{ id: "mill", values: { n: 2 } }, { id: "may", body: [] }] }, voc)).toBe("When this creature enters, mill two cards. You may ….");
    expect(abilityText({ hat: { id: "attacks" }, body: [{ id: "pay_mana", values: { mana: "{2}" }, body: [] }] }, voc)).toBe("Whenever this creature attacks, you may pay {2}. If you do, ….");
    expect(abilityText({ hat: { id: "activated" }, body: [] }, voc)).toBe("…: …");
    expect(abilityText({ hat: { id: "static" }, body: [] }, voc)).toBe("….");
  });
  it("reads the Dive example", () => {
    const dive: Entry = { kind: "keyword", name: "Dive", param: true, reminder: "", abilities: [{ hat: { id: "etb" },
      body: [{ id: "mill", values: { n: "N" } }, { id: "may", body: [{ id: "from_milled", values: { n: "N", card: "card_creature" } }] }] }] };
    const lines = compileEntry(dive, voc);
    expect(lines).toEqual(["When this creature enters, mill N cards. You may put a creature card with mana value N or less from among the cards milled this way into your hand."]);
    expect(keywordLine("Dive", true, lines, 2)).toMatch(/^Dive 2 \(When this creature enters, mill N cards\./);
    expect(keywordLine("Dive", false, [])).toBe("Dive");
  });
});

describe("actions", () => {
  it("reads dive the way the card says it", () => {
    const dive: Entry = { kind: "action", name: "dive", param: false, reminder: "", abilities: [{ hat: { id: "action" },
      body: [{ id: "unblockable_for", values: { who: "t_self", dur: "rdur_combat_attacking" } }] }] };
    expect(compileEntry(dive, voc, { me: "this creature" })).toEqual(["It can't be blocked until it deals combat damage while attacking."]);
    expect(actionPhrase(dive)).toBe("it dives");
    expect(actionSentences(dive, voc, { me: "target creature" })).toBe("target creature can't be blocked until it deals combat damage while attacking");
    expect(actionPhrase({ name: "plunge", param: true }, 2)).toBe("plunge 2");
    expect(actionPhrase({ name: "plunge", param: true })).toBe("plunge N");
    expect(abilityText({ hat: { id: "action" }, body: [] }, voc)).toBe("…");
  });
});

describe("selfWord", () => {
  it("names the card by its type", () => {
    expect(selfWord("Legendary Creature — Merfolk")).toBe("this creature");
    expect(selfWord("Artifact Creature — Golem")).toBe("this creature");
    expect(selfWord("Artifact — Equipment")).toBe("this artifact");
    expect(selfWord("Instant")).toBe("this spell");
    expect(selfWord(null)).toBe("this permanent");
  });
});
