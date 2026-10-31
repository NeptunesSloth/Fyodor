import { expect, test } from "@playwright/test";
import { ALICE_DECK, BOB_DECK } from "./helpers";

const KRENKO_LIST = `Commander
1 Krenko, Mob Boss
Deck
1 Lightning Bolt
1 Pyroblast
12 Mountain
`;

/** The scripted tables' importer, on the table: find a card, place a new deck, restart, all without leaving. */
test("card importer at the table: find a card, place a deck, restart without leaving", async ({ page }) => {
  for (const text of [ALICE_DECK, BOB_DECK]) expect((await page.request.post("/api/decks", { data: { text } })).ok()).toBeTruthy();
  const decks = (await (await page.request.get("/api/decks")).json()) as { id: string; name: string }[];
  const res = await page.request.post("/api/games", {
    data: {
      name: "Importer", mode: "local", shuffle: false, first_player: 0, mulligan_rule: "none",
      players: [{ name: "Alice", deck_id: decks[0]!.id }, { name: "Bob", deck_id: decks[1]!.id }],
    },
  });
  const gameId = ((await res.json()) as { game: { id: string } }).game.id;
  type V = { players: { id: string; deck_name: string | null; life: number; hand_count: number; commanders: { name: string }[] }[]; game: { settings: { allow_test_objects: boolean } } };
  const view = async () => (await (await page.request.get(`/api/games/${gameId}/view?viewer=p1`)).json()) as V;
  const alice = async () => (await view()).players.find((p) => p.id === "p1")!;
  await page.goto(`/#/game/${gameId}`);
  const url = page.url();

  // the importer opens on the table (from the button by my mat), not on another page
  await page.getByTestId("seat-btn-importer").click();
  const panel = page.getByTestId("table-importer");
  await expect(panel).toBeVisible();

  // find a card: into my hand (the host allows it here if the table doesn't yet)
  if (!(await view()).game.settings.allow_test_objects) await panel.getByRole("button", { name: "Allow it" }).click();
  await page.getByTestId("ti-search").fill("sol ring");
  await page.getByTestId("ti-result").first().click();
  await expect.poll(async () => (await alice()).hand_count).toBe(1);

  // place a whole new deck: Alice is now playing Krenko, with seven in hand, at the same table
  await page.getByTestId("ti-tab-deck").click();
  await page.getByTestId("ti-deck-text").fill(KRENKO_LIST);
  await page.getByTestId("ti-place-deck").click();
  await expect.poll(async () => (await alice()).commanders.map((c) => c.name)).toEqual(["Krenko, Mob Boss"]);
  expect((await alice()).hand_count).toBe(7);
  expect(page.url()).toBe(url);

  // restart for everyone from the table: asks twice, then life is back and hands are redrawn
  await page.request.post(`/api/games/${gameId}/actions`, { data: { action: { type: "life", player: "p2", delta: -9 } } });
  await page.getByTestId("ti-restart").click();
  await expect(page.getByTestId("ti-restart")).toContainText("Click again");
  await page.getByTestId("ti-restart").click();
  await expect.poll(async () => (await view()).players.find((p) => p.id === "p2")!.life).toBe(40);
  expect((await alice()).commanders.map((c) => c.name)).toEqual(["Krenko, Mob Boss"]); // the new deck stays
  expect(page.url()).toBe(url);
});
