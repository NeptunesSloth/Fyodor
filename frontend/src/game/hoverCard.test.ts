import { beforeEach, describe, expect, it } from "vitest";
import { useGame } from "../state/gameStore";
import { hoverProps, previewDock, previewKey, PREVIEW_RIGHT_GAP, PREVIEW_W } from "./hoverCard";

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
