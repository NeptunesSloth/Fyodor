import { expect, test, type Page } from "@playwright/test";
import { ALICE_DECK, BOB_DECK, remoteDevice, saveDecks } from "./helpers";

/**
 * Frames for review of four table fixes: the 2D log drawer beside the turn dial, the turn dial of a player who is out, a
 * card leaving another player's hidden hand on the 3D table, and Deck Lab's compare view. Skipped unless SHOT_DIR is set;
 * SHOT_ONLY picks one; SHOT_BEFORE=1 takes the frames without the checks (for the before pictures).
 */
const OUT = process.env.SHOT_DIR ?? "";
const ONLY = process.env.SHOT_ONLY ?? "";
const BEFORE = !!process.env.SHOT_BEFORE;
test.skip(!OUT, "set SHOT_DIR to capture screenshots");



async function prefs(page: Page, renderer: "2d" | "3d") {
  await page.addInitScript((r) => {
    localStorage.setItem("fyodor.renderer", r);
    localStorage.setItem("fyodor.welcomeDone", "1");
    localStorage.setItem("fyodor.coach3d", "done");
    localStorage.setItem("fyodor.tips.seen", JSON.stringify(["off"]));
    localStorage.setItem("fyodor.profiles", JSON.stringify({ version: 2, active: "t", profiles: [{ id: "t", name: "Alice", avatar: "A", prefs: { ambience: false } }] }));
  }, renderer);
}

async function localGame(page: Page, players: string[], game: Record<string, unknown> = {}) {
  const decks = await saveDecks(page, [ALICE_DECK, BOB_DECK, BOB_DECK]);
  const res = await page.request.post("/api/games", {
    data: { name: "Gaps", mode: "local", shuffle: false, first_player: 0, mulligan_rule: "none", players: players.map((name, i) => ({ name, deck_id: decks[i % decks.length]!.id })), ...game },
  });
  expect(res.ok(), await res.text()).toBeTruthy();
  const gameId = ((await res.json()) as { game: { id: string } }).game.id;
  const act = async (as: string, action: Record<string, unknown>) => {
    const r = await page.request.post(`/api/games/${gameId}/actions`, { data: { action, as } });
    expect(r.ok(), await r.text()).toBeTruthy();
  };
  const hand = async (pid: string) => ((await (await page.request.get(`/api/games/${gameId}/view?viewer=${pid}`)).json()) as { zones: Record<string, string[]> }).zones[`${pid}:hand`]!;
  return { gameId, act, hand };
}

async function pastIntro(page: Page) {
  const intro = page.getByTestId("game-intro");
  if (await intro.isVisible().catch(() => false)) await page.keyboard.press("Escape");
  await expect(intro).toHaveCount(0);
}

type Box = { x: number; y: number; width: number; height: number };
const overlap = (a: Box, b: Box) => Math.max(0, Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x)) * Math.max(0, Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y));

for (const [w, h, automation] of [[1920, 1080, "full"], [1440, 900, "full"], [1440, 900, "off"]] as const) {
  test(`2D: the open log drawer beside the turn dial, ${w}x${h}, automation ${automation}`, async ({ page }) => {
    test.skip(!!ONLY && ONLY !== "drawer", "SHOT_ONLY");
    test.setTimeout(120_000);
    await prefs(page, "2d");
    const { gameId, act } = await localGame(page, ["Alice", "Bob", "Cara"], { automation });
    for (let i = 0; i < 14; i++) await act("p1", { type: "chat", text: `line ${i + 1}: the log has a few entries to show` });
    await page.setViewportSize({ width: w, height: h });
    await page.goto(`/#/game/${gameId}`);
    await expect(page.getByTestId("seat-p2")).toBeVisible();
    await pastIntro(page);
    await page.locator(".log-pill").click();
    await expect(page.locator(".log-drawer.open")).toBeVisible();
    await page.waitForTimeout(700);
    const name = `${BEFORE ? "before-" : ""}drawer-${w}x${h}-${automation}`;
    await page.screenshot({ path: `${OUT}/${name}.png` });
    const dial = (await page.locator(".turn-dial-wrap").boundingBox())!;
    const drawer = (await page.locator(".log-drawer.open").boundingBox())!;
    console.log(name, "dial", JSON.stringify(dial), "drawer", JSON.stringify(drawer), "overlap", overlap(dial, drawer));
    if (!BEFORE) {
      expect(overlap(dial, drawer)).toBe(0);
      expect(dial.x).toBeGreaterThanOrEqual(0); // still on screen
      // closed again: the dial goes back to its corner
      await page.locator(".log-close").click();
      await page.waitForTimeout(400);
      const back = (await page.locator(".turn-dial-wrap").boundingBox())!;
      expect(back.x + back.width).toBeGreaterThan(w - 40);
    }
  });
}

