import { expect, test, type Page } from "@playwright/test";
import { saveDecks } from "./helpers";

/**
 * The large card preview (game/Hud.tsx CardPreview): docked on the right under the top bar, it never chases the pointer;
 * it goes when the hover ends (also when the hovered card leaves the page under the pointer), on Esc, and with its close
 * button until the next hover.
 */
type V = { zones: Record<string, string[]>; cards: Record<string, { name?: string }> };

/** A local game, Alice holding 7; `before` runs before the table opens. */
async function newGame(page: Page, renderer: "3d" | null, before?: (act: (a: Record<string, unknown>) => Promise<void>, view: () => Promise<V>) => Promise<void>) {
  await page.addInitScript((r) => {
    if (r) localStorage.setItem("fyodor.renderer", r);
    localStorage.setItem("fyodor.coach3d", "done");
    localStorage.setItem("fyodor.tips.seen", JSON.stringify(["off"]));
  }, renderer);
  const decks = await saveDecks(page);
  const res = await page.request.post("/api/games", {
    data: {
      name: "Preview", mode: "local", shuffle: false, first_player: 0, mulligan_rule: "none",
      players: [{ name: "Alice", deck_id: decks[0]!.id }, { name: "Bob", deck_id: decks[1]!.id }],
    },
  });
  const gameId = ((await res.json()) as { game: { id: string } }).game.id;
  const act = async (action: Record<string, unknown>) => {
    expect((await page.request.post(`/api/games/${gameId}/actions`, { data: { action } })).ok()).toBeTruthy();
  };
  const view = async () => (await (await page.request.get(`/api/games/${gameId}/view?viewer=p1`)).json()) as V;
  await act({ type: "draw", player: "p1", count: 7 });
  await before?.(act, view);
  await page.goto(`/#/game/${gameId}`);
  return { act, view };
}

const previewText = (page: Page) => page.evaluate(() => document.querySelector('[data-testid="card-preview"]')?.textContent ?? "");

test("2D table: the preview stays docked right, and goes when its card leaves the page, on Esc and with its close button", async ({ page }) => {
  const { act, view } = await newGame(page, null);
  const hand = page.locator(".hand-card");
  await expect(hand).toHaveCount(7);
  const preview = page.getByTestId("card-preview");
  // from the right end of the hand to the left end: docked right all the way (it used to flip at 62% of the width)
  await hand.last().hover();
  await expect(preview).toBeVisible();
  await expect(preview).toHaveAttribute("data-dock", "right");
  await hand.first().hover();
  await expect(preview).toHaveAttribute("data-dock", "right");
  const box = (await preview.boundingBox())!;
  expect(box.x + box.width).toBeGreaterThan(page.viewportSize()!.width - 30);
  expect(box.y).toBeGreaterThan(80); // under the top bar and the stack pill

  // Esc closes it
  await page.keyboard.press("Escape");
  await expect(preview).toHaveCount(0);
  // the next hover brings it back; its close button hides it (clicked where it is, the pointer still on the card)
  await hand.nth(2).hover();
  await expect(preview).toBeVisible();
  await page.getByTestId("card-preview-close").dispatchEvent("click");
  await expect(preview).toHaveCount(0);

  // a hovered hand card played from under the pointer: its preview goes with it (no pointerleave ever comes)
  await hand.nth(4).hover();
  await expect(preview).toBeVisible();
  const id = (await hand.nth(4).getAttribute("data-card-id"))!;
  const name = (await view()).cards[id]!.name!;
  await expect.poll(() => previewText(page)).toContain(name);
  await act({ type: "move", card_ids: [id], to: { zone: "battlefield", player: "p1" }, x: 40, y: 40 });
  await expect(hand).toHaveCount(6);
  await expect.poll(() => previewText(page)).not.toContain(name);
});

test("3D table: hovering a card on the table shows the preview on the right; empty table hides it", async ({ page }) => {
  test.setTimeout(240_000); // software WebGL
  let id = "";
  await newGame(page, "3d", async (act, view) => {
    id = (await view()).zones["p1:hand"]![0]!;
    await act({ type: "move", card_ids: [id], to: { zone: "battlefield", player: "p1" }, x: 300, y: 80 });
  });
  await expect.poll(() => page.evaluate(() => !!window.__fyodor3d), { timeout: 60_000 }).toBe(true);
  await expect.poll(() => page.evaluate((c) => window.__fyodor3d!.cardAt(c), id), { timeout: 30_000 }).not.toBeNull();
  await expect.poll(() => page.evaluate(() => window.__fyodor3d!.motion?.().busy ?? false), { timeout: 30_000 }).toBe(false);
  const at = (await page.evaluate((c) => window.__fyodor3d!.cardAt(c), id))!;
  const preview = page.getByTestId("card-preview");
  await page.mouse.move(at.x - 20, at.y - 10);
  await page.mouse.move(at.x, at.y, { steps: 4 });
  await expect(preview).toBeVisible({ timeout: 30_000 });
  await expect(preview).toHaveAttribute("data-dock", "right");
  // over empty table (the aisle between the mats)
  const vp = page.viewportSize()!;
  await page.mouse.move(vp.width * 0.2, vp.height * 0.5, { steps: 4 });
  await expect(preview).toHaveCount(0, { timeout: 30_000 });
});
