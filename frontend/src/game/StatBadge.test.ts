import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { StatBadge } from "./TableCard";

describe("StatBadge", () => {
  it("shows the current P/T, colored by direction, with gained keywords", () => {
    const up = renderToStaticMarkup(createElement(StatBadge, { stats: { pt: [3, 3], base: ["2", "2"], gained: ["haste"] } }));
    expect(up).toContain("stat-badge up");
    expect(up).toContain("3/3");
    expect(up).toContain("Has: haste");
    const down = renderToStaticMarkup(createElement(StatBadge, { stats: { pt: [1, 1], base: ["2", "2"] } }));
    expect(down).toContain("stat-badge down");
  });
});
