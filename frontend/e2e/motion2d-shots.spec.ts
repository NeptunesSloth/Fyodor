import { expect, test, type Page } from "@playwright/test";
import { saveDecks } from "./helpers";

/**
 * Frames of the 2D table's motion for review (game/motion/Motion2D.tsx): cards flying between zones, a draw, a mill, a shuffle, an
 * attack and a block, damage and life numbers. Skipped unless SHOT_DIR is set:
 * `SHOT_DIR=/some/dir npx playwright test e2e/motion2d-shots.spec.ts`.
 * Each flight is frozen at a set time (window.__fyodorMotion2d.freeze): wall-clock timing can't pin a frame.
 */
const OUT = process.env.SHOT_DIR ?? "";
test.skip(!OUT, "set SHOT_DIR to capture motion screenshots");

type View = { cards: Record<string, { id: string; zone: string; name?: string; hidden?: boolean }>; zones: Record<string, unknown> };

async function table(page: Page, prefs: Record<string, unknown> = {}) {
  await page.addInitScript((extra) => {
    localStorage.setItem("fyodor.renderer", "2d");
    localStorage.setItem("fyodor.welcomeDone", "1");
    localStorage.setItem("fyodor.tips.seen", JSON.stringify(["off"]));
    localStorage.setItem("fyodor.profiles", JSON.stringify({ version: 2, active: "t", profiles: [{ id: "t", name: "Alice", avatar: "A", prefs: { ambience: false, ...extra } }] }));
  }, prefs);
  const decks = await saveDecks(page);
  const res = await page.request.post("/api/games", {
    data: { name: "Motion", mode: "local", shuffle: false, first_player: 0, mulligan_rule: "none", players: ["Alice", "Bob"].map((name, i) => ({ name, deck_id: decks[i]!.id })) },
  });
  const gameId = ((await res.json()) as { game: { id: string } }).game.id;
  await page.setViewportSize({ width: 1600, height: 900 });
  await page.goto(`/#/game/${gameId}`);
  await expect(page.getByTestId("seat-p2")).toBeVisible();
  await page.waitForTimeout(800);
  const act = async (as: string, action: Record<string, unknown>) => {
    const r = await page.request.post(`/api/games/${gameId}/actions`, { data: { action, as } });
    expect(r.ok(), await r.text()).toBeTruthy();
  };
  const view = async (viewer = "p1"): Promise<View> => (await (await page.request.get(`/api/games/${gameId}/view?viewer=${viewer}`)).json()) as View;
  return { gameId, act, view };
}

const inZone = (v: View, zone: string, name?: string) => Object.values(v.cards).filter((c) => c.zone === zone && (!name || c.name === name)).map((c) => c.id);

/** Hold every animation at ``ms`` (the next ones too) and capture a frame. */
type Clip = { x: number; y: number; width: number; height: number };

async function frame(page: Page, name: string, ms: number, clip?: Clip) {
  await page.evaluate((t) => window.__fyodorMotion2d!.freeze(t), ms);
  await page.evaluate(() => new Promise<void>((done) => requestAnimationFrame(() => requestAnimationFrame(() => done()))));
  await page.screenshot({ path: `${OUT}/${name}-${ms}.png` });
  if (clip) await page.screenshot({ path: `${OUT}/${name}-${ms}-close.png`, clip });
}

/** Wait until no motion is playing (headless software rendering draws only a few frames a second). */
async function still(page: Page) {
  await page.waitForTimeout(300);
  await page.evaluate(() => new Promise<void>((done) => requestAnimationFrame(() => requestAnimationFrame(() => done()))));
  await expect.poll(() => page.evaluate(() => window.__fyodorMotion2d!.running()), { timeout: 20_000 }).toBe(0);
}

/** Run an action with the motion held at its first frame, wait for the motion to start, then capture it at each time. */
async function shoot(page: Page, name: string, times: number[], run: () => Promise<void>, clip?: Clip) {
  await page.evaluate((t) => window.__fyodorMotion2d!.freeze(t), times[0]!);
  await run();
  await expect.poll(() => page.evaluate(() => window.__fyodorMotion2d!.running()), { timeout: 10_000 }).toBeGreaterThan(0);
  for (const t of times) await frame(page, name, t, clip);
  await page.evaluate(() => window.__fyodorMotion2d!.freeze(null));
  await expect.poll(() => page.evaluate(() => window.__fyodorMotion2d!.running()), { timeout: 10_000 }).toBe(0);
  await page.waitForTimeout(300);
  // nothing is left hidden once the motion ends
  expect(await page.evaluate(() => [...document.querySelectorAll<HTMLElement>("[data-card-id], .pile-card, .chain-thumb, .seat-heart-n")].filter((e) => e.style.opacity === "0").length)).toBe(0);
}

