import { expect, test, type Page } from "@playwright/test";
import { ALICE_DECK, BOB_DECK } from "./helpers";

/**
 * Review frames for the Bag of Extras (game/ExtrasBag.tsx), opened from its seat chit on the 3D table and its button on
 * the 2D table. Skipped unless SHOT_DIR is set; SHOT_PREFIX names the set.
 */
const OUT = process.env.SHOT_DIR ?? "";
const PREFIX = process.env.SHOT_PREFIX ?? "extras";
test.skip(!OUT, "set SHOT_DIR to capture screenshots");

/** A deck that makes tokens: Krenko's Goblins, and a Tokens section (with a real card database, each a printed token). */
const TOKEN_DECK = `Commander
1x Krenko, Mob Boss (ddn) 13
Deck
1x Lightning Bolt (clb) 187
14x Mountain (cmm) 1003
Tokens
1x Treasure
1x Clue
1x Food
1x Blood
1x Soldier
1x Spirit
1x Thopter
`;

/**
 * SHOT_REAL=1: a real deck against a real card database (Scryfall's, with art cached): goblins and the cards that make
 * Treasure, Clue, Food, Thopters, Faeries and Elementals, so the bag shows the deck's real printed tokens.
 */
const REAL = !!process.env.SHOT_REAL;
const REAL_DECK = `Commander
1x Krenko, Mob Boss (ddn) 15
Deck
1x Siege-Gang Commander (tdc) 232
1x Beetleback Chief (tdc) 205
1x Legion Warboss (tdc) 220
1x Goblin Rabblemaster (j25) 558
1x Dockside Extortionist
1x Smothering Tithe
1x Tireless Tracker
1x Gilded Goose
1x Pia Nalaar
1x Bitterblossom
1x Young Pyromancer
1x Sol Ring (cmm) 410
14x Mountain (fra) 287
`;

async function game(page: Page, renderer: "3d" | "2d", decks = [REAL ? REAL_DECK : TOKEN_DECK, ALICE_DECK]): Promise<string> {
  await page.addInitScript((r) => {
    localStorage.setItem("fyodor.renderer", r);
    localStorage.setItem("fyodor.welcomeDone", "1");
    localStorage.setItem("fyodor.coach3d", "done");
    localStorage.setItem("fyodor.tips.seen", JSON.stringify(["off"]));
    localStorage.setItem("fyodor.profiles", JSON.stringify({ version: 2, active: "t", profiles: [{ id: "t", name: "Alice", avatar: "A", prefs: { ambience: false } }] }));
  }, renderer);
  const ids: string[] = [];
  for (const text of decks) {
    const r = await page.request.post("/api/decks", { data: { text, name: text.split("\n")[1]!.replace(/^1x /, "").replace(/ \(.*/, "") } });
    expect(r.ok()).toBeTruthy();
    ids.push(((await r.json()) as { id: string }).id);
  }
  const res = await page.request.post("/api/games", {
    data: { name: "Extras", format: "commander", mode: "local", shuffle: false, first_player: 0, mulligan_rule: "none", automation: "off",
      players: [{ name: "Alice", deck_id: ids[0] }, { name: "Bob", deck_id: ids[1] }] },
  });
  expect(res.ok()).toBeTruthy();
  return ((await res.json()) as { game: { id: string } }).game.id;
}

test("the Bag of Extras, 3D table, 1920x1080", async ({ page }) => {
  test.setTimeout(240_000);
  await page.setViewportSize({ width: 1920, height: 1080 });
  const id = await game(page, "3d");
  await page.goto(`/#/game/${id}`);
  await expect(page.getByTestId("table-3d")).toBeVisible({ timeout: 90_000 });
  const intro = page.getByTestId("game-intro");
  if (await intro.isVisible().catch(() => false)) await page.keyboard.press("Escape");
  await page.waitForTimeout(3500);
  const at = await page.evaluate(() => window.__fyodor3d!.buttonAt("extras"));
  expect(at).not.toBeNull();
  await page.mouse.click(at!.x, at!.y);
  await expect(page.getByTestId("extras-panel")).toBeVisible();
  await page.mouse.move(2, 400);
  await page.waitForFunction(() => [...document.querySelectorAll<HTMLImageElement>(".bag-art")].every((i) => i.complete), null, { timeout: 30_000 });
  await page.waitForTimeout(1500); // token art and the panel's entrance settle
  await page.screenshot({ path: `${OUT}/${PREFIX}-3d-1920x1080.png`, animations: "disabled" }); // (a slow software-WebGL frame can hold the entrance mid-fade)
  await page.getByTestId("extras-panel").screenshot({ path: `${OUT}/${PREFIX}-3d-panel.png` });
});

test("the Bag of Extras, 2D table, 1440x900", async ({ page }) => {
  test.setTimeout(180_000);
  const id = await game(page, "2d");
  await page.goto(`/#/game/${id}`);
  const intro = page.getByTestId("game-intro");
  await page.waitForTimeout(1500);
  if (await intro.isVisible().catch(() => false)) await page.keyboard.press("Escape");
  await page.getByRole("button", { name: /Bag of Extras/ }).first().click();
  await expect(page.getByTestId("extras-panel")).toBeVisible();
  await page.waitForFunction(() => [...document.querySelectorAll<HTMLImageElement>(".bag-art")].every((i) => i.complete), null, { timeout: 30_000 });
  await page.waitForTimeout(1200);
  await page.screenshot({ path: `${OUT}/${PREFIX}-2d-1440x900.png` });
  // reaching in: ×3 chosen, a token under the pointer
  const panel = page.getByTestId("extras-panel");
  await panel.getByRole("button", { name: "×3" }).click();
  await panel.getByTestId("extras-treasure").hover();
  await page.waitForTimeout(400);
  await panel.screenshot({ path: `${OUT}/${PREFIX}-2d-panel-hover.png`, animations: "disabled" });
});

test("the Bag of Extras of a deck that makes no tokens", async ({ page }) => {
  test.setTimeout(120_000);
  const id = await game(page, "2d", [ALICE_DECK, BOB_DECK]);
  await page.goto(`/#/game/${id}`);
  await page.waitForTimeout(1500);
  const intro = page.getByTestId("game-intro");
  if (await intro.isVisible().catch(() => false)) await page.keyboard.press("Escape");
  await page.getByRole("button", { name: /Bag of Extras/ }).first().click();
  const panel = page.getByTestId("extras-panel");
  await expect(panel.getByTestId("extras-no-tokens")).toHaveText("Your deck makes no tokens.");
  await expect(panel.getByTestId("extras-find-token")).toBeVisible();
  await panel.screenshot({ path: `${OUT}/${PREFIX}-2d-panel-empty.png`, animations: "disabled" });
});
