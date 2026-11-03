import { describe, expect, it } from "vitest";
import type { GameView } from "../../types/game";
import { onTableEvents, publishTableEvents, tableEvents } from "./tableEvents";

type Card = Record<string, unknown> & { id: string; zone: string; owner: string };
/** A table as a viewer is sent it: ``zones`` lists ids (a library: its size and shuffles), ``cards`` the views. */
function table(cards: Card[], extra: { libraries?: Record<string, [number, number?]>; life?: Record<string, number> } = {}): GameView {
  const zones: Record<string, unknown> = {};
  const views: Record<string, unknown> = {};
  for (const c of cards) {
    views[c.id] = { controller: c.owner, face_down: false, ...c };
    if (!c.zone.endsWith(":library")) ((zones[c.zone] ??= []) as string[]).push(c.id);
  }
  for (const [key, [count, shuffles]] of Object.entries(extra.libraries ?? {})) zones[key] = { count, known: [], ...(shuffles ? { shuffles } : {}) };
  const players = Object.entries(extra.life ?? { p1: 40, p2: 40 }).map(([id, life]) => ({ id, life }));
  return { zones, cards: views, players } as unknown as GameView;
}
const seen = (id: string, zone: string, owner = zone.split(":")[0]!, more: Record<string, unknown> = {}): Card => ({ id, zone, owner, name: id, ...more });
const hidden = (n: number, zone: string): Card[] =>
  Array.from({ length: n }, (_, i) => ({ id: `hidden:${zone}:${i}`, zone, owner: zone.split(":")[0]!, hidden: true }));

