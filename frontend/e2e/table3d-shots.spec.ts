import { expect, test, type Page } from "@playwright/test";
import { ALICE_DECK, BOB_DECK } from "./helpers";

/**
 * Screenshots and perf numbers for the 3D table overhaul (UI_REDESIGN_BRIEF "Visual testing").
 * Skipped unless SHOT_DIR is set: `SHOT_DIR=/some/dir npx playwright test e2e/table3d-shots.spec.ts`.
 * Each phase is compared against the same boards; nothing here is asserted beyond "it rendered".
 */
const OUT = process.env.SHOT_DIR ?? "";
const PREFIX = process.env.SHOT_PREFIX ?? "shot";
test.skip(!OUT, "set SHOT_DIR to capture 3D table screenshots");

type View = { seat_order: string[]; zones: Record<string, string[]>; cards: Record<string, { zone: string }> };

async function board(page: Page, perSeat: number, extras: boolean) {
  await page.addInitScript(() => {
    localStorage.setItem("fyodor.renderer", "3d");
    localStorage.setItem("fyodor.welcomeDone", "1");
    localStorage.setItem("fyodor.profiles", JSON.stringify({ version: 2, active: "t", profiles: [{ id: "t", name: "Alice", avatar: "A", prefs: { ambience: false } }] }));
  });
  for (const text of [ALICE_DECK, BOB_DECK]) await page.request.post("/api/decks", { data: { text } });
  const decks = (await (await page.request.get("/api/decks")).json()) as { id: string }[];
  const res = await page.request.post("/api/games", {
    data: {
      name: "Shots", format: "commander", mode: "local", shuffle: false, first_player: 0, auto_untap: true, mulligan_rule: "none",
      players: ["Alice", "Bob", "Casey", "Jordan"].map((name, i) => ({ name, deck_id: decks[i % decks.length]!.id })),
    },
  });
  const gameId = ((await res.json()) as { game: { id: string } }).game.id;
  const act = async (action: Record<string, unknown>) => {
    const r = await page.request.post(`/api/games/${gameId}/actions`, { data: { action } });
    if (!r.ok()) console.log("action refused", JSON.stringify(action).slice(0, 120), (await r.text()).slice(0, 200));
  };
  const view = async (v = "p1") => (await (await page.request.get(`/api/games/${gameId}/view?viewer=${v}`)).json()) as View;
  const seats = (await view()).seat_order;
  // the fixture decks hold ~20 cards: real cards first, then individual tokens to reach perSeat
  const real = Math.min(perSeat, 10);
  for (const pid of seats) await act({ type: "draw", player: pid, count: real + 5 });
  const placed: Record<string, string[]> = {};
  const at = (i: number) => ({ x: 20 + (i % 10) * 95, y: 30 + Math.floor(i / 10) * 140 });
  for (const pid of seats) {
    const ids = (await view(pid)).zones[`${pid}:hand`]!.slice(0, real);
    placed[pid] = ids;
    for (const [i, cid] of ids.entries()) await act({ type: "move", card_ids: [cid], to: { zone: "battlefield", player: pid }, ...at(i) });
    for (let i = real; i < perSeat; i++) await act({ type: "create_token", player: pid, token: { name: `Thopter ${i}`, power: "1", toughness: "1", colors: ["U"], type_line: "Token Artifact Creature — Thopter" }, count: 1, stacked: false, ...at(i) });
  }
  if (extras) {
    const [a, b, c] = [placed.p1!, placed.p2!, placed.p3!];
    await act({ type: "tap", card_ids: [a[0], b[0], c[0]], tapped: true });
    await act({ type: "counter", card_ids: [a[1]], kind: "+1/+1", delta: 3 });
    // a Kathril-style creature: several keyword counters (one stacked) plus +1/+1 counters
    for (const kind of ["flying", "first strike", "deathtouch", "lifelink", "trample"]) await act({ type: "counter", card_ids: [a[2]], kind, delta: kind === "flying" ? 2 : 1 });
    await act({ type: "counter", card_ids: [a[2]], kind: "+1/+1", delta: 2 });
    await act({ type: "set_damage", card_ids: [a[3]], value: 2 });
    await act({ type: "create_token", player: "p1", token: { name: "Soldier", power: "1", toughness: "1", colors: ["W"], type_line: "Token Creature — Soldier" }, count: 6, x: 40, y: 330 });
    await act({ type: "set_controller", card_ids: [b[2]], player: "p1" }); // a stolen permanent
    await act({ type: "attack", card_ids: [c[3], c[4]], target: { kind: "player", id: "p1" } });
    for (const pid of seats) await act({ type: "move", card_ids: [(await view(pid)).zones[`${pid}:hand`]![0]], to: { zone: "graveyard", player: pid } });
    const hand = (await view("p1")).zones["p1:hand"]!;
    await act({ type: "move", card_ids: [hand[0]], to: { zone: "stack" } });
    await act({ type: "move", card_ids: [hand[1]], to: { zone: "stack" } });
    await act({ type: "draw", player: "p1", count: 5 }); // a full hand for the fan
    // a spell on the stack targeting one of my creatures: its beam must leave the standing card from its top
    await act({ type: "create_arrow", source: hand[1], targets: [a[4]], kind: "target" });
  }
  await page.goto(`/#/game/${gameId}`);
  await expect(page.getByTestId("table-3d")).toBeVisible();
  await expect.poll(() => page.evaluate(() => window.__fyodor3d?.stats().cards ?? 0), { timeout: 30_000 }).toBeGreaterThanOrEqual(perSeat * 4);
  await page.waitForTimeout(2500);
  return { gameId, act, view };
}

