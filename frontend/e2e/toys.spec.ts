import { expect, test, type Page } from "@playwright/test";
import * as fs from "node:fs";
import { ALICE_DECK, saveDecks } from "./helpers";

/**
 * Table toys (docs/3D_DIRECTION.md §7): the dice cannon, the hidden draw bag and the Bag of Extras, on the 2D table and the
 * 3D table. The server decides every number and every draw; the cannon's dice land on its numbers in front of each player;
 * the bag's chits never reach a view; the Bag of Extras makes objects with the table's own actions. Throws are frozen
 * (window.__fyodorDice.freeze) so the checks and screenshots don't depend on software WebGL's frame rate.
 */
/** Alice's deck makes tokens for her Bag of Extras: Krenko's Goblins and a Treasure from its Tokens section. */
const TOKEN_DECK = `Commander
1x Krenko, Mob Boss (ddn) 13
Deck
1x Lightning Bolt (clb) 187
14x Mountain (cmm) 1003
Tokens
1x Treasure (ttst) T1
`;
const SHOTS = process.env.TOYS_SHOTS ?? "/tmp/gx/toys6-shots";

interface Roll { sides: number; results: number[]; coin: boolean; cannon?: { mode: "first" | "volley"; players: string[]; rounds: number[]; winner: string | null } | null }
interface View { log: { roll?: Roll; bag?: { player: string; chit: string | null; hidden: boolean }; parts: { t?: string }[] }[]; cards: Record<string, { name?: string; zone: string }>; bag?: { count: number } }

async function newGame(page: Page, renderer: "3d" | null) {
  await page.addInitScript((r) => {
    if (r) localStorage.setItem("fyodor.renderer", r);
    localStorage.setItem("fyodor.coach3d", "done");
    localStorage.setItem("fyodor.tips.seen", JSON.stringify(["off"]));
  }, renderer);
  const decks = await saveDecks(page, [TOKEN_DECK, ALICE_DECK]);
  const res = await page.request.post("/api/games", {
    data: {
      name: "Toys", mode: "local", shuffle: false, first_player: 0, mulligan_rule: "none",
      players: [{ name: "Alice", deck_id: decks[0]!.id }, { name: "Bob", deck_id: decks[1]!.id }],
    },
  });
  const gameId = ((await res.json()) as { game: { id: string } }).game.id;
  await page.goto(`/#/game/${gameId}`);
  const act = async (action: Record<string, unknown>, as?: string) => {
    expect((await page.request.post(`/api/games/${gameId}/actions`, { data: as ? { action, as } : { action } })).ok()).toBeTruthy();
  };
  const view = async (viewer = "p1"): Promise<View> => (await (await page.request.get(`/api/games/${gameId}/view?viewer=${viewer}`)).json()) as View;
  const raw = async (viewer: string) => (await page.request.get(`/api/games/${gameId}/view?viewer=${viewer}`)).text();
  const lastRoll = async () => (await view()).log.filter((e) => e.roll).at(-1)!.roll!;
  return { act, view, raw, lastRoll };
}

/** The throws a cannon roll makes (game/cannon.ts volleys): per volley, per player, the server's numbers. */
function throwsOf(roll: Roll): { round: number; player: string; labels: string[] }[] {
  const out: { round: number; player: string; labels: string[] }[] = [];
  roll.results.forEach((v, i) => {
    const player = roll.cannon!.players[i]!;
    const round = roll.cannon!.rounds[i]!;
    let t = out.find((x) => x.round === round && x.player === player);
    if (!t) out.push((t = { round, player, labels: [] }));
    t.labels.push(String(v));
  });
  return out;
}

/** A screenshot with the panels' entry animations done (the cannon's own, held at the frozen dice clock, stay as they are). */
const shot = async (page: Page, name: string) => {
  await page.evaluate(() => document.getAnimations().forEach((a) => { if (a.playState === "running") a.finish(); }));
  await page.screenshot({ path: `${SHOTS}/${name}.png` });
};
/** The roll panel, from the Bag of Extras by my seat (its dice): the 2D button, or the 3D table's medallion. */
async function openRollPanel(page: Page) {
  const button = await page.evaluate(() => window.__fyodor3d?.buttonAt("extras" as never) ?? null);
  if (button) await page.mouse.click(button.x, button.y);
  else await page.getByTestId("seat-btn-extras").click();
  await page.getByTestId("extras-panel").getByTestId("dice-button").click();
  await expect(page.getByTestId("dice-panel")).toBeVisible();
}

const frames = (page: Page) => page.evaluate(() => new Promise<void>((done) => requestAnimationFrame(() => requestAnimationFrame(() => requestAnimationFrame(() => done())))));

test.beforeAll(() => fs.mkdirSync(SHOTS, { recursive: true }));