test("2D: the turn dial of a player who conceded", async ({ page }) => {
  test.skip(!!ONLY && ONLY !== "out", "SHOT_ONLY");
  test.setTimeout(120_000);
  await prefs(page, "2d");
  const { gameId, act } = await localGame(page, ["Alice", "Bob", "Cara"], { automation: "full" });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`/#/game/${gameId}`);
  await expect(page.getByTestId("seat-p2")).toBeVisible();
  await pastIntro(page);
  await act("p1", { type: "concede" });
  await expect(page.getByTestId("eliminated-scene").or(page.getByTestId("eliminated-hub"))).toBeVisible({ timeout: 10_000 });
  if (await page.getByTestId("eliminated-scene").isVisible().catch(() => false)) await page.getByTestId("eliminated-scene").click();
  await page.getByTestId("eliminated-hub").getByRole("button", { name: "Keep watching" }).click();
  await expect(page.getByTestId("priority-holder")).toHaveText(BEFORE ? /.+/ : "You're out: watching");
  await page.waitForTimeout(500);
  await page.screenshot({ path: `${OUT}/${BEFORE ? "before-" : ""}out-dial.png` });
  if (!BEFORE) {
    await expect(page.locator(".turn-dial").getByRole("button", { name: /Next turn|To combat|Previous step/ })).toHaveCount(0);
    // the server says no too, with a clear message, if a key press or an old tab still asks
    const res = await page.request.post(`/api/games/${gameId}/actions`, { data: { action: { type: "next_turn" }, as: "p1" } });
    expect(res.status()).toBe(409);
    expect(await res.text()).toContain("You're out of this game");
  }
});

// ------------------------------------------------------------------------- 3D: another player's hand

async function frames(page: Page) {
  await page.evaluate(() => new Promise<void>((done) => requestAnimationFrame(() => requestAnimationFrame(() => requestAnimationFrame(() => done())))));
}
async function freeze(page: Page, ms: number | null) {
  await page.evaluate((t) => window.__fyodor3d?.motionFreeze?.(t), ms);
}
async function shoot(page: Page, name: string) {
  await expect.poll(() => page.evaluate(() => window.__fyodor3d?.motion?.().busy ?? true), { timeout: 15_000 }).toBe(true);
  await frames(page);
  await page.screenshot({ path: `${OUT}/${BEFORE ? "before-" : ""}${name}.png` });
}
async function settle(page: Page) {
  await freeze(page, null);
  await expect.poll(() => page.evaluate(() => window.__fyodor3d?.motion?.().busy ?? false), { timeout: 15_000 }).toBe(false);
  await frames(page);
}

for (const players of [["Alice", "Bob"], ["Alice", "Bob", "Cara", "Dana"]]) {
  test(`3D: a cast and a draw from another player's hand, ${players.length} players`, async ({ page }) => {
    test.skip(!!ONLY && ONLY !== "cast3d", "SHOT_ONLY");
    test.setTimeout(400_000);
    await prefs(page, "3d");
    const { gameId, act, hand } = await localGame(page, players);
    for (const pid of players.map((_, i) => `p${i + 1}`)) await act(pid, { type: "draw", player: pid, count: 6 });
    await page.setViewportSize({ width: 1600, height: 900 });
    await page.goto(`/#/game/${gameId}`);
    await expect(page.getByTestId("table-3d")).toBeVisible({ timeout: 60_000 });
    await expect.poll(() => page.evaluate(() => window.__fyodor3d?.stats().cards ?? 0), { timeout: 60_000 }).toBeGreaterThanOrEqual(players.length);
    await pastIntro(page);
    await page.waitForTimeout(2500);
    const n = players.length;
    // across the table (p2 at two players, p3 at four) and, at four, the neighbour in my row (p2)
    for (const pid of n === 2 ? ["p2"] : ["p3", "p2"]) {
      for (const at of [30, 120]) {
        await freeze(page, at);
        await act(pid, { type: "move", card_ids: [(await hand(pid))[0]], to: { zone: "stack" } });
        await shoot(page, `cast3d-${n}p-${pid}-${at}ms`);
        await settle(page);
        const view = (await (await page.request.get(`/api/games/${gameId}/view?viewer=p1`)).json()) as { stack: string[] };
        await act(pid, { type: "move", card_ids: [view.stack[view.stack.length - 1]], to: { zone: "graveyard", player: pid } });
        await settle(page);
      }
      await freeze(page, 150);
      await act(pid, { type: "draw", player: pid, count: 2 });
      await shoot(page, `draw3d-${n}p-${pid}-150ms`);
      await settle(page);
    }
  });
}

// ------------------------------------------------------------------------- Deck Lab: compare

async function toDeckLab(page: Page) {
  await expect(page.getByTestId("eliminated-scene").or(page.getByTestId("eliminated-hub"))).toBeVisible({ timeout: 15_000 });
  if (await page.getByTestId("eliminated-scene").isVisible().catch(() => false)) await page.getByTestId("eliminated-scene").click();
  await page.getByTestId("eliminated-hub").getByTestId("open-deck-lab").click();
}

