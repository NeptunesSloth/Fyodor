import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

// (read from disk: the test runner hands a stylesheet import back empty)
const read = (path: string) => readFileSync(new URL(path, import.meta.url), "utf8");
const lobby = read("./lobby.css");
const game = read("../game/game.css");
const seat = read("../game/seat.css");

/*
 * Every stylesheet is global once bundled, so a lobby rule on a class the game screen also uses reaches the table (the top
 * bar's room code, the seat plate's name button), and the other way round. The two screens style their own.
 */

/** Each rule's selectors and declarations (comments dropped; at-rule preludes like @media skipped, their rules kept). */
function rules(css: string): { selectors: string[]; body: string }[] {
  const clean = css.replace(/\/\*[\s\S]*?\*\//g, "");
  return [...clean.matchAll(/(?:^|(?<=[{};]))\s*([^{};@][^{};]*)\{([^{}]*)\}/g)].map((m) => ({ selectors: m[1]!.split(",").map((s) => s.trim()), body: m[2]! }));
}

const SHARED = /\.(seat-who|room-code)\b/;

describe("the lobby's styles stay in the lobby, the game screen's in the game", () => {
  it("every lobby rule for a class the table also uses is scoped to the lobby", () => {
    const loose = rules(lobby).flatMap((r) => r.selectors).filter((s) => SHARED.test(s) && !s.startsWith(".lobby "));
    expect(loose).toEqual([]);
  });

  it("the game's room code is the top bar's own, so it doesn't reach the lobby's", () => {
    const loose = rules(game + seat).flatMap((r) => r.selectors).filter((s) => /\.room-code\b/.test(s) && !s.startsWith(".game-top "));
    expect(loose).toEqual([]);
  });

  it("the seat plate's name button says how it is laid out itself (it used to come from the lobby's rule)", () => {
    const own = rules(seat).find((r) => r.selectors.includes(".seat-who"));
    expect(own?.body).toMatch(/display:\s*flex;/);
    expect(own?.body).toMatch(/flex-direction:\s*column/);
    expect(own?.body).toMatch(/line-height:\s*1\.2/);
    expect(own?.body).toMatch(/min-width:\s*0/);
  });
});