test("2D table: the dice cannon, the draw bag and the Bag of Extras", async ({ page }) => {
  test.setTimeout(150_000);
  const { act, view, raw, lastRoll } = await newGame(page, null);
  await expect(page.getByTestId("seat-p2")).toBeVisible();
  // -- the dice cannon: who goes first. Caught in flight, then at rest.
  await page.evaluate(() => window.__fyodorDice!.freeze(1250));
  await openRollPanel(page);
  await expect(page.getByTestId("dice-panel")).toBeVisible();
  await shot(page, "2d-roll-panel-toys");
  await page.getByTestId("cannon-first").click();
  await page.keyboard.press("Escape");
  await expect.poll(async () => (await lastRoll()).cannon?.mode).toBe("first");
  const first = await lastRoll();
  const throws = throwsOf(first);
  expect(new Set(first.cannon!.players)).toEqual(new Set(["p1", "p2"]));
  await expect.poll(() => page.evaluate(() => window.__fyodorDice2d?.state().length ?? 0), { timeout: 30_000 }).toBe(throws.length);
  await expect(page.getByTestId("cannon-2d")).toBeVisible();
  await frames(page);
  await shot(page, "2d-cannon-flight");
  await page.evaluate(() => window.__fyodorDice!.freeze(30000));
  // each die shows the server's number, and lands on the mat of the player it was fired at
  const state = await page.evaluate(() => window.__fyodorDice2d!.state());
  expect(state.map((t) => t.dice.map((d) => d.label))).toEqual(throws.map((t) => t.labels));
  const mats = await Promise.all(["p1", "p2"].map(async (p) => (await page.locator(`[data-drop="${p}:battlefield"]`).boundingBox())!));
  for (const p of await page.evaluate(() => window.__fyodorDice2d!.positions())) {
    expect(mats.some((m) => p.x > m.x && p.x < m.x + m.width && p.y > m.y && p.y < m.y + m.height)).toBe(true);
  }
  const names: Record<string, string> = { p1: "Alice", p2: "Bob" };
  const winner = first.cannon!.winner!;
  const deciding = first.results[first.results.length - 1 - [...first.cannon!.players].reverse().indexOf(winner)]!;
  await expect(page.getByTestId("dice-line").filter({ hasText: "Goes first" })).toContainText(`${names[winner]} · d20: ${deciding}`);
  const headline = (await view()).log.filter((e) => e.roll).at(-1)!.parts.map((p) => p.t ?? "").join("");
  expect(headline.startsWith(`${names[winner]} goes first (${deciding}) — Alice fired the dice cannon`)).toBe(true);
  await frames(page);
  await shot(page, "2d-cannon-first");
  // a volley of the dice picked in the roll panel, onto the firer's mat
  await openRollPanel(page);
  await page.getByTestId("dice-kind-d6").click();
  await page.getByRole("button", { name: "One more" }).click();
  await page.getByRole("button", { name: "One more" }).click();
  await page.getByTestId("cannon-fire").click();
  await page.keyboard.press("Escape");
  await expect.poll(async () => (await lastRoll()).cannon?.mode).toBe("volley");
  const volley = await lastRoll();
  expect(volley.sides).toBe(6);
  expect(volley.cannon!.players).toEqual(["p1", "p1", "p1"]);
  await expect.poll(() => page.evaluate(() => window.__fyodorDice2d!.state().map((t) => t.dice.map((d) => d.label).join(",")))).toContain(volley.results.join(","));

  // -- the draw bag: filled from the roll panel, its chits never in any view
  await openRollPanel(page);
  await page.getByTestId("bag-open").click();
  const panel = page.getByTestId("bag-panel");
  await expect(panel).toBeVisible();
  const words = ["Red team", "Blue team", "Green team"];
  await panel.getByTestId("bag-text").fill(words.join(", "));
  await panel.getByTestId("bag-fill").click();
  await expect(panel.getByTestId("bag-count")).toContainText("3 chits inside");
  for (const viewer of ["p1", "p2", "spectator"]) {
    const blob = await raw(viewer);
    for (const w of words) expect(blob).not.toContain(w);
  }
  await panel.getByTestId("bag-draw").click();
  const chit = page.getByTestId("bag-chit").first();
  await expect(chit).toBeVisible();
  const drawn = (await view()).log.filter((e) => e.bag).at(-1)!.bag!.chit!;
  expect(words).toContain(drawn);
  await expect(chit).toContainText(drawn);
  await expect(panel.getByTestId("bag-count")).toContainText("2 chits inside");
  await shot(page, "2d-bag-draw");
  // Bob draws one he keeps hidden: Alice's table sees only that he drew; his chit is in no view but his
  await act({ type: "bag_draw", reveal: false }, "p2");
  await expect(page.getByTestId("bag-chit").filter({ hasText: "a hidden chit" })).toBeVisible();
  const bobs = (await view("p2")).log.filter((e) => e.bag).at(-1)!.bag!.chit!;
  expect(words.filter((w) => w !== drawn)).toContain(bobs);
  for (const viewer of ["p1", "spectator"]) expect(await raw(viewer)).not.toContain(bobs);
  await page.keyboard.press("Escape");

  // -- the Bag of Extras, by my seat: a Treasure out of it
  await page.getByTestId("seat-btn-extras").click();
  const extras = page.getByTestId("extras-panel");
  await expect(extras).toBeVisible();
  await shot(page, "2d-extras");
  await extras.getByTestId("extras-treasure").click();
  await expect.poll(async () => Object.values((await view()).cards).filter((c) => c.name === "Treasure" && c.zone === "p1:battlefield").length).toBe(1);
});

