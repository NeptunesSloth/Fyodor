import { expect, test } from "@playwright/test";
import { act, keepAll, menuPath, playFromHand, seatToken, serverView, startLanGame } from "./helpers";

test("a saved custom action runs from the card menu as one undoable action; test objects are marked", async ({ browser }) => {
  const { host, guest, gameId } = await startLanGame(browser);
  const alice = host.page;
  const bob = guest.page;
  await keepAll(alice, bob);
  const card = await playFromHand(alice);
  const onAlice = alice.locator(`.table-card[data-card-id="${card}"]`);

  // build and save a macro from safe primitives
  await onAlice.click({ button: "right" });
  await menuPath(alice, "Custom actions", "New custom action…");
  await alice.getByTestId("macro-name").fill("Grow and drain");
  await alice.locator(".macro-editor").getByRole("button", { name: "+ Add step" }).click();
  const step2 = alice.locator(".macro-step").nth(1);
  await step2.locator("select").first().selectOption("CHANGE_LIFE");
  await step2.locator("select").nth(1).selectOption("each_opponent");
  await step2.locator("input").fill("-2");
  await alice.getByTestId("macro-save").click();
  await expect(alice.getByTestId("macro-name")).toHaveCount(0);

  // run it from the card menu
  await onAlice.click({ button: "right" });
  await menuPath(alice, "Custom actions", "Grow and drain");
  await expect(bob.getByTestId("life-p2")).toHaveText("38");
  const view = (await serverView(bob, gameId)) as { cards: Record<string, { counters?: Record<string, number> }> };
  expect(view.cards[card]!.counters).toEqual({ "+1/+1": 1 });

  // one history entry: a single undo takes back all of it
  const token = await seatToken(alice, gameId);
  expect((await alice.request.post(`/api/games/${gameId}/undo`, { data: {}, headers: { "X-Seat-Token": token! } })).ok()).toBeTruthy();
  await expect(bob.getByTestId("life-p2")).toHaveText("40");
  const after = (await serverView(bob, gameId)) as { cards: Record<string, { counters?: Record<string, number> }> };
  expect(after.cards[card]!.counters ?? {}).toEqual({});

  // test objects: off until the host allows them, then visibly marked for everyone
  await act(alice, gameId, { type: "configure", allow_test_objects: true });
  const found = (await (await alice.request.get(`/api/cards/search?q=Opt`)).json()) as { results: { id: string }[] };
  const opt = found.results[0]!;
  await act(alice, gameId, { type: "spawn_card", card_id: opt.id });
  await expect(bob.locator(".table-card .mark.test")).toHaveCount(1);

  await host.context.close();
  await guest.context.close();
});
