import { expect, test } from "@playwright/test";
import { saveDecks } from "./helpers";

/** Commander tax kept by hand on the table, and a slot of its own for a partner (as on the Oops mat). */
test("commander tax buttons, and a partner gets its own slot and counter", async ({ page }) => {
  const decks = await saveDecks(page);
  const res = await page.request.post("/api/games", {
    data: {
      name: "Tax", mode: "local", shuffle: false, first_player: 0, mulligan_rule: "none",
      players: [{ name: "Alice", deck_id: decks[0]!.id }, { name: "Bob", deck_id: decks[1]!.id }],
    },
  });
  const gameId = ((await res.json()) as { game: { id: string } }).game.id;
  type V = { players: { id: string; commanders: { key: string; name: string; tax: number }[] }[]; zones: Record<string, string[]> };
  const view = async () => (await (await page.request.get(`/api/games/${gameId}/view?viewer=p1`)).json()) as V;
  const alice = async () => (await view()).players.find((p) => p.id === "p1")!;
  await page.goto(`/#/game/${gameId}`);

  // Alice's commander has a tax medallion under it: click +2, right-click −2 (the number is drawn on it, and named)
  const key = (await alice()).commanders[0]!.key;
  const tax = page.locator(".player-area.mine").getByTestId(`tax-${key}`);
  await expect(tax).toHaveAccessibleName(/: 0\. Click to add 2/);
  await tax.click();
  await tax.click();
  await expect.poll(async () => (await alice()).commanders[0]!.tax).toBe(4);
  await tax.click({ button: "right" });
  await expect.poll(async () => (await alice()).commanders[0]!.tax).toBe(2);
  await expect(tax).toHaveAccessibleName(/: 2\. Click to add 2/);

  // a partner: a second commander gets its own slot and its own counter
  await page.request.post(`/api/games/${gameId}/actions`, { data: { action: { type: "draw", player: "p1", count: 1 } } });
  const drawn = (await view()).zones["p1:hand"]![0]!;
  await page.request.post(`/api/games/${gameId}/actions`, { data: { action: { type: "move", card_ids: [drawn], to: { zone: "command", player: "p1" } } } });
  await page.request.post(`/api/games/${gameId}/actions`, { data: { action: { type: "set_commander", card_id: drawn, value: true } } });
  const zone = page.locator(".player-area.mine .command-zone");
  await expect(zone).toHaveClass(/partners/);
  await expect(zone.locator(".command-slot")).toHaveCount(2);
  const partner = (await alice()).commanders[1]!.key;
  await zone.getByTestId(`tax-${partner}`).click();
  await expect.poll(async () => (await alice()).commanders.map((c) => c.tax)).toEqual([2, 2]);

  // the zone's name opens the Command zone browser, as Library / Graveyard / Exile do (clicking the commander previews it)
  await page.getByTestId("command-browse-p1").click();
  const browser = page.locator(".zone-browser");
  await expect(browser.locator(".zb-head b")).toHaveText("Command");
  await expect(browser.locator(".zb-head .hint")).toHaveText("2 cards");
  await browser.getByRole("button", { name: "Close" }).click();
  await expect(browser).toHaveCount(0);
});
