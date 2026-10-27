import { expect, test } from "@playwright/test";
import { ALICE_DECK, BOB_DECK } from "./helpers";

/** Combat lane view: attackers over their blockers, grouped by defender; the table itself never moves. */
test("combat lanes show each attacker over its blockers without moving cards", async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 900 });
  await page.addInitScript(() => localStorage.setItem("fyodor.welcomeDone", "1"));
  for (const text of [ALICE_DECK, BOB_DECK]) await page.request.post("/api/decks", { data: { text } });
  const decks = (await (await page.request.get("/api/decks")).json()) as { id: string }[];
  const res = await page.request.post("/api/games", { data: { name: "Fight", mode: "local", shuffle: false,
    players: ["Alice", "Bob"].map((name, i) => ({ name, deck_id: decks[i]!.id })) } });
  const gameId = ((await res.json()) as { game: { id: string } }).game.id;
  const act = async (action: Record<string, unknown>) => {
    const r = await page.request.post(`/api/games/${gameId}/actions`, { data: { action } });
    expect(r.ok(), await r.text()).toBeTruthy();
  };
  const token = (player: string, name: string, x: number) => act({ type: "create_token", player, token: { name, power: "2", toughness: "2", type_line: "Token Creature — Soldier" }, count: 1, x, y: 40 });
  await token("p1", "Raider", 20);
  await token("p1", "Scout", 120);
  await token("p2", "Wall", 20);
  type V = { zones: Record<string, string[]>; cards: Record<string, { x?: number; y?: number }> };
  const view = async () => (await (await page.request.get(`/api/games/${gameId}/view?viewer=all`)).json()) as V;
  const before = await view();
  const [raider, scout] = before.zones["p1:battlefield"]!;
  const [wall] = before.zones["p2:battlefield"]!;
  await act({ type: "attack", card_ids: [raider, scout], target: { kind: "player", id: "p2" } });
  await act({ type: "block", card_id: wall, attacker_id: raider });

  await page.goto(`/#/game/${gameId}`);
  await expect(page.getByTestId("combat-view-toggle")).toContainText("2 attacking · 1 blocked");
  await page.getByTestId("combat-view-toggle").click();
  const lanes = page.getByTestId("combat-lanes");
  await expect(lanes).toContainText("Attacking Bob");
  await expect(lanes.locator(".combat-lane")).toHaveCount(2);
  await expect(lanes.locator(".combat-vs.open")).toHaveText("Unblocked");
  await page.waitForTimeout(400);
  if (process.env.SHOT_DIR) await page.screenshot({ path: `${process.env.SHOT_DIR}/combat-lanes.png` });
  // presentation only: every card is exactly where it was
  const after = await view();
  for (const id of [raider, scout, wall]) expect([after.cards[id!]!.x, after.cards[id!]!.y]).toEqual([before.cards[id!]!.x, before.cards[id!]!.y]);
  // combat ends: the view goes away
  await act({ type: "clear_combat" });
  await expect(page.getByTestId("combat-view-toggle")).toHaveCount(0);
});
