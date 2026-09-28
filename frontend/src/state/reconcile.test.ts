import { describe, expect, it } from "vitest";
import { reconcile } from "./reconcile";

describe("reconcile", () => {
  it("keeps references for unchanged branches", () => {
    const prev = { cards: { a: { id: "a", tapped: false }, b: { id: "b", tapped: false } }, zones: { hand: ["a", "b"] } };
    const next = JSON.parse(JSON.stringify(prev));
    next.cards.b.tapped = true;
    const out = reconcile(prev, next);
    expect(out).toEqual(next);
    expect(out.cards.a).toBe(prev.cards.a);
    expect(out.cards.b).not.toBe(prev.cards.b);
    expect(out.zones).toBe(prev.zones);
    expect(out.zones.hand).toBe(prev.zones.hand);
    expect(out).not.toBe(prev);
  });

  it("returns prev when nothing changed", () => {
    const prev = { a: [1, 2, { x: 1 }], b: null };
    expect(reconcile(prev, JSON.parse(JSON.stringify(prev)))).toBe(prev);
  });

  it("handles added and removed keys and array length changes", () => {
    const prev: { cards: Record<string, { id: string }>; list: number[] } = { cards: { a: { id: "a" } }, list: [1, 2, 3] };
    const next: typeof prev = { cards: { b: { id: "b" } }, list: [1, 2] };
    const out = reconcile(prev, next);
    expect(out).toEqual(next);
    expect(Object.keys(out.cards)).toEqual(["b"]);
    expect(out.list).toEqual([1, 2]);
  });

  it("replaces when types differ", () => {
    expect(reconcile<unknown>({ a: 1 }, [1])).toEqual([1]);
    expect(reconcile<unknown>(null, { a: 1 })).toEqual({ a: 1 });
  });
});
