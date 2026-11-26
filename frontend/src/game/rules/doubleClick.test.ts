import { beforeEach, describe, expect, it, vi } from "vitest";
import { useCardCache } from "../../state/cardCache";
import { useGame } from "../../state/gameStore";
import type { CardData } from "../../types/cards";
import type { GameView } from "../../types/game";

const menus: unknown[] = [];
const toasts: string[] = [];
vi.mock("../../components/ContextMenu", () => ({ openMenu: (_at: unknown, items: unknown) => menus.push(items) }));
vi.mock("../../components/Toasts", () => ({ toast: (t: string) => toasts.push(t) }));
const { doubleClickGesture, tapAbilities } = await import("./intents");

const card = (id: string, card_id: string, extra: object = {}) => ({ id, zone: "p1:battlefield", card_id, name: card_id, owner: "p1", controller: "p1", ...extra });
const view = (rules: object | null, cards: Record<string, object>): GameView =>
  ({ viewer: "p1", seat_order: ["p1"], players: [{ id: "p1", name: "Alice" }], game: { seats: { p1: {} } }, turn: { active_player: "p1" }, cards, rules }) as unknown as GameView;
const RULES = (activatable: object[]) => ({ automation: "full", paused: false, prefs: { mana_sources: {} }, hints: { has_priority: true, activatable } });

const sent: unknown[] = [];
const tapped: string[][] = [];
const at = { clientX: 10, clientY: 10 };

beforeEach(() => {
  sent.length = 0; tapped.length = 0; menus.length = 0; toasts.length = 0;
  useGame.setState({ view: null, actingAs: null, send: vi.fn(async (a) => { sent.push(a); return true; }) });
  useCardCache.setState({
    cards: {
      looter: { id: "looter", name: "Merfolk Looter", type_line: "Creature", oracle_text: "{T}: Draw a card, then discard a card." } as CardData,
      twin: { id: "twin", name: "Twin", type_line: "Creature", oracle_text: "{T}: Draw a card.\n{1}, {T}: Scry 1." } as CardData,
      bears: { id: "bears", name: "Grizzly Bears", type_line: "Creature", oracle_text: "" } as CardData,
      forest: { id: "forest", name: "Forest", type_line: "Basic Land — Forest", oracle_text: "({T}: Add {G}.)" } as CardData,
    },
  });
});

describe("double-click on a permanent with a {T} ability (playtest nov 17: it tapped it by hand and wasted the ability)", () => {
  const plain = (ids: string[]) => tapped.push(ids);

  it("activates its one ready {T} ability instead of a plain tap", () => {
    useGame.setState({ view: view(RULES([{ card_id: "c", ability: 0 }]), { c: card("c", "looter") }) });
    doubleClickGesture(["c"], at, plain);
    expect(sent).toEqual([{ type: "activate_ability", card_id: "c", ability: 0 }]);
    expect(tapped).toEqual([]);
  });

  it("offers a chooser when several are ready", () => {
    useGame.setState({ view: view(RULES([{ card_id: "c", ability: 0 }, { card_id: "c", ability: 1 }]), { c: card("c", "twin") }) });
    doubleClickGesture(["c"], at, plain);
    expect(menus).toHaveLength(1);
    expect(sent).toEqual([]);
    expect(tapAbilities("c", useGame.getState().view!).map((a) => a.index)).toEqual([0, 1]);
  });

  it("not ready now: says so and leaves it untapped (T and the menu still tap by hand)", () => {
    useGame.setState({ view: view(RULES([]), { c: card("c", "looter") }) });
    doubleClickGesture(["c"], at, plain);
    expect(tapped).toEqual([]);
    expect(toasts[0]).toContain("press T");
  });

  it("no {T} ability, automation off, or a land: as before", () => {
    useGame.setState({ view: view(RULES([]), { c: card("c", "bears") }) });
    doubleClickGesture(["c"], at, plain);
    expect(tapped).toEqual([["c"]]);
    useGame.setState({ view: view(null, { c: card("c", "looter") }) });
    doubleClickGesture(["c"], at, plain);
    expect(tapped).toEqual([["c"], ["c"]]);
    useGame.setState({ view: view(RULES([]), { f: card("f", "forest") }) });
    doubleClickGesture(["f"], at, plain);
    expect(sent).toMatchObject([{ type: "activate_ability", card_id: "f", tap_for_mana: true }]);
  });
});
