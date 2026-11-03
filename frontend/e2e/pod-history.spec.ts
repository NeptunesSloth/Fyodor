import { expect, test, type Page } from "@playwright/test";
import { ALICE_DECK, BOB_DECK, bringDeck, hostLobby, saveDecks, seatToken } from "./helpers";

/**
 * -- pod history -- each game of the night keeps who went out, in order, and a public final board (docs/GAME_NIGHT_FLOW.md):
 * the lobby's session recap and Pod stats show both. The eliminated player's hub opens the table's game log.
 * SHOT_DIR, when set, keeps screenshots.
 */
const OUT = process.env.SHOT_DIR ?? "";
const shot = async (page: Page, name: string) => {
  if (OUT) await page.screenshot({ path: `${OUT}/history-${name}.png` });
};

async function post(page: Page, url: string, data: Record<string, unknown>, token: string | null) {
  const res = await page.request.post(url, { data, headers: token ? { "X-Seat-Token": token } : {} });
  expect(res.ok(), await res.text()).toBeTruthy();
  return (await res.json()) as Record<string, unknown>;
}

test("a conceded game: the session recap and Pod stats show who went out and the final board", async ({ page }) => {
  test.setTimeout(120_000);
  await page.setViewportSize({ width: 1600, height: 900 });
  const { gameId, code } = await hostLobby(page, { name: "Alice" });
  const host = await seatToken(page, gameId);
  await post(page, `/api/games/${gameId}/lobby/settings`, { automation: "full", mulligan_rule: "none" }, host);
  // Bob joins from "another computer" (the same API his browser would use)
  const bob = (await post(page, "/api/join", { code, name: "Bob" }, null)).token as string;
  await post(page, `/api/games/${gameId}/lobby/deck`, { text: BOB_DECK, name: "Goblins" }, bob);
  await post(page, `/api/games/${gameId}/lobby/ready`, { ready: true }, bob);
  await bringDeck(page, ALICE_DECK, "Superfriends");
  await page.getByTestId("ready").click();
  await expect(page.getByTestId("start-game")).toBeEnabled();
  await page.getByTestId("start-game").click();
  await expect(page.locator(".game-screen")).toBeVisible();

  // Alice puts a few cards onto the battlefield, then Bob concedes: the rules end the game and Alice confirms the result
  const act = (action: Record<string, unknown>, token: string | null) => post(page, `/api/games/${gameId}/actions`, { action }, token);
  type View = { viewer: string; zones: Record<string, string[]> };
  await act({ type: "draw", count: 3 }, host);
  const view = (await (await page.request.get(`/api/games/${gameId}/view`, { headers: { "X-Seat-Token": host! } })).json()) as View;
  await act({ type: "move", card_ids: view.zones[`${view.viewer}:hand`]!.slice(0, 2), to: { zone: "battlefield" } }, host);
  await act({ type: "concede" }, bob);
  await post(page, `/api/games/${gameId}/night/answer`, { agree: true }, host);
  await post(page, `/api/games/${gameId}/night/vote`, { choice: "lobby" }, host);

  // the lobby's session recap: the order, and the final board on request
  const recap = page.getByTestId("session-recap");
  await expect(recap).toBeVisible({ timeout: 15_000 });
  await expect(recap.getByTestId("elim-order")).toHaveText("1st out: Bob (turn 1, conceded)");
  const board = recap.getByTestId("final-board");
  await board.locator("summary").click();
  await expect(board).toContainText("Alice");
  await expect(board).toContainText("Atraxa, Praetors' Voice");
  await expect(board).toContainText("40 life · out 1st"); // Bob's line
  await expect(board).toContainText("Graveyard 0 · Exile 0");
  await recap.evaluate((el) => el.scrollIntoView({ block: "end" }));
  await page.waitForTimeout(300);
  await shot(page, "recap");

  // Pod stats: the same game, its order and its final board
  await page.goto("/#/stats");
  const game = page.getByTestId("pod-game").filter({ hasText: "1st out: Bob (turn 1, conceded)" }).first();
  await expect(game).toBeVisible();
  await game.getByTestId("final-board").locator("summary").click();
  await expect(game.getByTestId("final-board")).toContainText("Krenko, Mob Boss");
  await game.scrollIntoViewIfNeeded();
  await shot(page, "pod-stats");
});

test("the eliminated hub's Game log link opens the table's log", async ({ page }) => {
  test.setTimeout(90_000);
  await page.setViewportSize({ width: 1600, height: 900 });
  await page.addInitScript(() => localStorage.setItem("fyodor.welcomeDone", "1"));
  const decks = await saveDecks(page);
  const res = await page.request.post("/api/games", { data: { name: "Log", mode: "local", automation: "full", mulligan_rule: "none",
    players: ["Alice", "Bob", "Cara"].map((name, i) => ({ name, deck_id: decks[i % 2]!.id })) } });
  const gameId = ((await res.json()) as { game: { id: string } }).game.id;
  await page.goto(`/#/game/${gameId}`);
  await expect(page.locator(".game-screen")).toBeVisible();
  const intro = page.getByTestId("game-intro");
  if (await intro.isVisible()) await page.keyboard.press("Escape");
  await expect(intro).toHaveCount(0);
  const conceded = await page.request.post(`/api/games/${gameId}/actions`, { data: { action: { type: "concede" }, as: "p1" } });
  expect(conceded.ok(), await conceded.text()).toBeTruthy();
  const hub = page.getByTestId("eliminated-hub");
  await expect(hub).toBeVisible({ timeout: 10_000 });
  await hub.getByTestId("open-game-log").click();
  await expect(hub).toHaveCount(0);
  await expect(page.getByTestId("log-drawer")).toHaveClass(/open/);
  await expect(page.getByTestId("log-drawer")).toContainText("Alice conceded");
  await expect(page.getByTestId("eliminated-pill")).toBeVisible();
  await shot(page, "hub-log");
});
