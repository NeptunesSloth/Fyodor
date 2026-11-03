import { expect, test, type Page } from "@playwright/test";
import { ALICE_DECK, BOB_DECK, menuPath } from "./helpers";

/** The 3D table (M19): opt in on this device, then play a few moves with the mouse. */
async function fourPlayerTable(page: Page, perSeatOnBattlefield: number, plane = "dominaria", boardLayout: "arranged" | "free" = "arranged") {
  await page.addInitScript(([pl, layout]) => {
    localStorage.setItem("fyodor.renderer", "3d");
    localStorage.setItem("fyodor.welcomeDone", "1");
    localStorage.setItem("fyodor.profiles", JSON.stringify({ version: 2, active: "t", profiles: [{ id: "t", name: "Alice", avatar: "A", prefs: { plane: pl, ambience: false, boardLayout: layout } }] }));
  }, [plane, boardLayout] as const);
  for (const text of [ALICE_DECK, BOB_DECK]) expect((await page.request.post("/api/decks", { data: { text } })).ok()).toBeTruthy();
  const decks = (await (await page.request.get("/api/decks")).json()) as { id: string }[];
  const res = await page.request.post("/api/games", {
    data: {
      name: "3D", format: "commander", mode: "local", shuffle: false, first_player: 0, auto_untap: true, mulligan_rule: "none",
      players: ["Alice", "Bob", "Casey", "Jordan"].map((name, i) => ({ name, deck_id: decks[i % decks.length]!.id })),
    },
  });
  expect(res.ok()).toBeTruthy();
  const gameId = ((await res.json()) as { game: { id: string } }).game.id;
  const act = async (action: Record<string, unknown>) => {
    const r = await page.request.post(`/api/games/${gameId}/actions`, { data: { action } });
    expect(r.ok(), await r.text()).toBeTruthy();
  };
  const view = async (viewer = "p1") => (await (await page.request.get(`/api/games/${gameId}/view?viewer=${viewer}`)).json()) as { seat_order: string[]; zones: Record<string, string[]>; cards: Record<string, { name: string; tapped?: boolean; zone: string; x?: number; y?: number }> };
  let v = await view();
  for (const pid of v.seat_order) await act({ type: "draw", player: pid, count: Math.min(12, perSeatOnBattlefield + 3) });
  for (const pid of v.seat_order) {
    const own = await view(pid); // each player's own hand (the host computer may look from any seat)
    const ids = own.zones[`${pid}:hand`]!.slice(0, perSeatOnBattlefield);
    for (const [i, cid] of ids.entries()) await act({ type: "move", card_ids: [cid], to: { zone: "battlefield", player: pid }, x: 20 + (i % 10) * 95, y: 30 + Math.floor(i / 10) * 140 });
  }
  await page.goto(`/#/game/${gameId}`);
  await expect(page.getByTestId("table-3d")).toBeVisible({ timeout: 30_000 }); // software WebGL on a CI runner is slow to start
  await expect.poll(() => page.evaluate(() => window.__fyodor3d?.stats().cards ?? 0), { timeout: 20_000 }).toBeGreaterThanOrEqual(perSeatOnBattlefield * 4);
  return { gameId, act, view };
}

