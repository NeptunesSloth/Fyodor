import { expect, test, type Page } from "@playwright/test";
import { saveDecks } from "./helpers";

/**
 * Token math (game/TokenMathDialog.tsx, Shift+T): it reads the Scute Swarms on your board and works out the land drops; and a creation
 * past the separate-object limit, made by hand, is one card ×N (backend tests/test_big_token_counts.py).
 */
const SCUTE = "Landfall — Whenever a land you control enters, create a 1/1 green Insect creature token. If you control six or more lands, create a token that's a copy of this creature instead.";

async function newGame(page: Page, extra: Record<string, unknown> = {}) {
  await page.addInitScript(() => {
    localStorage.setItem("fyodor.coach3d", "done");
    localStorage.setItem("fyodor.tips.seen", JSON.stringify(["off"]));
  });
  const decks = await saveDecks(page);
  const res = await page.request.post("/api/games", {
    data: {
      name: "Token math", mode: "local", shuffle: false, first_player: 0, mulligan_rule: "none",
      players: [{ name: "Alice", deck_id: decks[0]!.id }, { name: "Bob", deck_id: decks[1]!.id }],
      ...extra,
    },
  });
  const gameId = ((await res.json()) as { game: { id: string } }).game.id;
  await page.goto(`/#/game/${gameId}`);
  return async (action: Record<string, unknown>) => {
    const r = await page.request.post(`/api/games/${gameId}/actions`, { data: { action } });
    expect(r.ok(), await r.text()).toBeTruthy();
  };
}

test("Shift+T works out Scute Swarm land drops from the board; a big creation by hand is one card ×N", async ({ page }) => {
  const act = await newGame(page);
  await expect(page.getByTestId("seat-p2")).toBeVisible();
  await act({ type: "create_token", player: "p1", token: { name: "Scute Swarm", type_line: "Creature — Insect", power: "1", toughness: "1", colors: ["G"], text: SCUTE }, count: 2, stacked: false });
  await act({ type: "create_token", player: "p1", token: { name: "Insect", type_line: "Token Creature — Insect", power: "1", toughness: "1", colors: ["G"] }, count: 5000 });

  await page.keyboard.press("Shift+T");
  await expect(page.getByTestId("tm-swarms")).toHaveValue("2");
  await page.getByTestId("tm-lands").fill("6");
  await page.getByTestId("tm-enter").fill("3");
  await expect(page.getByTestId("tm-total")).toContainText("16 Scute Swarms (+14)"); // 2 → 4 → 8 → 16
  await page.getByTestId("tm-all-at-once").click();
  await expect(page.getByTestId("tm-total")).toContainText("8 Scute Swarms (+6)"); // each swarm triggers 3 times; the copies don't
  if (process.env.SHOT_DIR) await page.getByRole("dialog").screenshot({ path: `${process.env.SHOT_DIR}/token-math-landfall.png` });

  await page.getByTestId("tm-tab-board").click();
  await expect(page.getByTestId("tm-census")).toContainText("5,000"); // the ×5,000 card counts as 5,000 Insects
  if (process.env.SHOT_DIR) await page.getByRole("dialog").screenshot({ path: `${process.env.SHOT_DIR}/token-math-board.png` });
  await page.keyboard.press("Shift+T");
  await expect(page.getByTestId("tm-total")).toHaveCount(0);
});

test("automation off: Token math puts the Scute Swarm turn on the table as one card ×N; the board pressure badge opens it", async ({ page }) => {
  const act = await newGame(page);
  await expect(page.getByTestId("seat-p2")).toBeVisible();
  await expect(page.getByTestId("board-pressure")).toHaveCount(0); // a small board: no badge
  await act({ type: "create_token", player: "p1", token: { name: "Scute Swarm", type_line: "Creature — Insect", power: "1", toughness: "1", colors: ["G"], text: SCUTE }, count: 2, stacked: false });
  await act({ type: "create_token", player: "p1", token: { name: "Forest", type_line: "Token Land — Forest" }, count: 6, stacked: false });
  await act({ type: "create_token", player: "p1", token: { name: "Wastes", type_line: "Basic Land — Wastes" }, count: 1, stacked: false });

  await page.keyboard.press("Shift+T");
  await expect(page.getByTestId("tm-lands")).toHaveValue("7");
  await expect(page.getByTestId("tm-load")).toContainText("9 objects");
  // Scapeshift for 5: 2 lands left, 5 enter at once → 7 lands as the triggers resolve: each swarm triggers 5 times, 10 copies
  await page.getByTestId("tm-scapeshift-n").fill("5");
  await page.getByTestId("tm-scapeshift").click();
  await expect(page.getByTestId("tm-sacrificed")).toHaveValue("5");
  await expect(page.getByTestId("tm-total")).toContainText("12 Scute Swarms (+10)");
  // one at a time instead: 2 → 4 → 8 (+6)
  await page.getByTestId("tm-one-at-a-time").click();
  await page.getByTestId("tm-enter").fill("2");
  await expect(page.getByTestId("tm-total")).toContainText("8 Scute Swarms (+6)");
  if (process.env.SHOT_DIR) await page.getByRole("dialog").screenshot({ path: `${process.env.SHOT_DIR}/token-math-apply.png` });

  let asked = "";
  page.once("dialog", (d) => { asked = d.message(); void d.accept(); });
  await page.getByTestId("tm-apply").click();
  await expect(page.getByTestId("tm-swarms")).toHaveValue("8"); // the board re-read: 2 + one card ×6
  expect(asked).toContain("6 Scute Swarm copies (one card ×6)");

  // other players' boards: no button
  await page.getByRole("dialog").getByRole("combobox").selectOption("p2");
  await expect(page.getByTestId("tm-apply")).toHaveCount(0);
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("tm-load")).toHaveCount(0);

  // a big board shows the badge; it opens Token math with the object count
  await act({ type: "create_token", player: "p2", token: { name: "Insect", type_line: "Token Creature — Insect", power: "1", toughness: "1", colors: ["G"] }, count: 5000, stacked: true });
  const badge = page.getByTestId("board-pressure");
  await expect(badge).toBeVisible();
  await expect(badge).toContainText("×5,000");
  await expect(badge).toHaveAttribute("title", /each token copy .* is its own object for the rules engine/);
  if (process.env.SHOT_DIR) await page.locator("header.game-top").screenshot({ path: `${process.env.SHOT_DIR}/board-pressure.png` });
  await badge.click();
  await expect(page.getByTestId("tm-load")).toContainText("standing for 5,015 permanents");
});

test("automation on: Token math says the rules engine makes the tokens", async ({ page }) => {
  const act = await newGame(page, { automation: "full" });
  await expect(page.getByTestId("seat-p2")).toBeVisible();
  await act({ type: "create_token", player: "p1", token: { name: "Scute Swarm", type_line: "Creature — Insect", power: "1", toughness: "1", colors: ["G"], text: SCUTE }, count: 1, stacked: false });
  await page.keyboard.press("Shift+T");
  await expect(page.getByTestId("tm-apply-hint")).toContainText("The rules engine makes these when the triggers resolve");
  await expect(page.getByTestId("tm-apply")).toHaveCount(0);
  await page.getByTestId("tm-tab-copies").click();
  await page.getByTestId("tm-dop").fill("4");
  await expect(page.getByTestId("tm-dop-out")).toContainText("= 16 tokens");
  await page.getByTestId("tm-rite").click();
  await expect(page.getByTestId("tm-made")).toContainText("→ 5");
  if (process.env.SHOT_DIR) await page.getByRole("dialog").screenshot({ path: `${process.env.SHOT_DIR}/token-math-copies.png` });
});
