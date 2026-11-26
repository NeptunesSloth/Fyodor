import { beforeEach, describe, expect, it, vi } from "vitest";
import { useGame } from "../../state/gameStore";
import { passOrResolve, RESOLVE_UNTIL } from "./intents";
import { passingLabel, passTitle, RESOLVE_ALL_TITLE } from "./RulesHud";

// -- runaway chains -- RESOLVE (the priority bar's big button and P) resolves the top object only: a chain of triggers goes one press at
// a time, so every draw is seen and a drawn instant can answer it (backend/tests/test_rules_runaway_chains.py).
const sent: unknown[] = [];

beforeEach(() => {
  sent.length = 0;
  useGame.setState({ view: null, actingAs: null, send: vi.fn(async (a) => { sent.push(a); return true; }) });
});

describe("resolve the top object", () => {
  it("resolves the top object and a run of your own triggers when something is on the stack (-- smart resolve --)", async () => {
    await passOrResolve(3);
    expect(sent).toEqual([{ type: "pass_priority", until: "own_triggers" }]);
    expect(RESOLVE_UNTIL).toBe("own_triggers");
  });

  it("is a plain pass with an empty stack", async () => {
    await passOrResolve(0);
    expect(sent).toEqual([{ type: "pass_priority" }]);
  });

  it("says what each button does", () => {
    expect(passTitle(true)).toMatch(/top object/);
    expect(passTitle(true)).toMatch(/priority back/);
    expect(passTitle(false)).toBe("Pass priority (P)");
    expect(RESOLVE_ALL_TITLE).toMatch(/draw a card you could cast/);
    expect(RESOLVE_ALL_TITLE).toMatch(/20 objects/);
  });

  it("names a pass in progress in words", () => {
    expect(passingLabel("stack_changes")).toBe("Resolving the top object");
    expect(passingLabel("own_triggers")).toBe("Resolving your triggers");
    expect(passingLabel("stack_empty")).toBe("Resolving all");
    expect(passingLabel("some_new_mode")).toBe("Passing until some new mode");
  });
});