test("2D table motion: casts, draws, mills, a shuffle, combat and life", async ({ page }) => {
  test.setTimeout(240_000);
  const { act, view } = await table(page);
  await act("p1", { type: "draw", player: "p1", count: 7 });
  await act("p2", { type: "draw", player: "p2", count: 7 });
  const atraxa = inZone(await view("p1"), "p1:command")[0]!;
  const krenko = inZone(await view("p2"), "p2:command")[0]!;
  await act("p1", { type: "move", card_ids: [atraxa], to: { zone: "battlefield", player: "p1" }, x: 520, y: 140 });
  await act("p2", { type: "move", card_ids: [krenko], to: { zone: "battlefield", player: "p2" }, x: 520, y: 140 });
  await still(page);
  await page.screenshot({ path: `${OUT}/00-board.png` });

  // my cast: from my hand onto my battlefield, face up all the way
  const ring = inZone(await view("p1"), "p1:hand", "Sol Ring")[0]!;
  await shoot(page, "01-cast", [30, 90, 180], () => act("p1", { type: "move", card_ids: [ring], to: { zone: "battlefield", player: "p1" }, x: 640, y: 160 }));

  // Bob's cast from his hidden hand: a card back from his hand, face up as it lands on the stack
  const bolt = inZone(await view("p2"), "p2:hand", "Lightning Bolt")[0]!;
  await shoot(page, "02-their-cast", [80, 200], () => act("p2", { type: "move", card_ids: [bolt], to: { zone: "stack", player: null } }));
  await shoot(page, "03-resolve", [120], () => act("p2", { type: "move", card_ids: [bolt], to: { zone: "graveyard", player: "p2" } }));

  // draws: mine turns face up in my hand; Bob's are card backs into his hand
  await shoot(page, "04-draw", [40, 100, 220], () => act("p1", { type: "draw", player: "p1", count: 1 }));
  await shoot(page, "05-their-draw", [120], () => act("p2", { type: "draw", player: "p2", count: 2 }));

  // a mill: staggered, face up as they land in the graveyard
  await shoot(page, "06-mill", [60, 120, 220], () => act("p2", { type: "mill", player: "p2", count: 3 }), { x: 230, y: 60, width: 340, height: 120 });

  // a bounce to Bob's hidden hand: flies there and turns face down
  const mountain = inZone(await view("p2"), "p2:hand", "Mountain")[0]!;
  await act("p2", { type: "move", card_ids: [mountain], to: { zone: "battlefield", player: "p2" }, x: 260, y: 160 });
  await still(page);
  await shoot(page, "07-bounce", [150], () => act("p1", { type: "move", card_ids: [mountain], to: { zone: "hand", player: "p2" } }));

  // a shuffle: a riffle on the library
  await shoot(page, "08-shuffle", [120, 260], () => act("p1", { type: "shuffle", player: "p1" }), { x: 0, y: 520, width: 240, height: 140 });

  // combat: the attacker steps toward Bob, the blocker toward it; damage and life numbers
  await shoot(page, "09-attack", [110], () => act("p1", { type: "attack", card_ids: [atraxa], target: { kind: "player", id: "p2" } }));
  await shoot(page, "10-block", [110], () => act("p2", { type: "block", card_id: krenko, attacker_id: atraxa }));
  await shoot(page, "11-damage", [250], () => act("p1", { type: "set_damage", card_ids: [krenko], delta: 3 }));
  await shoot(page, "12-life", [150, 380], async () => {
    await act("p1", { type: "life", player: "p2", delta: -5 });
    await act("p1", { type: "life", player: "p1", delta: 3 });
  });
});

test("reduced motion: flights shortened, no lunge, numbers kept", async ({ page }) => {
  test.setTimeout(120_000);
  const { act, view } = await table(page, { reducedMotion: true });
  await act("p1", { type: "draw", player: "p1", count: 7 });
  const atraxa = inZone(await view("p1"), "p1:command")[0]!;
  await act("p1", { type: "move", card_ids: [atraxa], to: { zone: "battlefield", player: "p1" }, x: 520, y: 140 });
  await still(page);
  await shoot(page, "20-reduced-draw", [40, 100], () => act("p1", { type: "draw", player: "p1", count: 1 }));
  // no lunge with reduced motion: the attacker never leaves its place
  await page.evaluate(() => window.__fyodorMotion2d!.freeze(0));
  await act("p1", { type: "attack", card_ids: [atraxa], target: { kind: "player", id: "p2" } });
  await page.waitForTimeout(400);
  expect(await page.evaluate((id) => document.querySelector(`.battlefield [data-card-id="${id}"]`)!.getAnimations().length, atraxa)).toBe(0);
  await page.evaluate(() => window.__fyodorMotion2d!.freeze(null));
  await shoot(page, "21-reduced-life", [300], () => act("p1", { type: "life", player: "p2", delta: -4 }));
});

test("baseline: the 2D table before any motion", async ({ page }) => {
  test.setTimeout(120_000);
  const { act, view } = await table(page);
  await act("p1", { type: "draw", player: "p1", count: 7 });
  await act("p2", { type: "draw", player: "p2", count: 7 });
  const v = await view("p2");
  const mountain = inZone(v, "p2:hand", "Mountain")[0]!;
  await act("p2", { type: "move", card_ids: [mountain], to: { zone: "battlefield", player: "p2" }, x: 300, y: 200 });
  const a = await view("p1");
  const island = inZone(a, "p1:hand", "Island")[0]!;
  await act("p1", { type: "move", card_ids: [island], to: { zone: "battlefield", player: "p1" }, x: 300, y: 200 });
  await still(page);
  await page.screenshot({ path: `${OUT}/baseline.png` });
});