async function shoot(page: Page, name: string) {
  await page.screenshot({ path: `${OUT}/${PREFIX}-${name}.png` });
}

async function camera(page: Page, name: "Seat" | "Table") {
  await page.getByRole("toolbar", { name: "Camera" }).getByRole("button", { name }).click();
  await page.waitForTimeout(2000);
}

for (const [w, h, tag] of [[1920, 1080, "1080p"], [2560, 1440, "1440p"], [1366, 768, "laptop"]] as const) {
  test(`3D shots ${tag}: four-player board`, async ({ page }) => {
    test.setTimeout(240_000);
    await page.setViewportSize({ width: w, height: h });
    await board(page, 7, true);
    await shoot(page, `${tag}-seat`);
    await camera(page, "Table");
    await shoot(page, `${tag}-table`);
    if (tag === "1080p") {
      await camera(page, "Seat");
      // the hand with a card hovered
      const handCard = page.locator("main.table > .hand .hand-card").nth(1);
      if (await handCard.count()) await handCard.hover();
      await page.waitForTimeout(500);
      await shoot(page, `${tag}-hand-hover`);
    }
  });
}

for (const perSeat of [25, 75]) {
  test(`3D perf: ${perSeat * 4} permanents`, async ({ page }) => {
    test.setTimeout(400_000);
    await page.setViewportSize({ width: 1920, height: 1080 });
    await board(page, perSeat, false);
    await page.waitForTimeout(3000);
    const stats = await page.evaluate(() => window.__fyodor3d!.stats());
    console.log(`3D perf ${perSeat * 4}`, JSON.stringify(stats));
    await shoot(page, `perf-${perSeat * 4}-seat`);
    await camera(page, "Table");
    await shoot(page, `perf-${perSeat * 4}-table`);
  });
}

test("3D shots: rules engine on, the turn dial with my priority", async ({ page }) => {
  test.setTimeout(240_000);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.addInitScript(() => {
    localStorage.setItem("fyodor.renderer", "3d");
    localStorage.setItem("fyodor.welcomeDone", "1");
    localStorage.setItem("fyodor.profiles", JSON.stringify({ version: 2, active: "t", profiles: [{ id: "t", name: "Alice", avatar: "A", prefs: { ambience: false } }] }));
  });
  for (const text of [ALICE_DECK, BOB_DECK]) await page.request.post("/api/decks", { data: { text } });
  const decks = (await (await page.request.get("/api/decks")).json()) as { id: string }[];
  const res = await page.request.post("/api/games", {
    data: {
      name: "Rules", format: "commander", mode: "local", shuffle: false, first_player: 0, auto_untap: true, mulligan_rule: "none", automation: "full",
      players: ["Alice", "Bob", "Casey", "Jordan"].map((name, i) => ({ name, deck_id: decks[i % decks.length]!.id })),
    },
  });
  const gameId = ((await res.json()) as { game: { id: string } }).game.id;
  await page.goto(`/#/game/${gameId}`);
  await expect(page.getByTestId("table-3d")).toBeVisible();
  const phase = async () => ((await (await page.request.get(`/api/games/${gameId}/view`)).json()) as { turn: { phase: string } }).turn.phase;
  for (let i = 0; i < 6 && (await phase()) !== "main1"; i++) {
    await page.getByTestId("priority-bar").getByRole("button", { name: /^(Pass|Next)/ }).first().click();
    await page.waitForTimeout(400);
  }
  await page.waitForTimeout(2500);
  await shoot(page, "dial-mine");
});
