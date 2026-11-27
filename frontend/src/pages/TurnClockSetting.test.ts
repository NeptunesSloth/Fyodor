import { createElement, type ReactElement } from "react";
import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { DEFAULT_CLOCK, TurnClockSetting, clockPatch } from "./TurnClockSetting";
import { CommitNumber } from "../components/CommitNumber";

const html = (c: object) => renderToStaticMarkup(createElement(TurnClockSetting, { value: c as never, onChange: vi.fn() }));

/** Every element in a (hookless) component's output tree. */
function walk(node: unknown, out: ReactElement[] = []): ReactElement[] {
  if (Array.isArray(node)) node.forEach((n) => walk(n, out));
  else if (node && typeof node === "object" && "props" in node) {
    out.push(node as ReactElement);
    walk((node as ReactElement<{ children?: unknown }>).props.children, out);
  }
  return out;
}
type Handler = { onChange: (e: unknown) => void; onCommit: (n: number) => void };

describe("TurnClockSetting", () => {
  it("always sends the full clock object, never a partial one", () => {
    const patch = clockPatch({ ...DEFAULT_CLOCK, on: true, bank_seconds: 900 }, { at_zero: "show" });
    expect(patch.clock).toEqual({ on: true, bank_seconds: 900, buffer_seconds: 30, at_zero: "show", grace_seconds: 120 });
    expect(Object.keys(clockPatch(undefined, { on: true }).clock).sort()).toEqual(["at_zero", "bank_seconds", "buffer_seconds", "grace_seconds", "on"]);
  });
  it("the lobby's own handlers send the full object for each control", () => {
    const sent: { clock: Record<string, unknown> }[] = [];
    const tree = walk(TurnClockSetting({ value: { ...DEFAULT_CLOCK, on: true, bank_seconds: 900 }, onChange: (v) => sent.push(v as never) }));
    const box = tree.find((e) => e.type === "input" && (e.props as { type?: string }).type === "checkbox")!;
    (box.props as Handler).onChange({ target: { checked: false } });
    (tree.find((e) => e.type === "select")!.props as Handler).onChange({ target: { value: "show" } });
    const nums = tree.filter((e) => e.type === CommitNumber);
    (nums[0]!.props as Handler).onCommit(40);
    (nums[1]!.props as Handler).onCommit(45);
    expect(sent).toHaveLength(4);
    for (const s of sent) expect(Object.keys(s.clock).sort()).toEqual(["at_zero", "bank_seconds", "buffer_seconds", "grace_seconds", "on"]);
    expect(sent[0]!.clock).toMatchObject({ on: false, bank_seconds: 900 });
    expect(sent[1]!.clock).toMatchObject({ on: true, at_zero: "show" });
    expect(sent[2]!.clock).toMatchObject({ bank_seconds: 2400 });
    expect(sent[3]!.clock).toMatchObject({ buffer_seconds: 45, bank_seconds: 900 });
  });
  it("shows the hints", () => {
    expect(html({ ...DEFAULT_CLOCK, on: false })).toContain("Off: no clock.");
    expect(html({ ...DEFAULT_CLOCK, on: true })).toContain("it never concedes for anyone");
    expect(html({ ...DEFAULT_CLOCK, on: true, at_zero: "show" })).toContain("the clock just reads 0:00; nothing happens.");
  });
});
