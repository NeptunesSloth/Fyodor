import { expect, test, type Page } from "@playwright/test";
import { ALICE_DECK, BOB_DECK } from "./helpers";

/**
 * Frames of the 3D table's motion for review (table3d/motion3d.ts): a card cast from another player's hidden hand, draws,
 * a mill, a shuffle, a bounce to a hidden hand, an attack with a block, and the damage numbers. Skipped unless SHOT_DIR is
 * set. Headless software WebGL draws about a frame a second, so each motion is frozen at a set time
 * (window.__fyodor3d.motionFreeze) before its frame is taken.
 */
const OUT = process.env.SHOT_DIR ?? "";
test.skip(!OUT, "set SHOT_DIR to capture motion screenshots");

type View = { seat_order: string[]; zones: Record<string, string[] | { count: number }>; cards: Record<string, { zone: string; name?: string }> };

async function setup(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem("fyodor.renderer", "3d");
    localStorage.setItem("fyodor.welcomeDone", "1");
    localStorage.setItem("fyodor.coach3d", "done");
    localStorage.setItem("fyodor.tips.seen", JSON.stringify(["off"]));
    localStorage.setItem("fyodor.profiles", JSON.stringify({ version: 2, active: "t", profiles: [{ id: "t", name: "Alice", avatar: "A", prefs: { ambience: false } }] }));
  });
  const decks: { id: string }[] = [];
  for (const text of [ALICE_DECK, BOB_DECK]) decks.push((await (await page.request.post("/api/decks", { data: { text } })).json()) as { id: string });
  const res = await page.request.post("/api/games", {
    data: {
      name: "Motion", format: "commander", mode: "local", shuffle: false, first_player: 0, auto_untap: true, mulligan_rule: "none",
      players: ["Alice", "Bob"].map((name, i) => ({ name, deck_id: decks[i]!.id })),
    },
  });
  expect(res.ok(), await res.text()).toBeTruthy();
  const gameId = ((await res.json()) as { game: { id: string } }).game.id;
  const act = async (as: string, action: Record<string, unknown>) => {
    const r = await page.request.post(`/api/games/${gameId}/actions`, { data: { action, as } });
    expect(r.ok(), await r.text()).toBeTruthy();
  };
  const view = async (v = "p1") => (await (await page.request.get(`/api/games/${gameId}/view?viewer=${v}`)).json()) as View;
  const hand = async (pid: string) => (await view(pid)).zones[`${pid}:hand`] as string[];
  for (const pid of ["p1", "p2"]) {
    await act(pid, { type: "draw", player: pid, count: 6 });
    const ids = (await hand(pid)).slice(0, 2);
    for (const [i, cid] of ids.entries()) await act(pid, { type: "move", card_ids: [cid], to: { zone: "battlefield", player: pid }, x: 60 + i * 110, y: 400 });
    await act(pid, { type: "create_token", player: pid, token: { name: pid === "p1" ? "Soldier" : "Goblin", power: "2", toughness: "2", colors: [pid === "p1" ? "W" : "R"], type_line: "Token Creature" }, count: 2, stacked: false, x: 420, y: 120 });
  }
  await page.setViewportSize({ width: 1600, height: 900 });
  await page.goto(`/#/game/${gameId}`);
  await expect(page.getByTestId("table-3d")).toBeVisible({ timeout: 60_000 });
  await expect.poll(() => page.evaluate(() => window.__fyodor3d?.stats().cards ?? 0), { timeout: 60_000 }).toBeGreaterThanOrEqual(8);
  await page.waitForTimeout(2500);
  return { gameId, act, view, hand };
}

/** Wait until the table has drawn a few frames (a frame can take a second in software WebGL). */
async function frames(page: Page) {
  await page.evaluate(() => new Promise<void>((done) => requestAnimationFrame(() => requestAnimationFrame(() => requestAnimationFrame(() => done())))));
}

async function freeze(page: Page, ms: number | null) {
  await page.evaluate((t) => window.__fyodor3d?.motionFreeze?.(t), ms);
}

/** Wait for the motion an action started, then take its frame. */
async function shoot(page: Page, name: string) {
  await expect.poll(() => page.evaluate(() => window.__fyodor3d?.motion?.().busy ?? true), { timeout: 15_000 }).toBe(true);
  await frames(page);
  await page.screenshot({ path: `${OUT}/${name}.png` });
}

