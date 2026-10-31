import { expect, test } from "@playwright/test";
import { ALICE_DECK, BOB_DECK } from "./helpers";

test("ping a card with G (never a hand card); sort the hand by mana value", async ({ page }) => {
  for (const text of [ALICE_DECK, BOB_DECK]) expect((await page.request.post("/api/decks", { data: { text } })).ok()).toBeTruthy();
  const decks = (await (await page.request.get("/api/decks")).json()) as { id: string; name: string }[];
  const res = await page.request.post("/api/games", {
    data: {
      name: "Pings", mode: "local", shuffle: false, first_player: 0, mulligan_rule: "none",
      players: [{ name: "Alice", deck_id: decks[0]!.id }, { name: "Bob", deck_id: decks[1]!.id }],
    },
  });
  const gameId = ((await res.json()) as { game: { id: string } }).game.id;
  const act = (action: Record<string, unknown>) => page.request.post(`/api/games/${gameId}/actions`, { data: { action } });
  await act({ type: "draw", player: "p1", count: 8 });
  await page.goto(`/#/game/${gameId}`);
  const hand = page.locator("main.table > .hand .hand-card");
  await expect(hand).toHaveCount(8);

  // a card in my hand is private: pinging it does nothing but explain
  await hand.first().hover();
  await page.keyboard.press("g");
  await expect(page.getByText("Point at a card everyone can see")).toBeVisible();
  await expect(page.getByTestId("ping")).toHaveCount(0);

  // play one, point at it: the ring and my name appear on it
  const id = await hand.first().getAttribute("data-card-id");
  await hand.first().dblclick();
  const permanent = page.locator(`.table-card[data-card-id="${id}"]`);
  await expect(permanent).toBeVisible();
  await permanent.hover();
  await page.keyboard.press("g");
  const ping = page.getByTestId("ping");
  await expect(ping.locator(".ping-name")).toBeVisible(); // the anchor itself is a zero-size point
  await expect(ping).toContainText("You");
  const box = (await permanent.boundingBox())!;
  const dot = (await ping.locator(".ping-dot").boundingBox())!;
  expect(Math.abs(dot.x + dot.width / 2 - (box.x + box.width / 2))).toBeLessThan(4);
  expect(Math.abs(dot.y + dot.height / 2 - (box.y + box.height / 2))).toBeLessThan(4);
  await expect(ping).toHaveCount(0, { timeout: 5000 }); // it fades by itself

  // Arena-style hand sorting: lands first, then by mana value, ties by name (display only)
  const names = async () => hand.evaluateAll((els) => els.map((e) => e.getAttribute("aria-label")));
  const drawn = await names();
  await page.getByTestId("hand-sort").click();
  await page.getByRole("button", { name: "By mana value" }).click();
  await expect(page.getByTestId("hand-sort")).toHaveText("Hand: mana value");
  const sorted = await names();
  expect([...sorted].sort()).toEqual([...drawn].sort());
  const lands = sorted.filter((n) => n === "Island" || n === "Command Tower").length;
  expect(sorted.slice(0, lands).every((n) => n === "Island" || n === "Command Tower")).toBeTruthy();
  expect(sorted.indexOf("Arcane Signet")).toBeGreaterThan(Math.max(sorted.indexOf("Swords to Plowshares"), sorted.indexOf("Opt"), sorted.indexOf("Sol Ring")));
  // S cycles on to colour; the server's hand order never changed
  await page.keyboard.press("s");
  await expect(page.getByTestId("hand-sort")).toHaveText("Hand: colour");
  const server = (await (await page.request.get(`/api/games/${gameId}/view?viewer=p1`)).json()) as { zones: Record<string, string[]>; cards: Record<string, { name: string }> };
  expect(server.zones["p1:hand"]!.map((cid) => server.cards[cid]!.name)).toEqual(drawn);
});
