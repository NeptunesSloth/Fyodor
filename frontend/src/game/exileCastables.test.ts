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
    const { ExileCastablesRow } = await import("./ExileCastablesRow");
    const withPlayers = (v: GameView) => Object.assign(v, { players: [{ id: "p1", name: "Alice" }, { id: "p2", name: "Bob" }] });
    const html = renderToStaticMarkup(createElement(ExileCastablesRow, { view: withPlayers(view()), me: "p1" }));
    expect(html).toContain('data-testid="exile-castables"');
    expect(html).toContain("Exiled with Ian Malcolm, Chaotician");
    expect(html).toContain("Bob");
    expect(html.match(/data-testid="exile-castable"/g)).toHaveLength(2);
    expect(renderToStaticMarkup(createElement(ExileCastablesRow, { view: withPlayers(view({ castable: [], playable_lands: [] })), me: "p1" }))).toBe("");
  });
});

describe("castable from any pile (playtest nov 16: a flashback Bolt in the graveyard browser)", () => {
  // (vi.mock-free: the store's send is replaced, as handDrop.test.ts does)
  const pile = (hints: Record<string, unknown>): GameView => ({
    viewer: "p1",
    cards: {
      bolt: { id: "bolt", name: "Lightning Bolt", zone: "p1:graveyard", owner: "p1", controller: "p1", card_id: "bolt" },
      opt: { id: "opt", name: "Opt", zone: "p1:graveyard", owner: "p1", controller: "p1", card_id: "opt" },
      top: { id: "top", name: "Brainstorm", zone: "p1:library", owner: "p1", controller: "p1", card_id: "opt" },
      hand: { id: "hand", name: "Opt", zone: "p1:hand", owner: "p1", controller: "p1", card_id: "opt" },
      esc: { id: "esc", name: "Ox of Agonas", zone: "p1:graveyard", owner: "p1", controller: "p1", card_id: "opt" },
    },
    zones: {},
    rules: { paused: false, prefs: {}, card_modes: {}, hints: { has_priority: true, ...hints } },
  }) as unknown as GameView;

  it("lists graveyard, library-top and exile cards the hints name, never the hand", async () => {
    const { zoneCastables } = await import("./exileCastables");
    const got = zoneCastables(pile({ castable: ["bolt", "hand"], free_castable: ["top"], alt_castable: { esc: [{ id: "escape", label: "Escape" }] } }));
    expect(got).toEqual([
      { id: "bolt", play: false, free: false, alt: false },
      { id: "top", play: false, free: true, alt: false },
      { id: "esc", play: false, free: false, alt: true },
    ]);
    expect(castableIn(pile({ castable: ["bolt"] }), "p1:graveyard")).toBe(1);
    expect(castableIn(pile({ castable: ["bolt"], has_priority: false }), "p1:graveyard")).toBe(0);
  });

  it("a double-click casts its one way straight away, or opens the ways to choose from", async () => {
    const { useGame } = await import("../state/gameStore");
    const { useMenu } = await import("../components/ContextMenu");
    const { castFromZone } = await import("./exileCastables");
    const sent: unknown[] = [];
    useGame.setState({ send: (async (a: unknown) => { sent.push(a); return true; }) as never });
    useMenu.setState({ menu: null });
    const v = pile({ castable: ["bolt"], alt_castable: { esc: [{ id: "e1", label: "Escape—{R}{R}, Exile two other cards" }, { id: "e2", label: "Other" }] } });
    useGame.setState({ view: v });
    expect(castFromZone(v.cards.bolt!, v, "p1", { clientX: 5, clientY: 6 })).toBe(true);
    expect(sent).toEqual([{ type: "cast_spell", card_id: "bolt" }]);
    expect(castFromZone(v.cards.esc!, v, "p1", { clientX: 5, clientY: 6 })).toBe(true);
    expect(useMenu.getState().menu!.items.map((i) => (i === "separator" ? "-" : i.label))).toHaveLength(2);
    expect(castFromZone(v.cards.opt!, v, "p1", { clientX: 5, clientY: 6 })).toBe(false); // (not castable: the caller moves it to hand)
  });
});
