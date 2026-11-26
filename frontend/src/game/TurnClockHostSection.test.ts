import { createElement } from "react";
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { ClockRow, clockRowButtons } from "./TurnClockHostSection";
import { commitNumber } from "../components/CommitNumber";

describe("host turn clock requests", () => {
  it("+1:00 sends 60, +5:00 sends 300, the reconnect grace sends 120 (seconds)", () => {
    const b = clockRowButtons(true);
    expect(b.map((x) => x.label)).toEqual(["+1:00", "+5:00", "Give 2 more minutes to reconnect"]);
    expect(b[0]!.body("p2")).toEqual({ op: "add_time", player: "p2", seconds: 60 });
    expect(b[1]!.body("p2")).toEqual({ op: "add_time", player: "p2", seconds: 300 });
    expect(b[2]!.body("p2")).toEqual({ op: "grace", player: "p2", seconds: 120 });
  });
  it("the reconnect button exists only for a player who is away", () => {
    expect(clockRowButtons(false).map((x) => x.label)).toEqual(["+1:00", "+5:00"]);
    const row = (away: boolean) => renderToStaticMarkup(createElement(ClockRow, { pid: "p2", name: "Bob", away, busy: false, go: () => undefined }));
    expect(row(false)).not.toContain("reconnect");
    expect(row(true)).toContain("Give 2 more minutes to reconnect");
  });
  it("busy disables every button", () => {
    const html = renderToStaticMarkup(createElement(ClockRow, { pid: "p2", name: "Bob", away: true, busy: true, go: () => undefined }));
    expect(html.match(/<button/g)?.length).toBe(3);
    expect(html.match(/disabled=""/g)?.length).toBe(3);
  });
});

describe("commitNumber", () => {
  it("blank, zero and junk are refused and keep the previous value; the rest clamps", () => {
    expect(commitNumber("", 30, 5, 300)).toEqual({ value: 30, ok: false });
    expect(commitNumber("0", 2, 1, 30)).toEqual({ value: 2, ok: false });
    expect(commitNumber("abc", 30, 5, 300)).toEqual({ value: 30, ok: false });
    expect(commitNumber("1", 30, 5, 300)).toEqual({ value: 5, ok: true });
    expect(commitNumber("999", 30, 5, 300)).toEqual({ value: 300, ok: true });
    expect(commitNumber("12.6", 30, 5, 300)).toEqual({ value: 13, ok: true });
  });
});
