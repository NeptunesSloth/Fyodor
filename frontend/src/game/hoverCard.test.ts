import { beforeEach, describe, expect, it } from "vitest";
import { useGame } from "../state/gameStore";
import { freeSlot, hoverProps, placePreview, previewDock, previewKey, PREVIEW_RIGHT_GAP, PREVIEW_W, tallestSlot } from "./hoverCard";

const el = () => ({ isConnected: true }) as unknown as HTMLElement;
const enter = (props: ReturnType<typeof hoverProps>, target: HTMLElement) =>
  props.onPointerEnter({ currentTarget: target } as unknown as React.PointerEvent<HTMLElement>);
const leave = (props: ReturnType<typeof hoverProps>, target: HTMLElement) =>
  props.onPointerLeave({ currentTarget: target } as unknown as React.PointerEvent<HTMLElement>);

describe("the card preview's dock (game/hoverCard.ts)", () => {
  const vw = 1440;
  const panel = { left: vw - PREVIEW_RIGHT_GAP - PREVIEW_W, right: vw - PREVIEW_RIGHT_GAP, top: 90, bottom: 700 };

  it("docks right, wherever the pointer is, and goes left only when the hovered card itself is under it", () => {
    expect(previewDock(null, panel)).toBe("right");
    expect(previewDock({ left: 100, right: 180, top: 300, bottom: 410 }, panel)).toBe("right");
    // a card in the right half but clear of the panel: still right (the old rule flipped at 62% of the width)
    expect(previewDock({ left: 1000, right: 1080, top: 300, bottom: 410 }, panel)).toBe("right");
    // the card is under the panel's rectangle: left
    expect(previewDock({ left: 1200, right: 1290, top: 300, bottom: 410 }, panel)).toBe("left");
    // beside it in x but below it: right
    expect(previewDock({ left: 1200, right: 1290, top: 720, bottom: 800 }, panel)).toBe("right");
  });
});

describe("where the preview goes among the table's chrome (placePreview)", () => {
  const box = (left: number, top: number, right: number, bottom: number) => ({ left, top, right, bottom });
  const base = { vw: 1440, vh: 900, w: 262, minH: 300, top: 96, naturalH: 480 };

  it("finds the stretch of a column between the things in it", () => {
    expect(freeSlot(1166, 262, 96, 888, 300, [])).toEqual({ top: 96, height: 792 });
    // the turn panel below: the slot stops above it
    expect(freeSlot(1166, 262, 96, 888, 300, [box(1134, 620, 1424, 840)])).toEqual({ top: 96, height: 516 });
    // a strip at the top: the slot starts under it
    expect(freeSlot(0, 262, 96, 888, 300, [box(10, 70, 470, 155)])).toEqual({ top: 163, height: 725 });
    // too little room between two things: past the second one
    expect(freeSlot(0, 262, 96, 888, 300, [box(10, 70, 470, 155), box(10, 440, 205, 790)])).toEqual(null);
  });

  it("docks right under the stack pill, stopping above the turn panel (2D: the rules text was cut off by it)", () => {
    const dial = box(1134, 550, 1424, 770);
    const p = placePreview({ ...base, card: box(300, 250, 450, 410), obstacles: [dial, box(1368, 52, 1428, 80)] });
    expect(p).toEqual({ side: "right", left: 1440 - PREVIEW_RIGHT_GAP - 262, top: 96, maxH: 550 - 8 - 96 });
  });

  it("goes left only for a card under it, and then clear of both players' plates (2D: it covered them)", () => {
    const bobStrip = box(10, 70, 470, 155);
    const myRail = box(10, 435, 205, 790);
    const card = box(1080, 245, 1225, 410); // under the right dock
    const p = placePreview({ ...base, card, obstacles: [bobStrip, myRail] });
    expect(p.side).toBe("left");
    expect(p.top).toBeGreaterThanOrEqual(155); // under the opponent strip
    expect(p.left).toBeGreaterThanOrEqual(205); // beside my rail, not over my plate
  });
});

describe("a crowded small window (playtest nov 17: the preview's rules text under the turn dial)", () => {
  const box = (left: number, top: number, right: number, bottom: number) => ({ left, top, right, bottom });

  it("the tallest free stretch of a column, however short", () => {
    expect(tallestSlot(1000, 262, 96, 788, [box(980, 300, 1270, 340), box(980, 560, 1270, 788)])).toEqual({ top: 348, height: 204 });
    expect(tallestSlot(1000, 262, 96, 788, [box(980, 0, 1270, 800)])).toBeNull();
  });

  it("with no room to its liking anywhere, it takes the stretch above the dial instead of the window's height behind it", () => {
    // 1600x1000 at 125%: a 1280x800 page; the dial and its buttons from 330 down, a seat strip across the left
    const dial = box(1000, 330, 1270, 788);
    const strip = box(0, 60, 1000, 788);
    const p = placePreview({ vw: 1280, vh: 800, w: 262, minH: 300, top: 96, naturalH: 520, card: box(500, 400, 600, 540), obstacles: [dial, strip] });
    expect(p.side).toBe("right");
    expect(p.top + p.maxH).toBeLessThanOrEqual(330);
  });
});

describe("a hovered card from the page (hoverProps)", () => {
  beforeEach(() => useGame.setState({ hover: null }));

  it("sets the hover on enter and clears it on leave", () => {
    const a = el();
    const props = hoverProps("c1");
    enter(props, a);
    expect(useGame.getState().hover).toBe("c1");
    leave(props, a);
    expect(useGame.getState().hover).toBeNull();
  });

  it("clears a hover left behind when the element goes away (a hand card played, a stack entry resolved)", () => {
    const a = el();
    const props = hoverProps("c1");
    const cleanup = props.ref(a); // React 19 calls the ref with the element, then its cleanup when the element unmounts
    enter(props, a);
    expect(useGame.getState().hover).toBe("c1");
    cleanup?.();
    expect(useGame.getState().hover).toBeNull();
  });

  it("leaves another hover alone when an element goes away", () => {
    const [a, b] = [el(), el()];
    const first = hoverProps("c1");
    const second = hoverProps("c2");
    const goneA = first.ref(a);
    second.ref(b);
    enter(first, a);
    leave(first, a);
    enter(second, b); // now over another card
    goneA?.(); // the first card's element goes
    expect(useGame.getState().hover).toBe("c2");
    // and a hover set by the 3D table (no element) is not cleared by an element that never set it
    useGame.setState({ hover: "c9" });
    second.ref(b)?.();
    expect(useGame.getState().hover).toBe("c9");
  });

  it("does not clear on leave when the hover has already moved to another card", () => {
    const [a, b] = [el(), el()];
    const first = hoverProps("c1");
    enter(first, a);
    enter(hoverProps("c2"), b);
    leave(first, a); // (a late leave from the first card)
    expect(useGame.getState().hover).toBe("c2");
  });

  it("has a stable ref per card, so a re-render does not count as the element going away", () => {
    expect(hoverProps("c1").ref).toBe(hoverProps("c1").ref);
  });
});

describe("Esc closes the preview (previewKey)", () => {
  beforeEach(() => useGame.setState({ hover: null }));

  it("clears the hover on Escape, and lets the key through when nothing is shown", () => {
    useGame.setState({ hover: "c1" });
    expect(previewKey({ key: "Escape" })).toBe(true);
    expect(useGame.getState().hover).toBeNull();
    expect(previewKey({ key: "Escape" })).toBe(false);
    useGame.setState({ hover: "c1" });
    expect(previewKey({ key: "a" })).toBe(false);
    expect(useGame.getState().hover).toBe("c1");
  });
});
