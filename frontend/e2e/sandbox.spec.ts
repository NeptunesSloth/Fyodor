import { expect, test } from "@playwright/test";
import { ALICE_DECK, bringDeck, serverView } from "./helpers";

/**
 * Sandbox: a place to test a deck on your own (free play with a Commander deck, as in Tabletop Simulator). On the Play page,
 * Sandbox is a one-seat setup: choose the deck, pick the automation level, start, and you're at the table at once (no lobby,
 * no room code, nobody joining). Nothing is checked, and test objects are allowed.
 */
test("test a deck alone: Sandbox goes straight to a one-seat table with the deck, nothing checked", async ({ page }) => {
  // a deck no Commander check would pass (18 cards, four colours under a four-colour commander): Sandbox checks nothing
  const made = await page.request.post("/api/decks", { data: { text: ALICE_DECK, name: "Superfriends" } });
  expect(made.ok()).toBeTruthy();

  await page.goto("/#/play");
  await expect(page.getByRole("heading", { name: "Host a LAN night" })).toBeVisible();
  await page.getByTestId("format-sandbox").check();
  await expect(page.getByRole("heading", { name: "Test a deck" })).toBeVisible();
  // one seat (yours), no lobby, no room code or password, no extra seats
  await expect(page.getByTestId("sandbox-seat")).toBeVisible();
  await expect(page.locator(".pg-chair")).toHaveCount(0);
  await expect(page.getByTestId("decks-own")).toHaveCount(0);
  await expect(page.getByPlaceholder("No password")).toHaveCount(0);
  // the automation level is yours to choose; a deck test starts manual
  await expect(page.getByTestId("automation-level")).toHaveValue("off");
  await expect(page.getByTestId("create-game")).toBeDisabled(); // choose the deck first
  await page.getByTestId("host-name").fill("Alice");
  await page.getByTestId("host-deck").click();
  await page.getByRole("dialog").getByText("Superfriends").first().click();
  await expect(page.getByTestId("create-game")).toHaveText("Start testing");
  await page.getByTestId("create-game").click();

  await expect(page.locator(".game-screen")).toBeVisible();
  await expect(page.getByTestId("lobby")).toHaveCount(0);
  const gameId = page.url().split("/game/")[1]!.split(/[?#]/)[0]!;
  const keep = page.getByTestId("mull-keep");
  if (await keep.isVisible().catch(() => false)) await keep.click();

  await expect(page.getByTestId("table-format")).toHaveText("Sandbox");
  let view = (await serverView(page, gameId)) as Record<string, any>;
  expect(view.game.format).toBe("sandbox");
  expect(view.players).toHaveLength(1);
  expect(view.game.settings.automation).toBe("off");
  expect(view.game.settings.allow_test_objects).toBe(true);
  expect(view.players[0].life).toBe(40);
  expect((view.zones["p1:command"] as string[]).length).toBe(1); // still a Commander deck: the commander waits in the command zone

  // a land from the opening hand (draw until one comes), played by hand: a double-click puts it onto the battlefield
  let island: string | undefined;
  for (let i = 0; i < 10 && !island; i++) {
    view = (await serverView(page, gameId)) as Record<string, any>;
    island = (view.zones["p1:hand"] as string[]).find((id) => view.cards[id]?.name === "Island");
    if (!island) await page.keyboard.press("d");
  }
  expect(island).toBeTruthy();
  await page.locator(`main.table > .hand .hand-card[data-card-id="${island}"]`).dblclick();
  await expect(page.locator(`.table-card[data-card-id="${island}"]`)).toBeVisible();
  view = (await serverView(page, gameId)) as Record<string, any>;
  expect(view.cards[island!].zone).toBe("p1:battlefield");
});

test("a deck test can start with the rules engine on", async ({ page }) => {
  await page.request.post("/api/decks", { data: { text: ALICE_DECK, name: "Superfriends" } });
  await page.goto("/#/play");
  await page.getByTestId("format-sandbox").check();
  await page.getByTestId("automation-level").selectOption("full");
  await page.getByTestId("host-deck").click();
  await page.getByRole("dialog").getByText("Superfriends").first().click();
  await page.getByTestId("create-game").click();
  await expect(page.locator(".game-screen")).toBeVisible();
  const gameId = page.url().split("/game/")[1]!.split(/[?#]/)[0]!;
  await expect.poll(async () => ((await serverView(page, gameId)) as Record<string, any>).game.settings.automation).toBe("full");
});

test("a LAN night's host can still switch the table to Sandbox in Table settings", async ({ page }) => {
  await page.goto("/#/play");
  await page.getByTestId("host-name").fill("Alice");
  await page.getByTestId("create-game").click();
  const lobby = page.getByTestId("lobby");
  await expect(lobby).toBeVisible();
  await expect(page.getByTestId("lobby-format")).toHaveText("Commander LAN night");
  const settings = async () => {
    await page.getByRole("button", { name: "Table settings" }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
  };
  await settings();
  await page.getByTestId("lobby-format-sandbox").check();
  await expect(page.getByTestId("lobby-automation")).toHaveCount(0); // a Sandbox table starts manual, and the hint says why
  await expect(page.getByTestId("lobby-automation-locked")).toHaveText("Off");
  await page.getByRole("dialog").getByRole("button", { name: "Save" }).click();
  await expect(page.getByTestId("lobby-format")).toHaveText("Sandbox: free play");
  await bringDeck(page, ALICE_DECK, "Superfriends");
  await expect(lobby).not.toContainText("deck check");
});