test("3D table: the dice cannon rolls in, fires who goes first and a volley, and rolls off", async ({ page }) => {
  test.setTimeout(480_000); // software WebGL on a shared machine: a frame can take seconds
  const { lastRoll } = await newGame(page, "3d");
  await expect.poll(() => page.evaluate(() => !!window.__fyodor3d), { timeout: 60_000 }).toBe(true);
  await page.evaluate(() => window.__fyodorDice!.freeze(1250));
  await openRollPanel(page);
  await page.getByTestId("cannon-first").click();
  await page.keyboard.press("Escape");
  await expect.poll(async () => (await lastRoll()).cannon?.mode).toBe("first");
  const first = await lastRoll();
  const throws = throwsOf(first);
  await expect.poll(() => page.evaluate(() => window.__fyodor3d!.diceState().length), { timeout: 30_000 }).toBe(throws.length);
  // the cannon is out on the table, at the end of the aisle, while it fires
  await expect.poll(() => page.evaluate(() => window.__fyodor3d!.cannon!().busy)).toBe(true);
  await frames(page);
  await shot(page, "3d-cannon-flight");
  await page.evaluate(() => window.__fyodorDice!.freeze(30000));
  await frames(page);
  const state = await page.evaluate(() => window.__fyodor3d!.diceState());
  expect(state.map((t) => t.dice.map((d) => d.label))).toEqual(throws.map((t) => t.labels));
  // gone again once the dice are on the table (it never stays on the mats)
  await expect.poll(() => page.evaluate(() => window.__fyodor3d!.cannon!().busy), { timeout: 30_000 }).toBe(false);
  await expect(page.getByTestId("dice-line").filter({ hasText: "Goes first" })).toHaveCount(1);
  await shot(page, "3d-cannon-first");
  // a volley: 4d8 across the table onto my mat
  await page.evaluate(() => window.__fyodorDice!.freeze(1350));
  await openRollPanel(page);
  await page.getByTestId("dice-kind-d8").click();
  for (let i = 0; i < 3; i++) await page.getByRole("button", { name: "One more" }).click();
  await page.getByTestId("cannon-fire").click();
  await page.keyboard.press("Escape");
  await expect.poll(async () => (await lastRoll()).cannon?.mode).toBe("volley");
  const volley = await lastRoll();
  await expect.poll(() => page.evaluate(() => window.__fyodor3d!.cannon!().busy)).toBe(true);
  await frames(page);
  await shot(page, "3d-cannon-volley-flight");
  await page.evaluate(() => window.__fyodorDice!.freeze(30000));
  await expect.poll(() => page.evaluate(() => window.__fyodor3d!.diceState().map((t) => t.dice.map((d) => d.label).join(",")))).toContain(volley.results.join(","));
  await frames(page);
  await shot(page, "3d-cannon-volley");
});

test("3D table: the draw bag draws, and the Bag of Extras is the brass button by the seat", async ({ page }) => {
  test.setTimeout(480_000);
  const { view } = await newGame(page, "3d");
  await expect.poll(() => page.evaluate(() => !!window.__fyodor3d), { timeout: 60_000 }).toBe(true);
  // the draw bag
  await openRollPanel(page);
  await page.getByTestId("bag-open").click();
  const panel = page.getByTestId("bag-panel");
  await panel.getByRole("button", { name: "Player names" }).click();
  await expect(panel.getByTestId("bag-count")).toContainText("2 chits inside");
  await panel.getByTestId("bag-draw-hidden").click();
  await expect(panel.getByTestId("bag-mine")).toBeVisible();
  const mine = (await view()).log.filter((e) => e.bag).at(-1)!.bag!;
  expect(mine.hidden).toBe(true);
  expect(["Alice", "Bob"]).toContain(mine.chit);
  await expect(page.getByTestId("bag-chit").first()).toContainText(mine.chit!);
  await shot(page, "3d-bag-draw"); // (the chit goes after a few seconds: a frame of software WebGL can take that long)
  await page.keyboard.press("Escape");

  // the Bag of Extras: the medallion past my seat's buttons
  const pouch = (await page.evaluate(() => window.__fyodor3d!.buttonAt("extras" as never)))!;
  expect(pouch).not.toBeNull();
  await page.mouse.click(pouch.x, pouch.y);
  const extras = page.getByTestId("extras-panel");
  await expect(extras).toBeVisible();
  await frames(page);
  await shot(page, "3d-extras");
  await extras.getByTestId("extras-goblin").click();
  await expect.poll(async () => Object.values((await view()).cards).filter((c) => c.name === "Goblin" && c.zone === "p1:battlefield").length).toBe(1);
});