test("3D table: seats, drag from hand onto the table, right-click menu, tap", async ({ page }) => {
  test.slow(); // many mouse steps, each waiting on rendered frames: software WebGL (CI, no GPU) needs more than the default minute
  // free placement: cards lie where the server keeps them, and a flick moves them there (the arranged boards: below)
  const { view } = await fourPlayerTable(page, 2, "dominaria", "free");
  // every player has a seat plate, and a life heart floating over their seat
  for (const pid of ["p1", "p2", "p3", "p4"]) {
    await expect(page.getByTestId(`seat-${pid}`)).toBeVisible();
    expect(await page.evaluate((p) => window.__fyodor3d!.heartAt(p), pid)).not.toBeNull();
  }

  // drag a card from the (2D) hand onto my 3D battlefield
  const hand = page.locator("main.table > .hand .hand-card");
  const id = (await hand.first().getAttribute("data-card-id"))!;
  const box = (await hand.first().boundingBox())!;
  const target = (await page.evaluate(() => window.__fyodor3d!.battlefieldAt("p1", 500, 250)))!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(target.x, target.y, { steps: 12 });
  await page.mouse.up();
  await expect.poll(async () => (await view()).cards[id]!.zone).toBe("p1:battlefield");

  // right-click the card on the 3D table → Tap
  await expect.poll(() => page.evaluate((cid) => window.__fyodor3d!.cardAt(cid), id)).not.toBeNull();
  await page.waitForTimeout(600); // let it settle where the server put it
  const at = (await page.evaluate((cid) => window.__fyodor3d!.cardAt(cid), id))!;
  await page.mouse.click(at.x, at.y, { button: "right" });
  await menuPath(page, "Tap");
  await expect.poll(async () => (await view()).cards[id]!.tapped).toBe(true);

  // the Oops heart: its ▲ half +1, its ▼ half −1, right-click 5 at a time, gathered into one change
  const life = async (pid: string) => ((await view()) as unknown as { players: { id: string; life: number }[] }).players.find((p) => p.id === pid)!.life;
  const up = (await page.evaluate(() => window.__fyodor3d!.heartAt("p2", 1)))!;
  const down = (await page.evaluate(() => window.__fyodor3d!.heartAt("p2", -1)))!;
  await page.mouse.click(up.x, up.y);
  await page.mouse.click(up.x, up.y);
  await page.mouse.click(down.x, down.y);
  await expect.poll(() => life("p2"), { timeout: 15_000 }).toBe(41);
  await page.mouse.click(down.x, down.y, { button: "right" });
  await expect.poll(() => life("p2"), { timeout: 15_000 }).toBe(36);

  // my seat's buttons are on the table by my mat: Draw draws one
  const handCount = async () => ((await view()) as unknown as { zones: Record<string, unknown> }).zones["p1:hand"] as string[];
  const handBefore = (await handCount()).length;
  const drawButton = (await page.evaluate(() => window.__fyodor3d!.buttonAt("draw")))!;
  await page.mouse.click(drawButton.x, drawButton.y);
  await expect.poll(async () => (await handCount()).length).toBe(handBefore + 1);

  // the commander tax counter beside my commander's slot: click +2
  const cmdKey = ((await view()) as unknown as { players: { id: string; commanders: { key: string; tax: number }[] }[] }).players.find((p) => p.id === "p1")!.commanders[0]!.key;
  const taxChip = (await page.evaluate((k) => window.__fyodor3d!.taxAt(k), cmdKey))!;
  await page.mouse.click(taxChip.x, taxChip.y);
  await expect.poll(async () => ((await view()) as unknown as { players: { id: string; commanders: { tax: number }[] }[] }).players.find((p) => p.id === "p1")!.commanders[0]!.tax).toBe(2);

  // the card importer, from the top bar, opens over the 3D table
  await page.getByTestId("open-importer").click();
  await expect(page.getByTestId("table-importer")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("table-importer")).toHaveCount(0);

  // a flick: one of my cards, let go while moving fast, slides on across my mat and the server keeps where it
  // stops (a real hand's pointer events are too far apart in this software-rendered browser, so the test throws
  // it through the same physics directly)
  const before = await view();
  const [left, right] = before.zones["p1:battlefield"]!.filter((cid) => cid !== id).sort((a, b) => (before.cards[a]!.x ?? 0) - (before.cards[b]!.x ?? 0));
  const rightX = before.cards[right!]!.x ?? 0;
  expect(await page.evaluate((cid) => window.__fyodor3d!.flick([cid], 9, 0), right!)).toBe(true);
  await expect.poll(async () => (await view()).cards[right!]!.x ?? 0).toBeGreaterThan(rightX + 200); // open felt: it slides a long way
  // and the left one, flicked harder across the felt, comes to rest well along too
  const leftX = before.cards[left!]!.x ?? 0;
  await page.waitForTimeout(500);
  expect(await page.evaluate((cid) => window.__fyodor3d!.flick([cid], 14, 0), left!)).toBe(true);
  await expect.poll(async () => (await view()).cards[left!]!.x ?? 0).toBeGreaterThan(leftX + 100);

  // camera presets
  await page.getByRole("toolbar", { name: "Camera" }).hover(); // the strip shows only the current view until hovered
  await page.getByRole("toolbar", { name: "Camera" }).getByRole("button", { name: "Table" }).click();
  await page.getByRole("toolbar", { name: "Camera" }).hover(); // the strip shows only the current view until hovered
  await page.getByRole("toolbar", { name: "Camera" }).getByRole("button", { name: "Seat" }).click();
});

