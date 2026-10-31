import { expect, test } from "@playwright/test";
import { ALICE_DECK, BOB_DECK, menuPath } from "./helpers";

/**
 * The scripted Tabletop Simulator tables' chores (docs/UI_REFERENCE_STUDY.md §25–26): reveal until a type, get a
 * basic land, discard at random, the seat buttons, counter steppers on the card, the owner gem and exact copy.
 */
test("library and hand chores, seat buttons, counter steppers, owner gem, exact copy", async ({ page }) => {
  for (const text of [ALICE_DECK, BOB_DECK]) expect((await page.request.post("/api/decks", { data: { text } })).ok()).toBeTruthy();
  const decks = (await (await page.request.get("/api/decks")).json()) as { id: string; name: string }[];
  const res = await page.request.post("/api/games", {
    data: {
      name: "Chores", mode: "local", shuffle: false, first_player: 0, mulligan_rule: "none",
      players: [{ name: "Alice", deck_id: decks[0]!.id }, { name: "Bob", deck_id: decks[1]!.id }],
    },
  });
  const gameId = ((await res.json()) as { game: { id: string } }).game.id;
  const view = async () => (await (await page.request.get(`/api/games/${gameId}/view?viewer=p1`)).json()) as {
    zones: Record<string, unknown>; cards: Record<string, { name?: string; zone: string; counters?: Record<string, number> }>;
  };
  await page.goto(`/#/game/${gameId}`);
  const library = page.locator('[data-drop="p1:library"]');
  await expect(library).toBeVisible();

  // reveal until a land: the server reads the types; the dialog offers where the cards go
  await library.click();
  await menuPath(page, "Reveal until…", "a land");
  const dig = page.getByTestId("dig-dialog");
  await expect(dig).toBeVisible();
  await expect(dig).toContainText("Found");
  await dig.getByRole("button", { name: "Put into your hand" }).click();
  await expect(page.locator("main.table > .hand .hand-card")).toHaveCount(1);
  await dig.getByTestId("dig-bottom").click();
  await expect(dig).toHaveCount(0); // everything placed, the dialog closes itself
  const hand = (await view()).zones["p1:hand"] as string[];
  expect((await view()).cards[hand[0]!]!.name).toBe("Command Tower");

  // get a basic land onto the battlefield (then the library is shuffled)
  await library.click();
  await menuPath(page, "Get a basic land", "Island onto the battlefield");
  await expect(page.locator('[data-drop="p1:battlefield"] .table-card')).toHaveCount(1);

  // the seat buttons: click draws one, right-click three
  await page.getByTestId("seat-btn-draw").click();
  await expect(page.locator("main.table > .hand .hand-card")).toHaveCount(2);
  await page.getByTestId("seat-btn-draw").click({ button: "right" });
  await expect(page.locator("main.table > .hand .hand-card")).toHaveCount(5);
  // hover a button and type a number: mill 2
  const libCount = async () => ((await view()).zones["p1:library"] as { count: number }).count;
  const before = await libCount();
  await page.getByTestId("seat-btn-mill").hover();
  await page.keyboard.press("2");
  await expect(page.getByTestId("seat-btn-mill")).toContainText("2"); // the count being typed, on the button
  await expect.poll(libCount).toBe(before - 2);

  // discard at random, from the Hand menu
  await page.getByTestId("hand-sort").click();
  await menuPath(page, "Discard a card at random");
  await expect(page.locator("main.table > .hand .hand-card")).toHaveCount(4);

  // counter steppers on the card: click +1, right-click −1
  const island = page.locator('[data-drop="p1:battlefield"] .table-card').first();
  const islandId = (await island.getAttribute("data-card-id"))!;
  await page.request.post(`/api/games/${gameId}/actions`, { data: { action: { type: "counter", card_ids: [islandId], kind: "charge", delta: 1 } } });
  const chip = island.locator(".counter").first();
  await expect(chip).toContainText("1");
  await chip.click();
  await expect(chip).toContainText("2");
  await chip.click({ button: "right" });
  await expect(chip).toContainText("1");

  // exact copy keeps the counter; a borrowed card wears its owner's gem
  await island.click({ button: "right" });
  await menuPath(page, "Create copy", "Exact copy");
  await expect.poll(async () => Object.values((await view()).cards).filter((c) => c.zone === "p1:battlefield" && c.counters?.charge === 1).length).toBe(2);
  await page.request.post(`/api/games/${gameId}/actions`, { data: { action: { type: "set_controller", card_ids: [islandId], player: "p2" } } });
  await expect(page.locator(`[data-card-id="${islandId}"] [data-testid="owner-gem"]`)).toHaveText("A");
});
