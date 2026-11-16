import { describe, expect, it, vi } from "vitest";
import type { GameView, PlayerView } from "../types/game";
import { dummyIsOut, dummyMenu, dummyOf, spawnOwners } from "./targetDummy";

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
    expect(send).toHaveBeenLastCalledWith({ type: "reset_dummy" });
    vi.unstubAllGlobals();
    const lost = table([player("p1"), player("p2", { dummy: true, life: 0 })], { rules: { lost: { p2: "0 or less life" }, conceded: [] } } as unknown as Partial<GameView>);
    expect((dummyMenu(lost, true, send) as Entry[])[0]!.label).toBe("Restore dummy…");
  });
});