/** Let everything that was frozen finish, then settle. */
async function settle(page: Page) {
  await freeze(page, null);
  await expect.poll(() => page.evaluate(() => window.__fyodor3d?.motion?.().busy ?? false), { timeout: 15_000 }).toBe(false);
  await frames(page);
}

test("3D table motion: flights, library, combat and numbers", async ({ page }) => {
  test.setTimeout(400_000);
  const { act, view, hand } = await setup(page);
  await page.screenshot({ path: `${OUT}/00-board.png` });

  // Bob casts a card from his hidden hand: it leaves his hand fan as a back and turns face up on its way to the stack
  await freeze(page, 40);
  await act("p2", { type: "move", card_ids: [(await hand("p2"))[0]], to: { zone: "stack" } });
  await shoot(page, "01-cast-from-hidden-hand");
  // the same moment from above the whole table
  await page.evaluate(() => window.__fyodor3d!.camera("overview"));
  await page.waitForTimeout(1500);
  await frames(page);
  await page.screenshot({ path: `${OUT}/01a-cast-overview.png` });
  await page.evaluate(() => window.__fyodor3d!.camera("seat"));
  await page.waitForTimeout(1500);
  await settle(page);
  await page.screenshot({ path: `${OUT}/01b-cast-landed.png` });
  // it resolves: from the stack to Bob's graveyard
  const cast = Object.entries((await view("p1")).cards).find(([, c]) => c.zone === "stack")![0];
  await act("p2", { type: "move", card_ids: [cast], to: { zone: "graveyard", player: "p2" } });
  await settle(page);

  // my own cast starts at my hand (the near edge of my mat)
  await freeze(page, 45);
  await act("p1", { type: "move", card_ids: [(await hand("p1"))[0]], to: { zone: "stack" } });
  await shoot(page, "01c-my-cast");
  await settle(page);
  const mine = Object.entries((await view("p1")).cards).find(([, c]) => c.zone === "stack")![0];
  await act("p1", { type: "move", card_ids: [mine], to: { zone: "graveyard", player: "p1" } });
  await settle(page);

  // draws: mine to the near edge of my mat, Bob's to his hand fan (both as card backs)
  await freeze(page, 70);
  await act("p1", { type: "draw", player: "p1", count: 1 });
  await act("p2", { type: "draw", player: "p2", count: 2 });
  await shoot(page, "02-draws");
  await settle(page);

  // a mill: from the top of Bob's library, turning face up, to his graveyard
  await freeze(page, 110);
  await act("p2", { type: "mill", player: "p2", count: 3 });
  await shoot(page, "03-mill");
  await settle(page);

  // a shuffle: a riffle on my library
  await freeze(page, 160);
  await act("p1", { type: "shuffle", player: "p1" });
  await shoot(page, "04-shuffle-split");
  await freeze(page, 330);
  await frames(page);
  await page.screenshot({ path: `${OUT}/04b-shuffle-interleave.png` });
  await settle(page);

  // a bounce to Bob's hidden hand: the card turns face down on its way to his fan
  const bobBf = (await view("p1")).zones["p2:battlefield"] as string[];
  await freeze(page, 45);
  await act("p1", { type: "move", card_ids: [bobBf[0]], to: { zone: "hand", player: "p2" } });
  await shoot(page, "05-bounce-face-down");
  await settle(page);

  // combat: my Soldier attacks Bob, his Goblin blocks it; then damage lands
  const v = await view("p1");
  const soldier = Object.entries(v.cards).find(([, c]) => c.zone === "p1:battlefield" && c.name === "Soldier")![0];
  const soldier2 = Object.entries(v.cards).filter(([, c]) => c.zone === "p1:battlefield" && c.name === "Soldier")[1]![0];
  const goblin = Object.entries(v.cards).find(([, c]) => c.zone === "p2:battlefield" && c.name === "Goblin")![0];
  await act("p1", { type: "phase", to: "declare_attackers", force: true });
  await act("p1", { type: "attack", card_ids: [soldier, soldier2], target: { kind: "player", id: "p2" } });
  await act("p2", { type: "block", card_id: goblin, attacker_id: soldier });
  await page.waitForTimeout(2500);
  await settle(page);
  await page.screenshot({ path: `${OUT}/06-attack-block.png` });
  await act("p1", { type: "phase", to: "combat_damage", force: true });
  await freeze(page, 75);
  await act("p1", { type: "set_damage", card_ids: [goblin], value: 2 });
  await act("p1", { type: "life", player: "p2", delta: -2 });
  await shoot(page, "07-strike-and-numbers");
  await freeze(page, 450);
  await frames(page);
  await page.screenshot({ path: `${OUT}/07b-numbers-rising.png` });
  await settle(page);
  await act("p1", { type: "clear_combat" });
  await page.waitForTimeout(2500);
  await page.screenshot({ path: `${OUT}/08-combat-over.png` });
});

