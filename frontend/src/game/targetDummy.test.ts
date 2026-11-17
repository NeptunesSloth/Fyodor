import { describe, expect, it, vi } from "vitest";
import type { GameView, PlayerView } from "../types/game";
import { dummyActions, dummyIsOut, dummyMenu, dummyName, dummyOf, rememberedDummies, spawnOwners } from "./targetDummy";

const player = (id: string, extra: Partial<PlayerView> = {}) => ({ id, name: id === "p2" ? "Target Dummy" : "Alice", life: 40, ...extra }) as PlayerView;
const table = (players: PlayerView[], extra: Partial<GameView> = {}) =>
  ({ players, game: { settings: { allow_test_objects: true } }, ...extra }) as unknown as GameView;
type Entry = { label: string; disabled?: boolean; hint?: string; onClick?: () => void };

describe("target dummy", () => {
  it("finds the dummy seat, and only one still at the table", () => {
    expect(dummyOf(table([player("p1")]))).toBeUndefined();
    expect(dummyOf(table([player("p1"), player("p2", { dummy: true })]))?.id).toBe("p2");
    expect(dummyOf(table([player("p1"), player("p2", { dummy: true, left: true })]))).toBeUndefined();
    expect(dummyOf(null)).toBeUndefined();
  });

  it("offers Spawn a card for the dummy only when there is one", () => {
    expect(spawnOwners(table([player("p1")]))).toEqual([]);
    expect(spawnOwners(table([player("p1"), player("p2", { dummy: true })]))).toEqual([{ id: null, label: "You" }, { id: "p2", label: "Target Dummy" }]);
  });

  it("knows when the rules put it out of the game", () => {
    const rules = { lost: { p2: "0 or less life" }, conceded: [] };
    expect(dummyIsOut(table([player("p1"), player("p2", { dummy: true })], { rules } as unknown as Partial<GameView>))).toBe(true);
    expect(dummyIsOut(table([player("p1"), player("p2", { dummy: true })]))).toBe(false); // (automation off: no rules view)
  });

  it("gives the host Add, then Reset / Restore", () => {
    const send = vi.fn();
    expect(dummyMenu(table([player("p1")]), false, send)).toEqual([]); // (host-only tools)
    const [add] = dummyMenu(table([player("p1")]), true, send) as Entry[];
    expect(add!.label).toBe("Add a target dummy");
    add!.onClick!();
    expect(send).toHaveBeenCalledWith({ type: "add_dummy" });
    const off = dummyMenu({ ...table([player("p1")]), game: { settings: { allow_test_objects: false } } } as unknown as GameView, true, send) as Entry[];
    expect(off[0]!.disabled).toBe(true);
    const seated = table([player("p1"), player("p2", { dummy: true, life: 12 })]);
    const [reset] = dummyMenu(seated, true, send) as Entry[];
    expect(reset!.label).toBe("Reset dummy…");
    expect(reset!.hint).toBe("12 life");
    vi.stubGlobal("window", { confirm: () => true });
    reset!.onClick!();
    expect(send).toHaveBeenLastCalledWith({ type: "reset_dummy", player: "p2" });
    vi.unstubAllGlobals();
    const lost = table([player("p1"), player("p2", { dummy: true, life: 0 })], { rules: { lost: { p2: "0 or less life" }, conceded: [] } } as unknown as Partial<GameView>);
    expect((dummyMenu(lost, true, send) as Entry[])[0]!.label).toBe("Restore dummy…");
  });

  it("lets the host set how the dummy blocks, the current way marked in words", () => {
    const send = vi.fn();
    const rules = { rules: { lost: {}, conceded: [] } } as unknown as Partial<GameView>;
    const seated = table([player("p1"), player("p2", { dummy: true, dummy_blocks: "chump" })], rules);
    const blocks = (dummyMenu(seated, true, send) as (Entry & { submenu?: Entry[] })[]).find((e) => e.label === "Dummy blocks")!;
    expect(blocks.hint).toBe("Chump the biggest attacker");
    expect(blocks.submenu!.map((e) => [e.label, e.hint, !!e.disabled])).toEqual([
      ["Never", undefined, false], ["Chump the biggest attacker", "current", true], ["Block with everything it can", undefined, false],
    ]);
    blocks.submenu![2]!.onClick!();
    expect(send).toHaveBeenCalledWith({ type: "set_dummy", blocks: "all", player: "p2" });
    const manual = (dummyMenu(table([player("p1"), player("p2", { dummy: true })]), true, send) as Entry[]).find((e) => e.label === "Dummy blocks")!;
    expect(manual.hint).toBe("with automation on"); // (automation off: the dummy's cards are moved by hand)
  });

  it("with several dummies: each its own Reset and blocks, Spawn for each, and Add until there are three", () => {
    const send = vi.fn();
    const d = (id: string, name: string) => player(id, { dummy: true, name });
    const two = table([player("p1"), d("p2", "Wall"), d("p3", "Target Dummy 2")]);
    expect(spawnOwners(two).map((o) => o.label)).toEqual(["You", "Wall", "Target Dummy 2"]);
    const labels = (dummyMenu(two, true, send) as Entry[]).map((e) => e.label);
    expect(labels).toEqual(["Reset Wall…", "Wall blocks", "Reset Target Dummy 2…", "Target Dummy 2 blocks", "Add another target dummy"]);
    const three = table([player("p1"), d("p2", "A"), d("p3", "B"), d("p4", "C")]);
    expect((dummyMenu(three, true, send) as Entry[]).map((e) => e.label)).not.toContain("Add another target dummy");
    vi.stubGlobal("window", { confirm: () => true });
    (dummyMenu(three, true, send) as Entry[]).find((e) => e.label === "Reset C…")!.onClick!();
    expect(send).toHaveBeenLastCalledWith({ type: "reset_dummy", player: "p4" });
    vi.unstubAllGlobals();
  });
});

describe("the Sandbox start's dummy seats", () => {
  it("names them as the server does", () => {
    expect([0, 1, 2].map(dummyName)).toEqual(["Target Dummy", "Target Dummy 2", "Target Dummy 3"]);
  });

  it("seats them in order, a blank name and life falling back to the defaults, three at most", () => {
    expect(dummyActions([
      { name: " Wall ", blocks: "all", life: "" },
      { name: "", blocks: "never", life: "20" },
      { name: "C", blocks: "chump", life: "abc" },
      { name: "D", blocks: "never", life: "" },
    ])).toEqual([
      { type: "add_dummy", blocks: "all", name: "Wall" },
      { type: "add_dummy", blocks: "never", name: "Target Dummy 2", life: 20 },
      { type: "add_dummy", blocks: "chump", name: "C" },
    ]);
    expect(dummyActions([])).toEqual([]);
  });

  it("remembers them for Same as last time, older one-checkbox records included", () => {
    expect(rememberedDummies(null)).toEqual([]);
    expect(rememberedDummies({ dummy: false })).toEqual([]);
    expect(rememberedDummies({ dummy: true, dummyBlocks: "chump" })).toEqual([{ name: "Target Dummy", blocks: "chump", life: "" }]);
    const seats = [{ name: "Wall", blocks: "all" as const, life: "20" }];
    expect(rememberedDummies({ dummies: seats, dummy: true })).toEqual(seats);
    expect(rememberedDummies({ dummies: [{ name: "X", blocks: "bogus" as never, life: "" }] })).toEqual([{ name: "X", blocks: "never", life: "" }]);
  });
});
