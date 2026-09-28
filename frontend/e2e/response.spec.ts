import { expect, test } from "@playwright/test";
import { act, keepAll, serverView, startLanGame } from "./helpers";

test("Response helper: cast asks the table, next step waits for PASS, auto-pass, host force", async ({ browser }) => {
  const { host, guest, gameId } = await startLanGame(browser);
  const alice = host.page;
  const bob = guest.page;
  await keepAll(alice, bob);

  // Alice casts a spell: Bob is asked, Alice sees whom she's waiting on.
  const view = await serverView(alice, gameId);
  const hand = (view.zones as Record<string, string[]>)["p1:hand"]!;
  await act(alice, gameId, { type: "move", card_ids: [hand[0]], to: { zone: "stack" } });
  await expect(bob.getByTestId("response-bar")).toContainText("Alice wants to cast");
  await expect(alice.getByTestId("response-status")).toHaveText("Waiting on Bob");
  await expect(alice.getByTestId("pass")).toHaveCount(0);
  await bob.keyboard.press("p"); // PASS via the hotkey
  await expect(alice.getByTestId("response-bar")).toHaveCount(0);

  // Next step asks first and happens when Bob passes.
  await act(alice, gameId, { type: "resolve_top" }); // everyone just passed: resolves at once
  await alice.keyboard.press("n");
  await expect(bob.getByTestId("response-bar")).toContainText("wants to move to upkeep");
  expect(((await serverView(alice, gameId)).turn as { phase: string }).phase).toBe("untap");
  await bob.getByTestId("pass").click();
  await expect.poll(async () => ((await serverView(alice, gameId)).turn as { phase: string }).phase).toBe("upkeep");

  // RESPOND puts Alice's request on hold; she can still go ahead anyway (never locked).
  await alice.keyboard.press("n");
  await bob.getByTestId("respond").click();
  await expect(alice.getByTestId("response-status")).toHaveText("Bob is responding");
  await alice.getByTestId("proceed").click();
  await expect(alice.getByTestId("response-bar")).toHaveCount(0);

  // AUTO-PASS: Bob passes every check for the rest of the turn.
  await bob.keyboard.press("Shift+P");
  await expect(bob.getByTestId("response-bar")).toContainText("Auto-passing this turn");
  const before = ((await serverView(alice, gameId)).turn as { phase: string }).phase;
  await alice.keyboard.press("n");
  await expect.poll(async () => ((await serverView(alice, gameId)).turn as { phase: string }).phase).not.toBe(before);

  // Host force: Bob opens a check, the host (Alice) forces it closed.
  await bob.keyboard.press("Shift+P"); // stop auto-passing
  await act(bob, gameId, { type: "phase", to: "next" });
  await expect(alice.getByTestId("force-pass")).toBeVisible();
  await expect(bob.getByTestId("force-pass")).toHaveCount(0);
  await alice.getByTestId("force-pass").click();
  await expect(bob.getByTestId("response-bar")).toHaveCount(0);

  await host.context.close();
  await guest.context.close();
});
