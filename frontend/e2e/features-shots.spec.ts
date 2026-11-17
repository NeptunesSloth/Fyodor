import { expect, test, type Page } from "@playwright/test";

/**
 * Review frames for the table features of November 2026: token piles (×N, spread), the combat filter, library search filters,
 * Undo back to here, saved rows, Planechase (2D plaque, 3D plane) and the Sandbox target dummy, plus the d4. Skipped unless SHOT_DIR
 * is set; point E2E_PORT at a server with the real card database (and the network, for card art).
 */
const OUT = process.env.SHOT_DIR ?? "";
test.skip(!OUT, "set SHOT_DIR to capture screenshots");
test.setTimeout(240_000);

const KRENKO = "Commander\n1 Krenko, Mob Boss\nDeck\n1 Sol Ring\n1 Arcane Signet\n1 Goblin Guide\n1 Goblin Matron\n1 Lightning Bolt\n1 Skirk Prospector\n"
  + "1 Goblin Chieftain\n1 Mogg War Marshal\n1 Shock\n1 Raging Goblin\n1 Goblin Bushwhacker\n1 Beetleback Chief\n1 Goblin Instigator\n"
  + "1 Goblin Lackey\n1 Goblin Warchief\n1 Legion Loyalist\n1 Siege-Gang Commander\n1 Impact Tremors\n1 Purphoros, God of the Forge\n35 Mountain";
const ATRAXA = "Commander\n1 Atraxa, Praetors' Voice\nDeck\n1 Sol Ring\n1 Llanowar Elves\n1 Grizzly Bears\n1 Savannah Lions\n1 Serra Angel\n"
  + "1 Swords to Plowshares\n1 Counterspell\n1 Wrath of God\n1 Rampant Growth\n1 Doubling Season\n10 Forest\n10 Plains\n10 Island\n10 Swamp";

async function prefs(page: Page, renderer: "2d" | "3d", extra: Record<string, unknown> = {}) {
  await page.addInitScript(([r, x]) => {
    localStorage.setItem("fyodor.renderer", r as string);
    localStorage.setItem("fyodor.welcomeDone", "1");
    localStorage.setItem("fyodor.coach3d", "done");
    localStorage.setItem("fyodor.tips.seen", JSON.stringify(["off"]));
    localStorage.setItem("fyodor.profiles", JSON.stringify({ version: 2, active: "t", profiles: [{ id: "t", name: "Alice", avatar: "A",
      prefs: { ambience: false, boardLayout: "free", ...(x as object) } }] }));
  }, [renderer, extra] as const);
}

async function deckIds(page: Page): Promise<string[]> {
  const ids: string[] = [];
  for (const text of [KRENKO, ATRAXA]) {
    const r = await page.request.post("/api/decks", { data: { text } });
    expect(r.ok(), await r.text()).toBeTruthy();
    ids.push(((await r.json()) as { id: string }).id);
  }
  return ids;
}

type View = { zones: Record<string, string[]>; cards: Record<string, { name?: string }> };

async function newGame(page: Page, body: Record<string, unknown> = {}) {
  const [a, b] = await deckIds(page);
  const res = await page.request.post("/api/games", {
    data: { name: "Review", format: "commander", mode: "local", shuffle: false, first_player: 0, mulligan_rule: "none",
      players: [{ name: "Alice", deck_id: a }, { name: "Bob", deck_id: b }], ...body },
  });
  expect(res.ok(), await res.text()).toBeTruthy();
  const id = ((await res.json()) as { game: { id: string } }).game.id;
  const act = async (action: Record<string, unknown>, as = "p1") => {
    const r = await page.request.post(`/api/games/${id}/actions`, { data: { action, as } });
    expect(r.ok(), await r.text()).toBeTruthy();
  };
  const view = async (p = "p1") => (await (await page.request.get(`/api/games/${id}/view?viewer=${p}`)).json()) as View;
  return { id, act, view };
}

async function open(page: Page, id: string, renderer: "2d" | "3d") {
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto(`/#/game/${id}`);
  if (renderer === "3d") await expect(page.getByTestId("table-3d")).toBeVisible({ timeout: 60_000 });
  await page.waitForTimeout(renderer === "3d" ? 6000 : 3000);
}

const shot = (page: Page, name: string) => page.screenshot({ path: `${OUT}/${name}.png` });

/** A board with permanents and a free pile of 30 Goblin tokens for each player. */
async function board(g: Awaited<ReturnType<typeof newGame>>) {
  for (const p of ["p1", "p2"]) {
    await g.act({ type: "draw", player: p, count: 14 }, p);
    const hand = (await g.view(p)).zones[`${p}:hand`]!;
    for (const [i, cid] of hand.slice(0, 6).entries()) await g.act({ type: "move", card_ids: [cid], to: { zone: "battlefield", player: p }, x: 60 + i * 120, y: i < 3 ? 210 : 420 }, p);
    await g.act({ type: "create_token", player: p, token: { name: "Goblin", power: "1", toughness: "1", colors: ["R"], type_line: "Token Creature — Goblin" },
      count: 30, stacked: false, x: 820, y: 230 }, p);
  }
}

