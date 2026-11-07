import { describe, expect, it } from "vitest";


describe("keywords on a permanent", () => {
  it("lists counters and gained keywords, less lost ones, with distinct tile codes", async () => {
    const { keywordsNow, keywordCode } = await import("./counters");
    expect(keywordsNow({ flying: 1, deathtouch: 1, "+1/+1": 2 }, ["Defender", "lifelink"], ["flying"])).toEqual(["Deathtouch", "Defender", "Lifelink"]);
    expect(keywordCode("deathtouch")).not.toBe(keywordCode("defender"));
    expect(keywordCode("flying")).not.toBe(keywordCode("flash"));
  });
});