test("3D table, arranged boards: every board in rows from my seat; dragging along my row or a flick reorders it on this screen only", async ({ page }) => {
  test.slow();
  const { act, view } = await fourPlayerTable(page, 0);
  await act({ type: "draw", player: "p1", count: 9 });
  await act({ type: "draw", player: "p4", count: 6 });
  const v0 = await view();
  const named = (pid: string, zone: string, name: string) => v0.zones[`${pid}:${zone}`]!.filter((id) => v0.cards[id]?.name === name);
  // my commander (a creature), two mana rocks and an Island; across the table (p4, Bob's deck) Krenko and a Mountain
  const atraxa = named("p1", "command", "Atraxa, Praetors' Voice")[0]!;
  const [ring, signet, island] = [named("p1", "hand", "Sol Ring")[0]!, named("p1", "hand", "Arcane Signet")[0]!, named("p1", "hand", "Island")[0]!];
  for (const cid of [atraxa, ring, signet, island]) await act({ type: "move", card_ids: [cid], to: { zone: "battlefield", player: "p1" } });
  const v4 = await view("p4");
  const krenko = v4.zones["p4:command"]![0]!;
  const mountain = v4.zones["p4:hand"]!.find((id) => v4.cards[id]?.name === "Mountain")!;
  for (const cid of [krenko, mountain]) await act({ type: "move", card_ids: [cid], to: { zone: "battlefield", player: "p4" } });
  const at = (cid: string) => page.evaluate((c) => window.__fyodor3d!.cardAt(c), cid);
  // settled in their rows (software WebGL draws a frame or two a second: wait out the cards' flights and glides)
  const settled = async () => {
    await expect.poll(async () => {
      if ((await page.evaluate(() => window.__fyodor3d!.motion?.().busy)) !== false) return false;
      const a = await Promise.all([atraxa, ring, signet, island, krenko, mountain].map(at));
      await page.waitForTimeout(500);
      const b = await Promise.all([atraxa, ring, signet, island, krenko, mountain].map(at));
      return a.every((p, i) => p && b[i] && Math.hypot(p.x - b[i]!.x, p.y - b[i]!.y) < 1);
    }, { timeout: 30_000 }).toBe(true);
  };
  await settled();
  // my creatures in front (toward the middle of the table: up the screen), my lands at my edge
  expect((await at(atraxa))!.y).toBeLessThan((await at(ring))!.y);
  expect((await at(ring))!.y).toBeLessThanOrEqual((await at(island))!.y + 1); // (a few rocks may share the land row, as on Arena)
  // a board across the table faces me: its creatures toward me (down the screen), its lands at the far edge
  expect((await at(krenko))!.y).toBeGreaterThan((await at(mountain))!.y);

  // drag Sol Ring past Arcane Signet along their row: my order changes, nothing is sent
  const order = async () => ((await at(ring))!.x < (await at(signet))!.x ? "ring-first" : "signet-first");
  const first = await order();
  const [a, b] = first === "ring-first" ? [ring, signet] : [signet, ring];
  const from = (await at(a))!;
  const past = (await at(b))!;
  const server = (await view()).cards[a]!;
  await page.mouse.move(from.x, from.y);
  await page.mouse.down();
  await page.mouse.move(past.x + 60, past.y, { steps: 10 });
  await page.waitForTimeout(400); // a slow, exact drop (no flick)
  await page.mouse.up();
  await expect.poll(order, { timeout: 15_000 }).not.toBe(first);
  await settled();
  const after = (await view()).cards[a]!;
  expect([after.x, after.y, after.zone]).toEqual([server.x, server.y, server.zone]);

  // a flick slides the card on across my mat (knocking the other aside), then both settle back into the row in the
  // order they came to rest in: still nothing sent
  const lead = (await order()) === "ring-first" ? ring : signet;
  const rowY = (await at(lead))!.y;
  const before = (await view()).cards[lead]!;
  expect(await page.evaluate((c) => window.__fyodor3d!.flick([c], 12, 0), lead)).toBe(true);
  await page.waitForTimeout(3000);
  await settled();
  expect(Math.abs((await at(lead))!.y - rowY)).toBeLessThan(6);
  const rest = (await view()).cards[lead]!;
  expect([rest.x, rest.y]).toEqual([before.x, before.y]);
});

test("3D table performance: a large Commander board stays within its draw-call budget", async ({ page }) => {
  await fourPlayerTable(page, 10);
  await page.waitForTimeout(2500);
  const stats = await page.evaluate(() => window.__fyodor3d!.stats());
  test.info().annotations.push({ type: "perf", description: JSON.stringify(stats) });
  console.log("3D perf", JSON.stringify(stats));
  // one draw call per card face plus a fixed environment; bodies are instanced
  expect(stats.cards).toBeGreaterThanOrEqual(40);
  expect(stats.calls).toBeLessThan(stats.cards + 140);
});