describe("tableEvents", () => {
  it("a card seen in both views that changed zones moves (Alice casts from her hand: she sees her hand)", () => {
    const prev = table([seen("bolt", "p1:hand")], { libraries: { "p1:library": [30] } });
    const next = table([seen("bolt", "stack", "p1")], { libraries: { "p1:library": [30] } });
    expect(tableEvents(prev, next)).toEqual([{ kind: "move", id: "bolt", from: "p1:hand", to: "stack" }]);
  });

  it("another player's card cast from their hidden hand arrives from that hand", () => {
    const prev = table([...hidden(3, "p2:hand")]);
    const next = table([...hidden(2, "p2:hand"), seen("ring", "stack", "p2")]);
    expect(tableEvents(prev, next)).toEqual([{ kind: "arrive", id: "ring", from: "p2:hand", to: "stack" }]);
  });

  it("your draw arrives from your library; another player's draw is hidden traffic", () => {
    const prev = table([...hidden(7, "p2:hand")], { libraries: { "p1:library": [30], "p2:library": [30] } });
    const next = table([seen("elf", "p1:hand"), ...hidden(8, "p2:hand")], { libraries: { "p1:library": [29], "p2:library": [29] } });
    expect(tableEvents(prev, next)).toEqual([
      { kind: "arrive", id: "elf", from: "p1:library", to: "p1:hand" },
      { kind: "hidden", from: "p2:library", to: "p2:hand", n: 1 },
    ]);
  });

  it("a mill arrives in the graveyard from the library; a discard from the hand", () => {
    const prev = table([...hidden(5, "p2:hand")], { libraries: { "p2:library": [30] } });
    const next = table([seen("a", "p2:graveyard"), seen("b", "p2:graveyard"), ...hidden(5, "p2:hand")], { libraries: { "p2:library": [28] } });
    expect(tableEvents(prev, next)).toEqual([
      { kind: "arrive", id: "a", from: "p2:library", to: "p2:graveyard" },
      { kind: "arrive", id: "b", from: "p2:library", to: "p2:graveyard" },
    ]);
    const discard = table([seen("c", "p2:graveyard"), ...hidden(4, "p2:hand")], { libraries: { "p2:library": [30] } });
    expect(tableEvents(prev, discard)).toEqual([{ kind: "arrive", id: "c", from: "p2:hand", to: "p2:graveyard" }]);
  });

  it("a card bounced to a hidden hand leaves for it; a token that leaves is gone", () => {
    const prev = table([seen("bear", "p2:battlefield"), seen("goblin", "p2:battlefield", "p2", { is_token: true }), ...hidden(1, "p2:hand")]);
    const next = table([...hidden(2, "p2:hand")]);
    expect(tableEvents(prev, next)).toEqual([
      { kind: "leave", id: "bear", from: "p2:battlefield", to: "p2:hand" },
      { kind: "leave", id: "goblin", from: "p2:battlefield", to: null },
    ]);
  });

  it("a token is made here; an ability arrives from its source permanent", () => {
    const prev = table([seen("krenko", "p1:battlefield")]);
    const next = table([seen("krenko", "p1:battlefield"), seen("t1", "p1:battlefield", "p1", { is_token: true }),
      seen("trig", "stack", "p1", { ability: { source_id: "krenko", text: "", source_card_id: null, source_name: "Krenko", kind: "activated" } })]);
    expect(tableEvents(prev, next)).toEqual([
      { kind: "arrive", id: "t1", from: null, to: "p1:battlefield" },
      { kind: "arrive", id: "trig", from: null, to: "stack", source: "krenko" },
    ]);
  });

  it("a shuffle is told by the library's count of shuffles; renamed known cards don't move", () => {
    const prev = table([], { libraries: { "p1:library": [30, 1] } });
    const next = table([], { libraries: { "p1:library": [30, 3] } });
    expect(tableEvents(prev, next)).toEqual([{ kind: "shuffle", zone: "p1:library", times: 2 }]);
  });

  it("attackers, blockers, damage and life", () => {
    const prev = table([seen("bear", "p1:battlefield"), seen("wall", "p2:battlefield")]);
    const next = table([seen("bear", "p1:battlefield", "p1", { attacking: { kind: "player", id: "p2" }, damage: 2 }),
      seen("wall", "p2:battlefield", "p2", { blocking: "bear" })], { life: { p1: 43, p2: 37 } });
    expect(tableEvents(prev, next)).toEqual([
      { kind: "attack", id: "bear", target: { kind: "player", id: "p2" } },
      { kind: "damage", id: "bear", amount: 2 },
      { kind: "block", id: "wall", attacker: "bear" },
      { kind: "life", player: "p1", delta: 3 },
      { kind: "life", player: "p2", delta: -3 },
    ]);
  });

  it("a card the viewer dragged doesn't fly (it is already where the hand put it)", () => {
    const prev = table([seen("forest", "p1:hand")]);
    const next = table([seen("forest", "p1:battlefield")]);
    expect(tableEvents(prev, next, new Set(["forest"]))).toEqual([]);
  });

  it("nothing in hidden zones is named: a hidden hand's placeholders never move or arrive", () => {
    const prev = table([...hidden(3, "p2:hand")]);
    const next = table([...hidden(3, "p2:hand")]);
    expect(tableEvents(prev, next)).toEqual([]);
  });

  it("a hot-seat table switching whose view it shows publishes nothing (the hands didn't move)", () => {
    const heard: unknown[] = [];
    const off = onTableEvents((events) => heard.push(events));
    const alice = { ...table([seen("bolt", "p1:hand"), ...hidden(3, "p2:hand")]), viewer: "p1" } as GameView;
    const bob = { ...table([...hidden(1, "p1:hand"), seen("ring", "p2:hand"), seen("elf", "p2:hand"), seen("ox", "p2:hand")]), viewer: "p2" } as GameView;
    publishTableEvents(alice, bob, new Set());
    expect(heard).toEqual([]);
    publishTableEvents(alice, { ...alice, players: [{ id: "p1", life: 39 }] } as unknown as GameView, new Set());
    expect(heard).toEqual([[{ kind: "life", player: "p1", delta: -1 }]]);
    off();
  });
});
