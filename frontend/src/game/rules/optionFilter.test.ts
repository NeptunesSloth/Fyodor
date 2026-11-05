import { describe, expect, it } from "vitest";
import { filterOptions } from "./optionFilter";

const opts = [{ label: "Elf" }, { label: "Elemental" }, { label: "Goblin" }];

describe("filterOptions", () => {
  it("filters case-insensitively by label and keeps all for blank text", () => {
    expect(filterOptions(opts, "ELE").map((o) => o.label)).toEqual(["Elemental"]);
    expect(filterOptions(opts, " el ").map((o) => o.label)).toEqual(["Elf", "Elemental"]);
    expect(filterOptions(opts, "  ")).toBe(opts);
    expect(filterOptions(opts, "zz")).toEqual([]);
  });
});
