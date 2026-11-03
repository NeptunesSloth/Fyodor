import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { PlayerView } from "../types/game";
import { CommanderMatrix, DealtList } from "./CommanderDamageViews";

const player = (id: string, name: string, cmdrs: string[], dmg: Record<string, number> = {}) => ({
  id, name, color: "#888", commander_damage: dmg,
  commanders: cmdrs.map((k) => ({ key: k, name: `${k}, the Tester`, card_id: null, instance_id: null, zone: null, tax: 0 })),
});

describe("commander damage views", () => {
  const players = [player("p1", "Ann", ["atraxa"]), player("p2", "Bob", ["edgar"], { atraxa: 8 }), player("p3", "Cara", [], { atraxa: 21 })] as unknown as PlayerView[];
  it("the inspector note names each opponent with the damage dealt, marking lethal", () => {
    const html = renderToStaticMarkup(createElement(DealtList, { players, commander: "atraxa" }));
    expect(html).toContain("Commander damage dealt");
    expect(html).toMatch(/Bob <b>8<\/b>/);
    expect(html).toMatch(/cmdr-dealt-row lethal[^>]*>.*Cara <b>21<\/b>/);
  });
  it("the matrix has a column per player and a row per commander", () => {
    const html = renderToStaticMarkup(createElement(CommanderMatrix, { players }));
    expect((html.match(/<th scope="col"/g) ?? []).length).toBe(3);
    expect((html.match(/<th scope="row"/g) ?? []).length).toBe(2);
    expect(html).toContain(">atraxa<"); // the name before the comma
    expect(html).toMatch(/class="lethal">21<span class="sr-only"> lethal/);
  });
});
