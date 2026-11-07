import { expect, test } from "@playwright/test";
import { saveDecks } from "./helpers";

/** The card menu's activated abilities: cost in symbols, the whole effect, a reason when greyed out, keys 1–9. */
const OUT = process.env.SHOT_DIR ?? "";

test("card menu shows activated abilities as cost + whole effect, and key 1 activates the first", async ({ page }) => {
  test.setTimeout(120_000);
  await page.setViewportSize({ width: 1600, height: 900 });
  await page.addInitScript(() => localStorage.setItem("fyodor.welcomeDone", "1"));
  const decks = await saveDecks(page);
  const res = await page.request.post("/api/games", { data: { name: "Menu", mode: "local", automation: "full", shuffle: false, first_player: 0,
    mulligan_rule: "none", players: [{ name: "Alice", deck_id: decks[0]!.id }, { name: "Bob", deck_id: decks[1]!.id }] } });
  const gameId = ((await res.json()) as { game: { id: string } }).game.id;
  type V = { turn: { phase: string }; cards: Record<string, { name: string }> };
  const view = async () => (await (await page.request.get(`/api/games/${gameId}/view?viewer=p1`)).json()) as V;
  const act = async (action: Record<string, unknown>) => {
    const r = await page.request.post(`/api/games/${gameId}/actions`, { data: { action, as: "p1" } });
    expect(r.ok(), await r.text()).toBeTruthy();
  };
  for (let i = 0; i < 6 && (await view()).turn.phase !== "main1"; i++) await act({ type: "pass_priority" });
  // Krenko, Mob Boss (Alice's commander): "{T}: Create X 1/1 red Goblin creature tokens, where X is the number of Goblins you control."
  const id = Object.entries((await view()).cards).find(([, c]) => c.name === "Krenko, Mob Boss")![0];
  await act({ type: "move", card_ids: [id], to: { zone: "battlefield", player: "p1" }, x: 200, y: 60 });
  await act({ type: "tap", card_ids: [id], tapped: true });

  await page.goto(`/#/game/${gameId}`);
  const card = page.locator(`[data-card-id="${id}"]`).first();
  await card.click({ button: "right" });
  const rows = page.locator(".ctx-ability");
  await expect(rows).toHaveCount(1);
  await expect(rows.first()).toContainText("Create X 1/1 red Goblin creature tokens, where X is the number of Goblins you control.");
  await expect(rows.first()).toContainText("Already tapped");
  await expect(page.locator(".ctx-section").first()).toHaveText("Abilities");
  if (OUT) await page.locator(".ctx-menu").screenshot({ path: `${OUT}/ability-menu.png` });
  await page.keyboard.press("Escape");
  await act({ type: "tap", card_ids: [id], tapped: false });
  await card.click({ button: "right" });
  await expect(rows.first()).toContainText("Summoning sick"); // 302.6: it came under Alice's control this turn
  await page.keyboard.press("Escape");
  // Alice's next turn: Krenko can tap now
  for (let i = 0; i < 2; i++) await act({ type: "next_turn" });
  for (let i = 0; i < 6 && (await view()).turn.phase !== "main1"; i++) await act({ type: "pass_priority" });
  await card.click({ button: "right" });
  await expect(page.locator(".ctx-key")).toHaveText("1");
  if (OUT) await page.locator(".ctx-menu").screenshot({ path: `${OUT}/ability-menu-ready.png` });
  await page.keyboard.press("1"); // activates it: Krenko taps
  await expect(page.locator(".ctx-menu")).toHaveCount(0);
  await expect.poll(async () => ((await view()).cards[id] as unknown as { tapped?: boolean }).tapped).toBe(true);
});
