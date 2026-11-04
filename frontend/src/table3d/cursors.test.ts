import { describe, expect, it } from "vitest";
import { CURSOR_X, CURSOR_Y, CursorOutbox, CursorTrack, cursorToWorld, FADE_MS, IDLE_MS, overTable, SEND_EVERY, worldToCursor } from "./cursors";
import { seats, tableSize, toLocal, toWorld, virtualToLocal } from "./layout";

const ORDER = ["p1", "p2", "p3", "p4", "p5"];

/** A card's centre in a viewer's world (its battlefield top-left in virtual units, as the server keeps it). */
function cardCentre(viewer: string, owner: string, vx: number, vy: number): [number, number] {
  const seat = seats(ORDER, viewer).find((s) => s.player === owner)!;
  return toWorld(seat, ...virtualToLocal(vx, vy));
}

describe("live cursors: the viewer-independent frame", () => {
  it("a point over a card on A's screen lands over the same card on B's", () => {
    for (const [a, b] of [["p1", "p3"], ["p2", "p5"], ["p4", "p1"]] as const) {
      for (const owner of ORDER) {
        // a little off the card's centre, in its owner's mat frame
        const seatA = seats(ORDER, a).find((s) => s.player === owner)!;
        const [l0x, l0z] = virtualToLocal(420, 230);
        const [ax, az] = toWorld(seatA, l0x + 0.1, l0z - 0.05);
        const spot = worldToCursor(seats(ORDER, a), ax, az)!;
        expect(spot.player).toBe(owner); // over a battlefield: that seat
        const [bx, bz] = cursorToWorld(seats(ORDER, b), spot)!;
        // the same offset from the card, turned with the owner's mat on B's screen
        const seatB = seats(ORDER, b).find((s) => s.player === owner)!;
        const [cx, cz] = cardCentre(b, owner, 420, 230);
        const [lx, lz] = toLocal(seatB, bx, bz);
        const [clx, clz] = toLocal(seatB, cx, cz);
        expect(lx - clx).toBeCloseTo(0.1, 2);
        expect(lz - clz).toBeCloseTo(-0.05, 2);
      }
    }
  });

  it("off the battlefields (the aisle, the wood) the spot is kept by the nearest seat, the same on every screen", () => {
    const mine = seats(ORDER, "p1");
    const size = tableSize(mine);
    for (const [wx, wz] of [[0, 0], [size.w / 2 - 0.2, 0.3], [-3, size.d / 2], [1.5, -size.d / 2 - 0.4]] as const) {
      const spot = worldToCursor(mine, wx, wz)!;
      expect(spot.x).toBeGreaterThanOrEqual(CURSOR_X[0]);
      expect(spot.x).toBeLessThanOrEqual(CURSOR_X[1]);
      expect(spot.y).toBeGreaterThanOrEqual(CURSOR_Y[0]);
      expect(spot.y).toBeLessThanOrEqual(CURSOR_Y[1]);
      const back = cursorToWorld(mine, spot)!;
      expect(back[0]).toBeCloseTo(wx, 1);
      expect(back[1]).toBeCloseTo(wz, 1);
      // and on p4's screen it sits at the same place relative to that seat's mat (the rows are laid out per viewer,
      // so the far mats are not one rigid turn of mine: the nearest seat is the reference)
      const theirs = seats(ORDER, "p4");
      const there = cursorToWorld(theirs, spot)!;
      const s = mine.find((x) => x.player === spot.player)!;
      const t = theirs.find((x) => x.player === spot.player)!;
      const [l1x, l1z] = toLocal(s, wx, wz);
      const [l2x, l2z] = toLocal(t, ...there);
      expect(l2x).toBeCloseTo(l1x, 1);
      expect(l2z).toBeCloseTo(l1z, 1);
    }
  });

  it("only the table top and its rail count as over the table; a seat not at this table can't be placed", () => {
    const size = tableSize(seats(ORDER, "p1"));
    expect(overTable(size, 0, 0)).toBe(true);
    expect(overTable(size, size.w / 2 + 0.3, 0)).toBe(true);
    expect(overTable(size, size.w / 2 + 3, 0)).toBe(false);
    expect(overTable(size, 0, -size.d)).toBe(false);
    expect(cursorToWorld(seats(ORDER, "p1"), { player: "p9", x: 0, y: 0 })).toBeNull();
  });
});

