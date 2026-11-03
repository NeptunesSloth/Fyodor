import { describe, expect, it } from "vitest";
import type { GameView } from "../types/game";
import { castableIn, exileCastables } from "./exileCastables";

/** A table where Ian Malcolm exiled Bob's Giant Growth (Alice may cast it) and Alice's own Sol Ring (she may not). */
function view(hints: Record<string, unknown> = {}, paused = false): GameView {
  return {
    viewer: "p1",
    cards: {
      growth: { id: "growth", name: "Giant Growth", zone: "p2:exile", owner: "p2", controller: "p2" },
      ring: { id: "ring", name: "Sol Ring", zone: "p1:exile", owner: "p1", controller: "p1" },
      bolt: { id: "bolt", name: "Lightning Bolt", zone: "p1:hand", owner: "p1", controller: "p1" },
      island: { id: "island", name: "Island", zone: "p2:exile", owner: "p2", controller: "p2" },
    },
    rules: { paused, hints: { has_priority: true, castable: ["growth", "bolt"], playable_lands: ["island"], exiled_with: { growth: "Ian Malcolm, Chaotician" }, ...hints } },
  } as unknown as GameView;
}

describe("castable from exile (the Ian Malcolm exile markers)", () => {
  it("lists only exiled cards the viewer's own hints allow, with the card that exiled them", () => {
    expect(exileCastables(view())).toEqual([
      { id: "growth", play: false, owner: "p2", source: "Ian Malcolm, Chaotician" },
      { id: "island", play: true, owner: "p2" },
    ]);
  });
  it("counts them per exile pile", () => {
    expect(castableIn(view(), "p2:exile")).toBe(2);
    expect(castableIn(view(), "p1:exile")).toBe(0); // (her own Sol Ring isn't castable: Ian lets you cast cards you don't own)
  });
  it("shows nothing without priority, with automation paused, or without hints", () => {
    expect(exileCastables(view({ has_priority: false }))).toEqual([]);
    expect(exileCastables(view({}, true))).toEqual([]);
    expect(exileCastables(null)).toEqual([]);
  });
  it("renders the row with whose card it is and what exiled it", async () => {
    const { createElement } = await import("react");
    const { renderToStaticMarkup } = await import("react-dom/server");
    const { ExileCastablesRow } = await import("./ExileCastables");
    const withPlayers = (v: GameView) => Object.assign(v, { players: [{ id: "p1", name: "Alice" }, { id: "p2", name: "Bob" }] });
    const html = renderToStaticMarkup(createElement(ExileCastablesRow, { view: withPlayers(view()), me: "p1" }));
    expect(html).toContain('data-testid="exile-castables"');
    expect(html).toContain("Exiled with Ian Malcolm, Chaotician");
    expect(html).toContain("Bob");
    expect(html.match(/data-testid="exile-castable"/g)).toHaveLength(2);
    expect(renderToStaticMarkup(createElement(ExileCastablesRow, { view: withPlayers(view({ castable: [], playable_lands: [] })), me: "p1" }))).toBe("");
  });
});
