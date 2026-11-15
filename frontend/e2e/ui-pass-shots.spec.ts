import { expect, test, type Page } from "@playwright/test";
import { ALICE_DECK, BOB_DECK } from "./helpers";

/**
 * The game-night UI pass (a player's screenshot): the choice wheel's mana tokens on their ring, a big token pile and a
 * land pile on the arranged 3D table (no black slab under the pile, no cut-off names peeking out), an ability on the
 * stack and the selection toolbar beside it. The wheel check always runs; screenshots only with SHOT_DIR set.
 */
const OUT = process.env.SHOT_DIR ?? "";

test("choice wheel tokens sit on their ring in the production CSS (no clash with the global .mana symbol class)", async ({ page }) => {
  await page.goto("/");
  await page.waitForLoadState("networkidle");
  // the markup ChoiceWheel renders for five mana options, the dial's centre at (400, 400) and a 91 px ring
  const off = await page.evaluate(() => {
    const root = document.createElement("div");
    root.className = "choice-wheel";
    root.style.left = "400px";
    root.style.top = "400px";
    root.style.animation = "none"; // (measured settled, not mid scale-in)
    const ring = [-90, -18, 54, 126, 198].map((d) => (d * Math.PI) / 180);
    for (const a of ring) {
      const b = document.createElement("button");
      b.className = "wheel-opt k-mana disc";
      Object.assign(b.style, { left: `${Math.round(91 * Math.cos(a))}px`, top: `${Math.round(91 * Math.sin(a))}px`, width: "52px", height: "52px" });
      root.append(b);
    }
    document.body.append(root);
    const got = [...root.querySelectorAll("button")].map((b) => {
      const r = b.getBoundingClientRect();
      return [r.left + r.width / 2, r.top + r.height / 2];
    });
    root.remove();
    return got.map(([x, y], i) => Math.hypot(x! - (400 + 91 * Math.cos(ring[i]!)), y! - (400 + 91 * Math.sin(ring[i]!))));
  });
  expect(Math.max(...off)).toBeLessThan(2);
});

async function arrangedBoard(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem("fyodor.renderer", "3d");
    localStorage.setItem("fyodor.welcomeDone", "1");
    localStorage.setItem("fyodor.profiles", JSON.stringify({ version: 2, active: "t", profiles: [{ id: "t", name: "Alice", avatar: "A", prefs: { ambience: false } }] }));
  });
  for (const text of [ALICE_DECK, BOB_DECK]) await page.request.post("/api/decks", { data: { text } });
  const decks = (await (await page.request.get("/api/decks")).json()) as { id: string }[];
  const res = await page.request.post("/api/games", {
    data: {
      name: "UI pass", format: "commander", mode: "local", shuffle: false, first_player: 0, auto_untap: true, mulligan_rule: "none",
      players: ["Alice", "Bob"].map((name, i) => ({ name, deck_id: decks[i]!.id })),
    },
  });
  const gameId = ((await res.json()) as { game: { id: string } }).game.id;
  const act = async (action: Record<string, unknown>) => {
    const r = await page.request.post(`/api/games/${gameId}/actions`, { data: { action } });
    if (!r.ok()) console.log("action refused", JSON.stringify(action).slice(0, 120), (await r.text()).slice(0, 200));
  };
  const view = async () => (await (await page.request.get(`/api/games/${gameId}/view?viewer=p1`)).json()) as { zones: Record<string, string[]> };
  // Bob: 80 separate Scute-Swarm-like tokens (the arranged board piles them ×80) and a pile of identical lands
  await act({ type: "create_token", player: "p2", token: { name: "Scute Swarm", power: "1", toughness: "1", colors: ["G"], type_line: "Token Creature — Insect" }, count: 80, stacked: false, x: 40, y: 40 });
  await act({ type: "create_token", player: "p2", token: { name: "Plant", power: "0", toughness: "1", colors: ["G"], type_line: "Token Creature — Plant" }, count: 12, stacked: false, x: 300, y: 40 });
  await act({ type: "draw", player: "p1", count: 8 });
  const hand = (await view()).zones["p1:hand"]!;
  for (const [i, id] of hand.slice(0, 4).entries()) await act({ type: "move", card_ids: [id], to: { zone: "battlefield", player: "p1" }, x: 40 + i * 95, y: 40 });
  await act({ type: "move", card_ids: [hand[4]], to: { zone: "stack" } });
  await page.goto(`/#/game/${gameId}`);
  await expect(page.getByTestId("table-3d")).toBeVisible({ timeout: 60_000 });
  await expect.poll(() => page.evaluate(() => window.__fyodor3d?.stats().cards ?? 0), { timeout: 30_000 }).toBeGreaterThanOrEqual(90);
  await page.waitForTimeout(3000);
  return { gameId, act, hand };
}

test("arranged 3D table: a ×80 token pile, a land pile, the stack and the toolbar", async ({ page }) => {
  test.skip(!OUT, "set SHOT_DIR to capture the screenshots");
  await page.setViewportSize({ width: 1920, height: 1080 });
  const { hand } = await arrangedBoard(page);
  await page.screenshot({ path: `${OUT}/ui-pass-board.png` });
  // Bob's board up close: the ×80 pile lies low, only its top card is labelled, and no black slab spreads under it
  await page.evaluate(() => window.__fyodor3d?.camera({ focus: "p2" }));
  await page.waitForTimeout(2500);
  await page.screenshot({ path: `${OUT}/ui-pass-piles.png` });
  await page.evaluate(() => window.__fyodor3d?.camera("seat"));
  await page.waitForTimeout(2000);
  // select a creature near the stack: the toolbar must not cover the standing stack cards
  const at = await page.evaluate((id) => window.__fyodor3d?.cardAt(id) ?? null, hand[0]!);
  if (at) {
    await page.mouse.click(at.x, at.y);
    await page.waitForTimeout(800);
    await page.screenshot({ path: `${OUT}/ui-pass-toolbar.png` });
  }
});
