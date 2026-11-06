import { expect, test, type Page } from "@playwright/test";

/**
 * Review frames for the crowded 2D table (playtest: "the card text is blocked by the turn clock", "overall crowded 2-D play
 * area"): four players under full automation, my board ~30 permanents of every type with token stacks, a hover preview
 * near the turn dial. Skipped unless SHOT_DIR is set; SHOT_PREFIX names the set ("before", "after").
 */
const OUT = process.env.SHOT_DIR ?? "";
const PREFIX = process.env.SHOT_PREFIX ?? "shot";
const LAYOUT = process.env.SHOT_LAYOUT ?? "arranged";
test.skip(!OUT, "set SHOT_DIR to capture screenshots");

const BUSY = `Commander
1x Krenko, Mob Boss
Deck
1x Grizzly Bears
1x Llanowar Elves
1x Soul Warden
1x Young Pyromancer
1x Merfolk Looter
1x Ambush Viper
1x Kitchen Finks
1x Mulldrifter
1x Banisher Priest
1x Frogmite
1x Perilous Myr
1x Sol Ring
1x Arcane Signet
1x Sol Grail
1x Liquimetal Coating
1x Stuffed Bear
1x Bonesplitter
1x Test Rest
1x Test Moat
1x Test Ward
1x Gideon Jura
1x God-Pharaoh's Statue
1x Command Tower
1x Shivan Reef
1x Breeding Pool
1x Gaea's Cradle
1x Cabal Coffers
6x Mountain
5x Forest
`;

const OTHER = `Commander
1x Atraxa, Praetors' Voice
Deck
1x Grizzly Bears
1x Llanowar Elves
1x Soul Warden
1x Sol Ring
1x Arcane Signet
1x Test Moat
1x Command Tower
10x Island
`;

type View = { seat_order: string[]; zones: Record<string, string[]>; cards: Record<string, { zone: string; name?: string }> };

async function setup(page: Page, mine: number) {
  await page.addInitScript((layout) => {
    localStorage.setItem("fyodor.renderer", "2d");
    localStorage.setItem("fyodor.welcomeDone", "1");
    localStorage.setItem("fyodor.tips.seen", JSON.stringify(["off"]));
    localStorage.setItem("fyodor.profiles", JSON.stringify({ version: 2, active: "t", profiles: [{ id: "t", name: "Alice", avatar: "A", prefs: { ambience: false, boardLayout: layout } }] }));
  }, LAYOUT);
  const ids: string[] = [];
  for (const text of [BUSY, OTHER]) {
    const r = await page.request.post("/api/decks", { data: { text } });
    expect(r.ok(), await r.text()).toBeTruthy();
    ids.push(((await r.json()) as { id: string }).id);
  }
  const res = await page.request.post("/api/games", {
    data: {
      name: "Shots", format: "commander", mode: "local", shuffle: false, first_player: 0, auto_untap: true, mulligan_rule: "none", automation: "full",
      players: ["Alice", "Bob", "Casey", "Jordan"].map((name, i) => ({ name, deck_id: ids[i === 0 ? 0 : 1]! })),
    },
  });
  expect(res.ok(), await res.text()).toBeTruthy();
  const gameId = ((await res.json()) as { game: { id: string } }).game.id;
  const act = async (action: Record<string, unknown>) => {
    const r = await page.request.post(`/api/games/${gameId}/actions`, { data: { action } });
    if (!r.ok()) console.log("action refused", JSON.stringify(action).slice(0, 120), (await r.text()).slice(0, 200));
  };
  const view = async (v = "p1") => (await (await page.request.get(`/api/games/${gameId}/view?viewer=${v}`)).json()) as View;
  const seats = (await view()).seat_order;
  for (const [s, pid] of seats.entries()) {
    const n = s === 0 ? mine : 9;
    await act({ type: "draw", player: pid, count: n + 6 });
    const hand = (await view(pid)).zones[`${pid}:hand`]!;
    for (const [i, cid] of hand.slice(0, n).entries()) await act({ type: "move", card_ids: [cid], to: { zone: "battlefield", player: pid }, x: 20 + (i % 10) * 95, y: 30 + Math.floor(i / 10) * 140 });
  }
  await act({ type: "create_token", player: "p1", token: { name: "Goblin", power: "1", toughness: "1", colors: ["R"], type_line: "Token Creature — Goblin" }, count: 7, stacked: true });
  await act({ type: "create_token", player: "p1", token: { name: "Treasure", type_line: "Token Artifact — Treasure", text: "{T}, Sacrifice this artifact: Add one mana of any color." }, count: 4, stacked: true });
  await act({ type: "create_token", player: "p1", token: { name: "Elemental", power: "1", toughness: "1", colors: ["R"], type_line: "Token Creature — Elemental" }, count: 2 });
  await act({ type: "create_token", player: "p2", token: { name: "Soldier", power: "1", toughness: "1", colors: ["W"], type_line: "Token Creature — Soldier" }, count: 5, stacked: true });
  return { gameId, act, view, seats };
}

for (const [w, h] of [[1366, 768], [1440, 900], [1920, 1080]] as const) {
  test(`busy 2D board at ${w}x${h}`, async ({ page }) => {
    test.setTimeout(240_000);
    await page.setViewportSize({ width: w, height: h });
    const { gameId } = await setup(page, 32);
    await page.goto(`/#/game/${gameId}`);
    await expect(page.locator('[data-drop="p1:battlefield"]')).toBeVisible({ timeout: 30_000 });
    const intro = page.getByTestId("game-intro");
    if (await intro.isVisible().catch(() => false)) await page.keyboard.press("Escape");
    await page.mouse.move(2, 400);
    await page.waitForTimeout(1500);
    await page.screenshot({ path: `${OUT}/${PREFIX}-${LAYOUT}-board-${w}x${h}.png` });
    // the right-most card of my board nearest the dial: its hover preview
    const dial = await page.locator(".turn-dial-wrap").boundingBox();
    const boxes = await page.locator('[data-drop="p1:battlefield"] [data-card-id]').evaluateAll((els) => els.map((e) => {
      const r = e.getBoundingClientRect();
      return { x: r.left + r.width / 2, y: r.top + r.height / 2, right: r.right, bottom: r.bottom };
    }));
    const target = boxes.sort((a, b) => b.right + b.bottom - (a.right + a.bottom))[0];
    if (target) {
      await page.mouse.move(target.x, target.y);
      await page.waitForTimeout(700);
      await page.screenshot({ path: `${OUT}/${PREFIX}-${LAYOUT}-hover-${w}x${h}.png` });
    }
    // overlap report: my cards the dial covers
    if (dial) {
      const hidden = boxes.filter((b) => b.right > dial.x && b.bottom > dial.y).length;
      console.log(`MEASURE ${w}x${h} dial=${JSON.stringify(dial)} cards=${boxes.length} underDial=${hidden}`);
    }
  });
}