for (const renderer of ["2d", "3d"] as const) {
  test(`piles and combat filter (${renderer})`, async ({ page }) => {
    await prefs(page, renderer);
    const g = await newGame(page);
    await board(g);
    await open(page, g.id, renderer);
    await shot(page, `${renderer}-01-token-pile`);
    await page.keyboard.press("b");
    await page.waitForTimeout(1500);
    await shot(page, `${renderer}-02-combat-filter-creatures`);
    await page.keyboard.press("b");
    await page.waitForTimeout(1500);
    await shot(page, `${renderer}-03-combat-filter-attack-block`);
  });

  test(`planechase (${renderer})`, async ({ page }) => {
    await prefs(page, renderer);
    const g = await newGame(page, { planechase: true, planar_deck_size: 10 });
    await board(g);
    await open(page, g.id, renderer);
    await page.waitForTimeout(6000); // the plane's art downloads on first sight
    await shot(page, `${renderer}-04-planechase`);
    await g.act({ type: "planar_roll" });
    await page.waitForTimeout(400);
    await shot(page, `${renderer}-05-planar-roll-mid`);
    await page.waitForTimeout(5000);
    await shot(page, `${renderer}-06-planar-roll-after`);
  });
}

test("spread pile (2d)", async ({ page }) => {
  await prefs(page, "2d");
  const g = await newGame(page);
  await board(g);
  await open(page, g.id, "2d");
  const tokens = Object.entries((await g.view()).cards).filter(([, c]) => c.name === "Goblin").map(([id]) => id);
  const mine = (await g.view()).zones["p1:battlefield"]!.filter((id) => tokens.includes(id));
  const top = mine[mine.length - 1]!;
  await page.locator(`[data-card-id="${top}"]`).first().click({ button: "right" });
  await page.waitForTimeout(500);
  await shot(page, "2d-07-pile-menu");
  await page.getByText(/Spread pile/).first().click();
  await page.waitForTimeout(2000);
  await shot(page, "2d-08-pile-spread");
});

test("library search filters (2d)", async ({ page }) => {
  await prefs(page, "2d");
  const g = await newGame(page);
  await open(page, g.id, "2d");
  await g.act({ type: "search_start", zone: { zone: "library", player: "p1" } });
  await page.waitForTimeout(3000);
  await shot(page, "2d-09-library-search");
  const chip = page.getByRole("button", { name: /^Creature/ }).first();
  if (await chip.count()) {
    await chip.click();
    await page.waitForTimeout(1500);
    await shot(page, "2d-10-library-search-creatures");
  }
});

test("undo back to here (2d)", async ({ page }) => {
  await prefs(page, "2d");
  const g = await newGame(page, { automation: "full" });
  for (let i = 0; i < 6; i++) await g.act({ type: "pass_priority" }).catch(() => undefined);
  await open(page, g.id, "2d");
  await page.keyboard.press("Escape");
  await page.getByTestId("table-menu").click();
  await page.getByText(/Snapshots & history/).first().click();
  await page.getByRole("button", { name: "History" }).click();
  await page.waitForTimeout(1500);
  await shot(page, "2d-11-history-steps");
});

test("target dummy (sandbox, 2d and play page)", async ({ page }) => {
  await prefs(page, "2d");
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto("/#/play");
  await page.getByTestId("format-sandbox").check();
  await page.getByTestId("add-dummy").click();
  await expect(page.getByTestId("dummy-seat")).toHaveCount(1);
  await page.waitForTimeout(800);
  await shot(page, "2d-12-play-sandbox-dummy");
  const [a] = await deckIds(page);
  const res = await page.request.post("/api/games", {
    data: { name: "Combo test", format: "sandbox", mode: "local", shuffle: false, first_player: 0, mulligan_rule: "none", players: [{ name: "Alice", deck_id: a }] },
  });
  const id = ((await res.json()) as { game: { id: string } }).game.id;
  const act = (action: Record<string, unknown>) => page.request.post(`/api/games/${id}/actions`, { data: { action, as: "p1" } });
  expect((await act({ type: "add_dummy", blocks: "chump" })).ok()).toBeTruthy();
  await act({ type: "life", player: "p2", delta: -17 });
  await open(page, id, "2d");
  await shot(page, "2d-13-target-dummy");
});

test("d4 numbers (3d)", async ({ page }) => {
  await prefs(page, "3d");
  const g = await newGame(page);
  await open(page, g.id, "3d");
  await g.act({ type: "roll", sides: 4, count: 4 });
  await page.waitForTimeout(7000);
  await shot(page, "3d-14-d4-dice");
});