test("Deck Lab compare on a guest's computer: the edited list against the deck brought", async ({ page, browser }) => {
  test.skip(!!ONLY && ONLY !== "decklab", "SHOT_ONLY");
  test.setTimeout(150_000);
  const decks = await saveDecks(page, [ALICE_DECK, BOB_DECK, BOB_DECK]);
  const res = await page.request.post("/api/games", { data: { name: "Lab", mode: "lan", automation: "full", mulligan_rule: "none",
    players: ["Alice", "Bob", "Cara"].map((name, i) => ({ name, deck_id: decks[i]!.id })) } });
  expect(res.ok(), await res.text()).toBeTruthy();
  const { game } = (await res.json()) as { game: { id: string; code: string } };
  const context = await browser.newContext(remoteDevice());
  const guest = await context.newPage();
  const token = ((await (await guest.request.post("/api/join", { data: { code: game.code } })).json()) as { token: string }).token;
  await prefs(guest, "2d");
  await guest.addInitScript(([id, t]) => localStorage.setItem(`fyodor.seat.${id}`, t), [game.id, token] as const);
  await guest.setViewportSize({ width: 1440, height: 900 });
  await guest.goto(`/#/game/${game.id}`);
  await expect(guest.locator(".game-screen")).toBeVisible();
  await pastIntro(guest);
  const conceded = await guest.request.post(`/api/games/${game.id}/actions`, { data: { action: { type: "concede" } }, headers: { "X-Seat-Token": token } });
  expect(conceded.ok(), await conceded.text()).toBeTruthy();
  await toDeckLab(guest);
  const list = guest.getByRole("textbox", { name: "Deck list" });
  await expect(list).toHaveValue(/Krenko, Mob Boss/);
  const text = await list.inputValue();
  await list.fill(text.replace(/1 Pyroblast[^\n]*\n/, "1 Goblin Bombardment\n1 Skullclamp\n").replace(/14 Mountain/, "13 Mountain"));
  await guest.getByTestId("deck-lab-compare").click();
  const cmp = guest.getByTestId("deck-compare");
  await expect(cmp).toContainText("Goblin Bombardment");
  await expect(cmp).toContainText("Pyroblast");
  await expect(cmp).toContainText("18 cards");
  await guest.waitForTimeout(400);
  await guest.screenshot({ path: `${OUT}/decklab-compare-guest.png` });
  // back to the list, closed and reopened: the same list comes back (this tab keeps it)
  await guest.getByTestId("deck-lab-compare").click();
  await guest.keyboard.press("Escape");
  await guest.getByTestId("eliminated-pill").click();
  await guest.getByTestId("eliminated-hub").getByTestId("open-deck-lab").click();
  await expect(guest.getByRole("textbox", { name: "Deck list" })).toHaveValue(/Skullclamp/);
  await context.close();
});

test("Deck Lab compare on the host computer: the library copy as the deck editor saved it", async ({ page }) => {
  test.skip(!!ONLY && ONLY !== "decklab", "SHOT_ONLY");
  test.setTimeout(150_000);
  await prefs(page, "2d");
  const { gameId, act } = await localGame(page, ["Alice", "Bob", "Cara"], { automation: "full" });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`/#/game/${gameId}`);
  await expect(page.getByTestId("seat-p2")).toBeVisible();
  await pastIntro(page);
  await act("p1", { type: "concede" });
  await toDeckLab(page);
  const link = page.getByTestId("deck-lab-editor");
  await expect(link).toBeVisible();
  const deckId = decodeURIComponent((await link.getAttribute("href"))!.replace("#/decks/", ""));
  // edited in the deck editor (another tab): one Opt out, two Counterspells in
  const deck = (await (await page.request.get(`/api/decks/${deckId}`)).json()) as { name: string; format: string; notes: string; entries: { name: string; quantity: number }[] };
  const entries = deck.entries.filter((e) => e.name !== "Opt").map((e) => (e.name === "Counterspell" ? { ...e, quantity: 3 } : e));
  const put = await page.request.put(`/api/decks/${deckId}`, { data: { name: deck.name, format: deck.format, notes: deck.notes, entries } });
  expect(put.ok(), await put.text()).toBeTruthy();
  await page.getByTestId("deck-lab-compare").click();
  const cmp = page.getByTestId("deck-compare");
  await expect(cmp).toContainText("Counterspell");
  await expect(cmp).toContainText("Opt");
  await page.waitForTimeout(400);
  await page.screenshot({ path: `${OUT}/decklab-compare-host.png` });
  // reopened: the same library copy, not a new one
  await page.keyboard.press("Escape");
  await page.getByTestId("eliminated-pill").click();
  await page.getByTestId("eliminated-hub").getByTestId("open-deck-lab").click();
  await expect(page.getByTestId("deck-lab-editor")).toHaveAttribute("href", `#/decks/${encodeURIComponent(deckId)}`);
});
