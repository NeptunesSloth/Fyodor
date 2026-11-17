/** -- resolving progress -- the connection passes on interim views only on top of the update it has (never before the first snapshot,
 * never after the action's own update), and they never move its revision. */
import { describe, expect, it, vi } from "vitest";
import { GameConnection } from "./gameSocket";

const view = (revision: number) => ({ game: { id: "g1", revision } });

describe("interim messages", () => {
  it("are passed on only on top of the current revision", () => {
    const onState = vi.fn();
    const onInterim = vi.fn();
    const conn = new GameConnection("g1", {}, { onState, onInterim, onLobby: vi.fn(), onStatus: vi.fn(), onClosedByServer: vi.fn() });
    const receive = (m: unknown) => (conn as unknown as { onMessage: (d: string) => void }).onMessage(JSON.stringify(m));
    const progress = { resolved: 4, left: 6, by: "p1" };

    receive({ type: "interim", revision: 0, view: view(0), progress }); // before the first snapshot: dropped
    expect(onInterim).not.toHaveBeenCalled();
    receive({ type: "state", revision: 7, view: view(7) });
    receive({ type: "interim", revision: 7, view: view(7), progress });
    receive({ type: "interim", revision: 7, progress }); // (count only)
    expect(onInterim.mock.calls.map((c) => c[0] === null)).toEqual([false, true]);
    expect(conn.revision).toBe(7);
    receive({ type: "state", revision: 8, view: view(8) }); // the action's own update: no gap, no resync
    receive({ type: "interim", revision: 7, view: view(7), progress }); // late: dropped
    expect(onInterim).toHaveBeenCalledTimes(2);
    expect(onState).toHaveBeenCalledTimes(2);
    expect(conn.revision).toBe(8);
  });
});
