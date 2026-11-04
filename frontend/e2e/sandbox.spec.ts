import { expect, test } from "@playwright/test";
import { ALICE_DECK, bringDeck, serverView } from "./helpers";

/**
 * Sandbox: free play with Commander decks, as in Tabletop Simulator. A host alone opens a Sandbox LAN night (solo testing),
 * brings a deck no Commander check would pass (no deck checks at this table), starts with rules automation off, and plays a
 * land by hand.
 */
test("a solo Sandbox LAN night: no deck checks, automation off, a land played by hand", async ({ page }) => {
  await page.goto("/#/play");
  await expect(page.getByRole("heading", { name: "Host a LAN night" })).toBeVisible(); // every new game is a LAN night
  await expect(page.getByTestId("automation-level")).toHaveValue("full"); // Commander plays at Full
  await page.getByTestId("format-sandbox").check();
  await expect(page.getByTestId("format-sandbox")).toBeChecked();
  await expect(page.getByTestId("automation-level")).toHaveCount(0); // a Sandbox table starts with automation off
  await expect(page.getByTestId("automation-level-fixed")).toHaveText("Off");
  await page.getByLabel("Table name").fill("Free play");
  await page.getByTestId("host-name").fill("Alice");
  for (let n = 3; n > 0; n--) await page.getByRole("button", { name: "Remove a seat" }).first().click(); // one seat: the host's
  await expect(page.locator(".pg-chair")).toHaveCount(0);
  await page.getByTestId("create-game").click();

  const lobby = page.getByTestId("lobby");
  await expect(lobby).toBeVisible();
  await expect(page.getByTestId("lobby-format")).toHaveText("Sandbox LAN night: free play");
  await expect(page.locator(".house-rules div", { hasText: "Automation" })).toContainText("Off"); // the house rules
  // the host can change the format in Table settings: Commander turns the automation choice back on, Sandbox turns it off
  const settings = async () => {
    await page.getByRole("button", { name: "Table settings" }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
  };
  await settings();
  await expect(page.getByTestId("lobby-format-sandbox")).toBeChecked();
  await expect(page.getByTestId("lobby-automation")).toHaveCount(0); // locked at setup, and the hint says why
  await expect(page.getByTestId("lobby-automation-locked")).toHaveText("Off");
  await page.getByTestId("lobby-format-commander").check();
  await expect(page.getByTestId("lobby-automation")).toHaveValue("full"); // back to Commander: Full, as the pod plays
  await page.getByRole("dialog").getByRole("button", { name: "Save" }).click();
  await expect(page.getByTestId("lobby-format")).toHaveText("Commander LAN night");
  await settings();
  await page.getByTestId("lobby-format-sandbox").check();
  await page.getByRole("dialog").getByRole("button", { name: "Save" }).click();
  await expect(page.getByTestId("lobby-format")).toHaveText("Sandbox LAN night: free play");
  // 18 cards and four colours under a four-colour commander: Commander's checks would flag it; a Sandbox table checks nothing
  await bringDeck(page, ALICE_DECK, "Superfriends");
  await expect(lobby).not.toContainText("deck check");
  await expect(page.locator("[data-testid^='coverage-']")).toHaveCount(0); // a Sandbox table starts manual: no "% automated"
  await expect(page.getByTestId("ready")).toHaveText("Ready");
  await page.getByTestId("ready").click();
  await expect(page.getByTestId("start-game")).toBeEnabled();
  await page.getByTestId("start-game").click();
  await expect(page.locator(".game-screen")).toBeVisible();
  const gameId = page.url().split("/game/")[1]!.split(/[?#]/)[0]!;

  const keep = page.getByTestId("mull-keep");
  await keep.click();
  await expect(page.getByTestId("mulligan")).toHaveCount(0);

  // the top bar says what this table is, where the automation level shows; the rules engine is off
  await expect(page.getByTestId("table-format")).toHaveText("Sandbox");
  await expect(page.getByTestId("auto-level")).toHaveCount(0);
  let view = (await serverView(page, gameId)) as Record<string, any>;
  expect(view.game.format).toBe("sandbox");
  expect(view.game.settings.automation).toBe("off");
  expect(view.game.settings.allow_test_objects).toBe(true);
  expect(view.rules ?? null).toBeNull();
  expect(view.players[0].life).toBe(40);

  // a land from the opening hand (draw until one comes), played by hand: a double-click puts it onto the battlefield
  let island: string | undefined;
  for (let i = 0; i < 10 && !island; i++) {
    view = (await serverView(page, gameId)) as Record<string, any>;
    island = (view.zones["p1:hand"] as string[]).find((id) => view.cards[id]?.name === "Island");
    if (!island) await page.keyboard.press("d");
  }
  expect(island).toBeTruthy();
  const card = page.locator(`main.table > .hand .hand-card[data-card-id="${island}"]`);
  await card.dblclick();
  await expect(page.locator(`.table-card[data-card-id="${island}"]`)).toBeVisible();
  view = (await serverView(page, gameId)) as Record<string, any>;
  expect(view.cards[island!].zone).toBe("p1:battlefield");
  expect(view.zones["p1:battlefield"]).toContain(island);

  // the format pill opens the automation settings: the host can turn the rules on from the top bar
  await page.getByTestId("table-format").click();
  await expect(page.locator(".auto-settings")).toContainText("Sandbox table");
});
