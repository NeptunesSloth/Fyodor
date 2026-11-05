import { expect, test, type Page } from "@playwright/test";
import { saveDecks } from "./helpers";

/**
 * Token math (game/TokenMathDialog.tsx, Shift+T): it reads the Scute Swarms on your board and works out the land drops; and a creation
 * past the separate-object limit, made by hand, is one card ×N (backend tests/test_big_token_counts.py).
 */
const SCUTE = "Landfall — Whenever a land you control enters, create a 1/1 green Insect creature token. If you control six or more lands, create a token that's a copy of this creature instead.";

async function newGame(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem("fyodor.coach3d", "done");
    localStorage.setItem("fyodor.tips.seen", JSON.stringify(["off"]));
  });
  const decks = await saveDecks(page);
  const res = await page.request.post("/api/games", {
    data: {
      name: "Token math", mode: "local", shuffle: false, first_player: 0, mulligan_rule: "none",
      players: [{ name: "Alice", deck_id: decks[0]!.id }, { name: "Bob", deck_id: decks[1]!.id }],
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
