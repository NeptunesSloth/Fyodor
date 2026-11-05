import { expect, test, type Page } from "@playwright/test";
import { menuPath, saveDecks } from "./helpers";

/**
 * Token stacks, part of a pile (docs/TOKEN_STACKS.md): attack with some of a "Goblin ×40", tap some, sacrifice some (the sandbox), the
 * combat strip's damage total, and a batch of 400 identical triggers shown as one stack row.
 */
type V = { zones: Record<string, string[]>; stack: string[]; cards: Record<string, { name?: string; quantity?: number; tapped?: boolean; attacking?: { id: string } | null; zone: string }> };

async function setup(page: Page) {
  await page.setViewportSize({ width: 1600, height: 900 });
  await page.addInitScript(() => localStorage.setItem("fyodor.welcomeDone", "1"));
  const decks = await saveDecks(page);
  const res = await page.request.post("/api/games", { data: { name: "Piles", mode: "local", shuffle: false,
    players: ["Alice", "Bob"].map((name, i) => ({ name, deck_id: decks[i]!.id })) } });
  const gameId = ((await res.json()) as { game: { id: string } }).game.id;
  const act = async (action: Record<string, unknown>) => {
    const r = await page.request.post(`/api/games/${gameId}/actions`, { data: { action } });
    expect(r.ok(), await r.text()).toBeTruthy();
  };
  const view = async () => (await (await page.request.get(`/api/games/${gameId}/view?viewer=all`)).json()) as V;
  return { gameId, act, view };
}

const goblins = (v: V) => (v.zones["p1:battlefield"] ?? []).map((id) => ({ id, ...v.cards[id]! })).filter((c) => c.name === "Goblin");

async function answer(page: Page, n: number) {
  const input = page.locator(".modal input[type=number]");
  await expect(input).toBeVisible();
  await input.fill(String(n));
  await page.getByRole("button", { name: "OK", exact: true }).click();
}

test("attack, tap and sacrifice part of a token stack; the combat strip sums an attacking stack's damage", async ({ page }) => {
  const { gameId, act, view } = await setup(page);
  await act({ type: "create_token", player: "p1", token: { name: "Goblin", power: "2", toughness: "1", type_line: "Token Creature — Goblin", colors: ["R"] },
    count: 40, stacked: true, x: 60, y: 60 });
  const [pile] = goblins(await view());
  expect(pile!.quantity).toBe(40);
  await page.goto(`/#/game/${gameId}`);
  const card = page.locator(`.table-card[data-card-id="${pile!.id}"]`);
  await expect(card).toBeVisible();

  // Attack with 25 of the 40: the card itself keeps 25 and attacks; 15 are split off beside it
  await card.click({ button: "right" });
  await menuPath(page, "Attack", "Attack with some of the ×40", "Bob…");
  await answer(page, 25);
  await expect.poll(async () => goblins(await view()).map((g) => g.quantity).sort()).toEqual([15, 25]);
  await expect.poll(async () => (await view()).cards[pile!.id]!.attacking?.id).toBe("p2"); // (the attack follows the split)
  let v = await view();
  expect(v.cards[pile!.id]!.quantity).toBe(25);
  const rest = goblins(v).find((g) => g.id !== pile!.id)!;
  expect(rest.attacking ?? null).toBeNull();

  const strip = page.getByTestId("combat-strip");
  await expect(strip.getByTestId("combat-total")).toContainText("25 attacking");
  await expect(strip.getByTestId("combat-total")).toContainText("50 damage unblocked");
  await expect(strip.getByTestId("combat-stack-damage")).toContainText("×25 → 50");
  await page.waitForTimeout(300);
  if (process.env.SHOT_DIR) await page.screenshot({ path: `${process.env.SHOT_DIR}/stack-attack-some.png` });
  await act({ type: "clear_combat" });

  // Tap 5 of the 15 at home (Treasure-pile style): the tapped card is the 5
  const home = page.locator(`.table-card[data-card-id="${rest.id}"]`);
  await home.click({ button: "right" });
  await menuPath(page, "Token stack ×15", "Tap some…");
  await answer(page, 5);
  await expect.poll(async () => (await view()).cards[rest.id]?.tapped).toBe(true);
  v = await view();
  expect(v.cards[rest.id]!.quantity).toBe(5);
  expect(goblins(v).filter((g) => !g.tapped && g.id !== pile!.id).map((g) => g.quantity)).toEqual([10]);

  // Sacrifice 3 of the untapped 10: they go to the graveyard and cease to exist
  const ten = goblins(v).find((g) => !g.tapped && g.id !== pile!.id)!;
  await page.locator(`.table-card[data-card-id="${ten.id}"]`).click({ button: "right" });
  await menuPath(page, "Token stack ×10", "Sacrifice some…");
  await answer(page, 3);
  await expect.poll(async () => goblins(await view()).reduce((n, g) => n + (g.quantity ?? 1), 0)).toBe(37);
  v = await view();
  expect(goblins(v).find((g) => g.id === ten.id)).toBeUndefined();
  expect(goblins(v).map((g) => g.quantity).sort((a, b) => a! - b!)).toEqual([5, 7, 25]);
});

test("400 identical triggers on the stack are one row that opens; a different object stays its own row", async ({ page }) => {
  const { gameId, act, view } = await setup(page);
  await act({ type: "create_token", player: "p1", token: { name: "Scute Swarm", power: "1", toughness: "1", type_line: "Token Creature — Insect" }, count: 1, x: 60, y: 60 });
  const swarm = (await view()).zones["p1:battlefield"]![0];
  const text = "Landfall — Whenever a land you control enters, create a 1/1 green Insect creature token.";
  for (let i = 0; i < 400; i++) await act({ type: "create_ability", text, source_id: swarm, kind: "triggered" });
  await act({ type: "create_ability", text: "Draw a card.", kind: "other" });
  expect((await view()).stack).toHaveLength(401);

  await page.goto(`/#/game/${gameId}`);
  const rows = page.getByTestId("stack-entry");
  await expect(rows).toHaveCount(2);
  await expect(rows.nth(1)).toContainText("Scute Swarm — landfall ×400");
  await expect(rows.nth(0)).toContainText("Resolves next");
  await rows.nth(1).getByTestId("stack-batch-toggle").click();
  await expect(rows.nth(1).getByTestId("stack-batch").locator("li.chain-batch-item")).toHaveCount(150);
  await page.waitForTimeout(300);
  if (process.env.SHOT_DIR) await page.screenshot({ path: `${process.env.SHOT_DIR}/stack-batch.png` });
});