describe("live cursors: easing and fading", () => {
  it("appears where it first is, then eases toward each new position", () => {
    const t = new CursorTrack();
    expect(t.opacity(0)).toBe(0); // nothing yet
    t.target(2, 3, 0);
    expect([t.x, t.z]).toEqual([2, 3]);
    t.target(4, 3, 10);
    t.step(1 / 60, 20, false);
    expect(t.x).toBeGreaterThan(2);
    expect(t.x).toBeLessThan(4);
    for (let i = 0; i < 60; i++) t.step(1 / 60, 30, false);
    expect(t.x).toBeCloseTo(4, 3);
  });

  it("snaps with reduced motion", () => {
    const t = new CursorTrack();
    t.target(0, 0, 0);
    t.target(5, -1, 10);
    t.step(1 / 60, 20, true);
    expect([t.x, t.z]).toEqual([5, -1]);
  });

  it("fades out after a few seconds without a move, and comes back on the next", () => {
    const t = new CursorTrack();
    t.target(1, 1, 1000);
    expect(t.step(0.016, 1000 + IDLE_MS - 1, false)).toBe(1);
    const mid = t.step(0.016, 1000 + IDLE_MS + FADE_MS / 2, false);
    expect(mid).toBeGreaterThan(0.3);
    expect(mid).toBeLessThan(0.7);
    expect(t.step(0.016, 1000 + IDLE_MS + FADE_MS + 1, false)).toBe(0);
    t.target(1.2, 1, 9000);
    expect(t.step(0.016, 9001, false)).toBe(1);
  });

  it("fades at once when they leave the table, and reappears in place when they come back", () => {
    const t = new CursorTrack();
    t.target(1, 1, 0);
    t.leave(500);
    expect(t.opacity(500)).toBe(1);
    expect(t.opacity(500 + FADE_MS)).toBe(0);
    t.target(-3, 2, 2000);
    expect([t.x, t.z]).toEqual([-3, 2]); // not a slide across the table from where it left
    expect(t.opacity(2000)).toBe(1);
  });
});

describe("live cursors: what goes out", () => {
  it("at most ~15 a second, always the latest, never the same spot twice, one gone when it leaves", () => {
    const o = new CursorOutbox();
    expect(o.poll(0)).toBeNull(); // never on the table: nothing, not even a gone
    o.move({ player: "p1", x: 1, y: 1 });
    expect(o.poll(0)).toEqual({ player: "p1", x: 1, y: 1 });
    o.move({ player: "p1", x: 2, y: 1 });
    o.move({ player: "p1", x: 3, y: 1 });
    expect(o.poll(SEND_EVERY - 1)).toBeNull();
    expect(o.poll(SEND_EVERY)).toEqual({ player: "p1", x: 3, y: 1 }); // the trailing send carries the latest
    expect(o.poll(SEND_EVERY * 3)).toBeNull(); // it hasn't moved
    o.move(null);
    expect(o.poll(SEND_EVERY * 3 + 1)).toEqual({ gone: true });
    expect(o.poll(SEND_EVERY * 5)).toBeNull();
    o.leave();
    expect(o.poll(SEND_EVERY * 6)).toBeNull();
    o.move({ player: "p2", x: 3, y: 1 });
    expect(o.poll(SEND_EVERY * 7)).toEqual({ player: "p2", x: 3, y: 1 });
    // the same table spot, now over a card (it moved under the pointer): that is news
    o.move({ player: "p2", x: 3, y: 1, card: "c1", cx: 0.2, cy: -0.4 });
    expect(o.poll(SEND_EVERY * 8)).toEqual({ player: "p2", x: 3, y: 1, card: "c1", cx: 0.2, cy: -0.4 });
  });
});
