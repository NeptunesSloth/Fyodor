import { describe, expect, it } from "vitest";
import type { GameCard, GameView, TableArrow } from "../types/game";
import { autoCenterTarget, autoSnap, type AutoCenterLevel } from "./autoCenter";

const card = (id: string, controller: string, zone: string, extra: Partial<GameCard> = {}): GameCard =>
  ({ id, owner: controller, controller, zone, face_down: false, card_id: null, name: id, face: 0, revealed: false, note: "", is_token: false, ...extra }) as GameCard;

const baseCards = [
  card("myBear", "me", "me:battlefield"),
  card("myWalker", "me", "me:battlefield"),
  card("bobOrc", "bob", "bob:battlefield"),
  card("bobElf", "bob", "bob:battlefield"),
  card("caraWolf", "cara", "cara:battlefield"),
];

function view(patch: { cards?: GameCard[]; stack?: string[]; arrows?: TableArrow[]; active?: string; turn?: number; lost?: Record<string, string> } = {}): GameView {
  const cards = [...baseCards, ...(patch.cards ?? [])];
  return {
    cards: Object.fromEntries(cards.map((c) => [c.id, c])),
    stack: patch.stack ?? [],
    arrows: patch.arrows ?? [],
    turn: { number: patch.turn ?? 4, active_player: patch.active ?? "bob", phase: "main1" },
    rules: patch.lost ? { conceded: [], lost: patch.lost } : undefined,
  } as unknown as GameView;
}

const at = (level: AutoCenterLevel, before: GameView, after: GameView) => autoCenterTarget(autoSnap(before), after, "me", level);
const attack = (id: string, controller: string, target: { kind: "player" | "card"; id: string }) =>
  card(id, controller, `${controller}:battlefield`, { attacking: target });

describe("auto-centre events", () => {
  const quiet = view();
  it("does nothing when off, or when nothing major happened", () => {
    const spell = card("bolt", "bob", "stack");
    expect(at("off", quiet, view({ lost: { bob: "life" } }))).toBeNull();
    expect(at("important", quiet, view({ cards: [spell], stack: ["bolt"] }))).toBeNull(); // an ordinary spell
    expect(at("on", quiet, quiet)).toBeNull();
  });
  it("important: an elimination looks at that seat (never your own)", () => {
    expect(at("important", quiet, view({ lost: { cara: "life" } }))).toEqual({ focus: "cara" });
    expect(at("important", quiet, view({ lost: { me: "life" } }))).toBeNull();
  });
  it("important: someone else's commander cast looks at their seat; yours doesn't move the camera", () => {
    const theirs = card("edgar", "bob", "stack", { commander_key: "edgar" });
    expect(at("important", quiet, view({ cards: [theirs], stack: ["edgar"] }))).toEqual({ focus: "bob" });
    const mine = card("atraxa", "me", "stack", { commander_key: "atraxa" });
    expect(at("important", quiet, view({ cards: [mine], stack: ["atraxa"] }))).toBeNull();
  });
  it("important: an attack declared on you or your planeswalker frames the fight", () => {
    expect(at("important", quiet, view({ cards: [attack("a1", "bob", { kind: "player", id: "me" })] }))).toEqual({ combat: true });
    expect(at("important", quiet, view({ cards: [attack("a1", "bob", { kind: "card", id: "myWalker" })] }))).toEqual({ combat: true });
    // an attack on someone else is not important …
    const elsewhere = view({ cards: [attack("a1", "bob", { kind: "player", id: "cara" })] });
    expect(at("important", quiet, elsewhere)).toBeNull();
    // … and an attack already declared isn't news
    expect(at("important", view({ cards: [attack("a1", "bob", { kind: "player", id: "me" })] }), view({ cards: [attack("a1", "bob", { kind: "player", id: "me" })] }))).toBeNull();
  });
  it("important: someone else's spell targeting you or your permanent frames the stack", () => {
    const spell = card("bolt", "bob", "stack");
    const arrow = (targets: string[], owner = "bob"): TableArrow => ({ id: "ar1", owner, source: "bolt", targets, kind: "target", label: "" });
    expect(at("important", quiet, view({ cards: [spell], stack: ["bolt"], arrows: [arrow(["myBear"])] }))).toEqual({ stack: true });
    expect(at("important", quiet, view({ cards: [spell], stack: ["bolt"], arrows: [arrow(["me"])] }))).toEqual({ stack: true });
    expect(at("important", quiet, view({ cards: [spell], stack: ["bolt"], arrows: [arrow(["caraWolf"])] }))).toBeNull();
    const mine = card("bolt", "me", "stack");
    expect(at("important", quiet, view({ cards: [mine], stack: ["bolt"], arrows: [arrow(["myBear"], "me")] }))).toBeNull();
    // a hand-drawn target arrow from a permanent looks at its controller's seat
    const fromOrc: TableArrow = { id: "ar2", owner: "bob", source: "bobOrc", targets: ["myBear"], kind: "target", label: "" };
    expect(at("important", quiet, view({ arrows: [fromOrc] }))).toEqual({ focus: "bob" });
    // a custom (non-target) arrow is not targeting
    expect(at("important", quiet, view({ arrows: [{ ...fromOrc, kind: "custom" }] }))).toBeNull();
  });
  it("on: adds the start of your turn and other players' attacks", () => {
    expect(at("important", quiet, view({ active: "me", turn: 5 }))).toBeNull();
    expect(at("on", quiet, view({ active: "me", turn: 5 }))).toBe("seat");
    expect(at("on", view({ active: "me" }), view({ active: "me" }))).toBeNull(); // still your turn: nothing new
    expect(at("on", quiet, view({ cards: [attack("a1", "bob", { kind: "player", id: "cara" })] }))).toEqual({ combat: true });
    expect(at("on", quiet, view({ cards: [attack("a1", "me", { kind: "player", id: "bob" })] }))).toBeNull(); // your own attack
  });
  it("the most important event wins", () => {
    const both = view({ lost: { cara: "life" }, cards: [attack("a1", "bob", { kind: "player", id: "me" })] });
    expect(at("on", quiet, both)).toEqual({ focus: "cara" });
  });
});
