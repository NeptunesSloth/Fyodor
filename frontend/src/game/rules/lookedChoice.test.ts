import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { LookedChoice, lookedPlan } from "./LookedChoice";
import type { DecisionView, GameView, VisibleCard } from "../../types/game";

const base = { owner: "p1", controller: "p1", zone: "p1:library", face_down: false, face: 0, revealed: false, note: "", card_id: null, is_token: false };
const card = (id: string, name: string) => ({ ...base, id, name }) as unknown as VisibleCard;
const view = { cards: { b: card("b", "Grizzly Bears"), i: card("i", "Island"), l: card("l", "Lightning Bolt") } } as unknown as GameView;
const decision = (over: Partial<DecisionView>): DecisionView =>
  ({ id: "d1", player: "p1", kind: "choose_cards", prompt: "", min_choices: 0, max_choices: 1, ...over }) as DecisionView;

describe("LookedChoice: every card looked at, the ones that don't qualify shown but not answers", () => {
  it("Risen Reef, a nonland on top: the card is shown dimmed with why, and one OK", () => {
    const d = decision({ max_choices: 0, options: [],
      display: { kind: "looked", cards: ["b"], ineligible: "not a land card", otherwise: "It goes into your hand" } });
    expect(lookedPlan(d, view).mode).toBe("ok");
    const html = renderToStaticMarkup(createElement(LookedChoice, { d, view: view as GameView }));
    expect(html).toContain("looked-card ineligible");
    expect(html).toContain('aria-disabled="true"');
    expect(html).toMatch(/class="looked-face dim"/);
    expect(html).toContain(">Grizzly Bears<");
    expect(html).toContain(">not a land card<");
    expect(html).toMatch(/data-testid="decision-done"[^>]*>OK</);
    expect(html).not.toContain('data-testid="option-b"'); // not an answer: no pick button (digit keys skip it)
  });

  it("Risen Reef, a land on top: take it (the card's words) or no — where it goes then", () => {
    const d = decision({ options: [{ id: "i", label: "Island", card_id: "i" }],
      display: { kind: "looked", cards: ["i"], ineligible: "not a land card", take: "Put it onto the battlefield tapped", otherwise: "It goes into your hand" } });
    expect(lookedPlan(d, view).mode).toBe("gate");
    const html = renderToStaticMarkup(createElement(LookedChoice, { d, view: view as GameView }));
    expect(html).toContain("looked-card eligible");
    expect(html).not.toContain("dim");
    expect(html).toMatch(/data-testid="option-take"[^>]*>Put it onto the battlefield tapped</);
    expect(html).toMatch(/data-testid="option-decline"[^>]*>No — it goes into your hand</);
  });

  it("Augur of Bolas: the three cards in order; the one that qualifies picks, the others are greyed", () => {
    const d = decision({ options: [{ id: "l", label: "Lightning Bolt", card_id: "l" }],
      display: { kind: "looked", cards: ["b", "l", "i"], ineligible: "not an instant or sorcery card" } });
    const plan = lookedPlan(d, view);
    expect(plan.mode).toBe("pick");
    expect(plan.rows.map((r) => [r.name, r.eligible, r.why])).toEqual([
      ["Grizzly Bears", false, "not an instant or sorcery card"], ["Lightning Bolt", true, null], ["Island", false, "not an instant or sorcery card"],
    ]);
    const html = renderToStaticMarkup(createElement(LookedChoice, { d, view: view as GameView }));
    expect(html.match(/data-testid="option-/g)?.length).toBe(1); // only Lightning Bolt picks
    expect(html).toContain('data-testid="option-l"');
    expect(html.match(/looked-face dim/g)?.length).toBe(2);
    expect(html).toMatch(/data-testid="decision-done"[^>]*>Done \(none\)</);
  });
});