test("3D table motion: cost on a four-seat board of 100+ cards, idle and with motion running", async ({ page }) => {
  test.setTimeout(400_000);
  await page.addInitScript(() => {
    localStorage.setItem("fyodor.renderer", "3d");
    localStorage.setItem("fyodor.welcomeDone", "1");
    localStorage.setItem("fyodor.coach3d", "done");
    localStorage.setItem("fyodor.tips.seen", JSON.stringify(["off"]));
    localStorage.setItem("fyodor.profiles", JSON.stringify({ version: 2, active: "t", profiles: [{ id: "t", name: "Alice", avatar: "A", prefs: { ambience: false } }] }));
  });
  const decks: { id: string }[] = [];
  for (const text of [ALICE_DECK, BOB_DECK]) decks.push((await (await page.request.post("/api/decks", { data: { text } })).json()) as { id: string });
  const res = await page.request.post("/api/games", {
    data: {
      name: "Motion perf", format: "commander", mode: "local", shuffle: false, first_player: 0, auto_untap: true, mulligan_rule: "none",
      players: ["Alice", "Bob", "Casey", "Jordan"].map((name, i) => ({ name, deck_id: decks[i % 2]!.id })),
    },
  });
  const gameId = ((await res.json()) as { game: { id: string } }).game.id;
  const act = async (as: string, action: Record<string, unknown>) => {
    const r = await page.request.post(`/api/games/${gameId}/actions`, { data: { action, as } });
    expect(r.ok(), await r.text()).toBeTruthy();
  };
  for (const pid of ["p1", "p2", "p3", "p4"]) {
    await act(pid, { type: "draw", player: pid, count: 5 });
    for (let i = 0; i < 27; i++) await act(pid, { type: "create_token", player: pid, token: { name: `Thopter ${i}`, power: "1", toughness: "1", colors: ["U"], type_line: "Token Artifact Creature" }, count: 1, stacked: false, x: 20 + (i % 9) * 100, y: 30 + Math.floor(i / 9) * 140 });
  }
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto(`/#/game/${gameId}`);
  await expect.poll(() => page.evaluate(() => window.__fyodor3d?.stats().cards ?? 0), { timeout: 60_000 }).toBeGreaterThanOrEqual(108);
  const sample = async () => {
    await page.waitForTimeout(6000); // stats refresh once a second; a frame takes about a second in software WebGL
    return page.evaluate(() => ({ ...window.__fyodor3d!.stats(), motion: window.__fyodor3d!.motion!() }));
  };
  const idle = await sample();
  // a busy moment held mid-way: everyone draws, a mill, a shuffle, life changes (held so every frame steps it)
  await freeze(page, 120);
  for (const pid of ["p2", "p3", "p4"]) await act(pid, { type: "draw", player: pid, count: 2 });
  await act("p1", { type: "draw", player: "p1", count: 2 });
  await act("p3", { type: "mill", player: "p3", count: 6 });
  await act("p4", { type: "shuffle", player: "p4" });
  for (const pid of ["p1", "p2", "p3", "p4"]) await act(pid, { type: "life", player: pid, delta: -3 });
  const busy = await sample();
  await page.screenshot({ path: `${OUT}/09-four-seats-busy.png` });
  await settle(page);
  const after = await sample();
  const out = { idle, busy, after };
  console.log("motion3d perf", JSON.stringify(out));
  const fs = await import("node:fs");
  fs.writeFileSync(`${OUT}/perf.json`, JSON.stringify(out, null, 2));
  expect(after.motion.busy).toBe(false); // nothing left running when idle
});
