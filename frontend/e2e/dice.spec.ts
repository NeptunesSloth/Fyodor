import { expect, test, type Page } from "@playwright/test";
import * as zlib from "node:zlib";
import { saveDecks } from "./helpers";

/**
 * Dice you can see (game/dice.ts): a roll is thrown and lands on the roller's mat for everyone, showing the server's
 * numbers, on the 3D table, the 2D table's 3D overlay and the drawn dice without WebGL; the roll panel sends rolls.
 * Throws are frozen at rest (window.__fyodorDice.freeze) so the checks don't depend on software WebGL's frame rate.
 */

/** RGB(A) pixels of a PNG screenshot (8-bit, not interlaced: what Chromium writes). */
function pixels(png: Buffer): { w: number; h: number; ch: number; data: Uint8Array } {
  let p = 8;
  let w = 0, h = 0, ch = 4;
  const idat: Buffer[] = [];
  while (p < png.length) {
    const len = png.readUInt32BE(p);
    const type = png.toString("ascii", p + 4, p + 8);
    const body = png.subarray(p + 8, p + 8 + len);
    if (type === "IHDR") {
      w = body.readUInt32BE(0);
      h = body.readUInt32BE(4);
      ch = body[9] === 6 ? 4 : 3;
    } else if (type === "IDAT") idat.push(body);
    p += 12 + len;
  }
  const raw = zlib.inflateSync(Buffer.concat(idat));
  const data = new Uint8Array(w * h * ch);
  const stride = w * ch;
  for (let y = 0; y < h; y++) {
    const f = raw[y * (stride + 1)]!;
    for (let x = 0; x < stride; x++) {
      const v = raw[y * (stride + 1) + 1 + x]!;
      const a = x >= ch ? data[y * stride + x - ch]! : 0;
      const b = y ? data[(y - 1) * stride + x]! : 0;
      const c = x >= ch && y ? data[(y - 1) * stride + x - ch]! : 0;
      const pa = Math.abs(b - c), pb = Math.abs(a - c), pc = Math.abs(a + b - 2 * c);
      const pred = f === 1 ? a : f === 2 ? b : f === 3 ? (a + b) >> 1 : f === 4 ? (pa <= pb && pa <= pc ? a : pb <= pc ? b : c) : 0;
      data[y * stride + x] = (v + pred) & 255;
    }
  }
  return { w, h, ch, data };
}

/** Mean per-channel difference between two screenshots of the same region. */
function difference(a: Buffer, b: Buffer): number {
  const pa = pixels(a), pb = pixels(b);
  let sum = 0, n = 0;
  for (let i = 0; i < pa.w * pa.h; i++) {
    for (let c = 0; c < 3; c++) sum += Math.abs(pa.data[i * pa.ch + c]! - pb.data[i * pb.ch + c]!);
    n += 3;
  }
  return sum / n;
}

async function newGame(page: Page, renderer: "3d" | null) {
  await page.addInitScript((r) => {
    if (r) localStorage.setItem("fyodor.renderer", r);
    localStorage.setItem("fyodor.coach3d", "done");
    localStorage.setItem("fyodor.tips.seen", JSON.stringify(["off"]));
  }, renderer);
  const decks = await saveDecks(page);
  const res = await page.request.post("/api/games", {
    data: {
      name: "Dice", mode: "local", shuffle: false, first_player: 0, mulligan_rule: "none",
      players: [{ name: "Alice", deck_id: decks[0]!.id }, { name: "Bob", deck_id: decks[1]!.id }],
    },
  });
  const gameId = ((await res.json()) as { game: { id: string } }).game.id;
  await page.goto(`/#/game/${gameId}`);
  const act = async (action: Record<string, unknown>, as?: string) => {
    expect((await page.request.post(`/api/games/${gameId}/actions`, { data: as ? { action, as } : { action } })).ok()).toBeTruthy();
  };
  const lastRoll = async () => {
    const view = (await (await page.request.get(`/api/games/${gameId}/view?viewer=p1`)).json()) as { log: { roll?: { sides: number; results: number[]; coin: boolean } }[] };
    return view.log.filter((e) => e.roll).at(-1)!.roll!;
  };
  return { act, lastRoll };
}

/** Let the page draw a few frames (seconds each in software WebGL). */
const frames = (page: Page) => page.evaluate(() => new Promise<void>((done) => requestAnimationFrame(() => requestAnimationFrame(() => requestAnimationFrame(() => done())))));
const rolled = (r: { sides: number; results: number[] }) => `${r.results.length}d${r.sides}`;

test("2D table: a roll lands on the roller's mat as 3D dice, with the server's numbers, and stays until cleared", async ({ page }) => {
  test.setTimeout(120_000);
  const { act, lastRoll } = await newGame(page, null);
  await expect(page.getByTestId("seat-p2")).toBeVisible();
  // rolls already in the log when the table opens aren't replayed; a new one is
  await expect(page.getByTestId("dice-line")).toHaveCount(0);
  await page.evaluate(() => window.__fyodorDice!.freeze(6000)); // every throw shown at rest
  const mat = (await page.locator('[data-drop="p2:battlefield"]').boundingBox())!;
  const clip = { x: mat.x, y: mat.y, width: mat.width, height: mat.height };
  const before = await page.screenshot({ clip });
  await act({ type: "roll", sides: 6, count: 2 }, "p2");
  await expect.poll(() => page.evaluate(() => window.__fyodorDice2d?.state().length ?? 0), { timeout: 30_000 }).toBe(1);
  const results = (await lastRoll()).results;
  const line = page.getByTestId("dice-line");
  await expect(line).toHaveCount(1);
  await expect(line).toContainText(`Bob · 2d6: ${results[0]} + ${results[1]} = ${results[0]! + results[1]!}`);
  // the dice the overlay shows are the server's numbers, and they landed on Bob's mat
  const state = await page.evaluate(() => window.__fyodorDice2d!.state());
  expect(state[0]!.dice.map((d) => d.label)).toEqual(results.map(String));
  for (const p of await page.evaluate(() => window.__fyodorDice2d!.positions())) {
    expect(p.x).toBeGreaterThan(mat.x);
    expect(p.x).toBeLessThan(mat.x + mat.width);
    expect(p.y).toBeGreaterThan(mat.y);
    expect(p.y).toBeLessThan(mat.y + mat.height);
  }
  // they can be seen: the mat looks different with them on it
  await frames(page);
  expect(difference(before, await page.screenshot({ clip }))).toBeGreaterThan(0.4);
  await expect(page.getByTestId("dice-chip")).toHaveCount(2);
  // they stay (no fade), until someone clears them here
  await page.waitForTimeout(2000);
  await expect(line).toHaveCount(1);
  await line.click();
  await expect(page.getByTestId("dice-line")).toHaveCount(0, { timeout: 15_000 });
  // a new roll, then the next turn clears the table's dice
  await act({ type: "coin", count: 1 }, "p1");
  await expect(page.getByTestId("dice-line")).toHaveCount(1, { timeout: 15_000 });
  await act({ type: "next_turn" });
  await expect(page.getByTestId("dice-line")).toHaveCount(0, { timeout: 15_000 });
});

test("3D table: a roll's dice can be seen on the table, with a chip per die, and a click clears them", async ({ page }) => {
  test.setTimeout(150_000);
  const { act, lastRoll } = await newGame(page, "3d");
  await expect.poll(() => page.evaluate(() => !!window.__fyodor3d), { timeout: 60_000 }).toBe(true);
  await page.evaluate(() => window.__fyodorDice!.freeze(6000));
  await act({ type: "roll", sides: 20, count: 2 }, "p1");
  await expect.poll(() => page.evaluate(() => window.__fyodor3d!.diceState().length), { timeout: 30_000 }).toBe(1);
  const results = (await lastRoll()).results;
  expect((await page.evaluate(() => window.__fyodor3d!.diceState()))[0]!.dice.map((d) => d.label)).toEqual(results.map(String));
  await frames(page);
  const at = await page.evaluate(() => window.__fyodor3d!.dice());
  expect(at).toHaveLength(2);
  const box = {
    x: Math.min(...at.map((p) => p.x)) - 40, y: Math.min(...at.map((p) => p.y)) - 40,
    width: Math.max(...at.map((p) => p.x)) - Math.min(...at.map((p) => p.x)) + 80, height: Math.max(...at.map((p) => p.y)) - Math.min(...at.map((p) => p.y)) + 80,
  };
  await expect(page.getByTestId("dice-chip")).toHaveCount(2);
  await expect(page.getByTestId("dice-line")).toContainText(`Alice · 2d20: ${results[0]} + ${results[1]} = ${results[0]! + results[1]!}`);
  const withDice = await page.screenshot({ clip: box });
  // a click on a die clears them; the same spot without them looks clearly different
  await page.mouse.click(at[0]!.x, at[0]!.y);
  await expect.poll(() => page.evaluate(() => window.__fyodor3d!.diceState().length), { timeout: 15_000 }).toBe(0);
  await expect(page.getByTestId("dice-chip")).toHaveCount(0, { timeout: 15_000 });
  await frames(page);
  expect(difference(withDice, await page.screenshot({ clip: box }))).toBeGreaterThan(2);
});

test("2D table without WebGL: drawn dice tumble onto the roller's mat and rest with the server's numbers up", async ({ page }) => {
  await page.addInitScript(() => {
    const get = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (this: HTMLCanvasElement, id: string, ...rest: unknown[]) {
      return /webgl/.test(id) ? null : (get as (...a: unknown[]) => RenderingContext | null).call(this, id, ...rest);
    } as typeof get;
  });
  const { act, lastRoll } = await newGame(page, null);
  await expect(page.getByTestId("seat-p2")).toBeVisible();
  await act({ type: "roll", sides: 8, count: 3 }, "p2");
  const dice = page.getByTestId("dice-die");
  await expect(dice).toHaveCount(3);
  const results = (await lastRoll()).results;
  await expect(page.getByTestId("dice-line")).toContainText(`Bob · 3d8: ${results.join(" + ")} = ${results.reduce((a, b) => a + b, 0)}`);
  await page.evaluate(() => document.getAnimations().forEach((a) => a.finish()));
  const mat = (await page.locator('[data-drop="p2:battlefield"]').boundingBox())!;
  for (let i = 0; i < 3; i++) {
    await expect(dice.nth(i)).toBeVisible();
    await expect(dice.nth(i)).toContainText(String(results[i]));
    const b = (await dice.nth(i).boundingBox())!;
    expect(b.x + b.width / 2).toBeGreaterThan(mat.x);
    expect(b.x + b.width / 2).toBeLessThan(mat.x + mat.width);
    expect(b.y + b.height / 2).toBeGreaterThan(mat.y);
    expect(b.y + b.height / 2).toBeLessThan(mat.y + mat.height);
  }
});

test("the roll panel: Shift+R opens it, it rolls what you pick, quick picks and Again roll too", async ({ page }) => {
  const { lastRoll } = await newGame(page, null);
  await expect(page.getByTestId("seat-p2")).toBeVisible();
  await page.keyboard.press("Shift+R");
  const panel = page.getByTestId("dice-panel");
  await expect(panel).toBeVisible();
  await panel.getByTestId("dice-kind-d12").click();
  await panel.getByRole("button", { name: "One more" }).click();
  await panel.getByRole("button", { name: "One more" }).click();
  await expect(panel.getByTestId("dice-roll")).toHaveText("Roll 3d12");
  await panel.getByTestId("dice-roll").click();
  await expect.poll(async () => rolled(await lastRoll())).toBe("3d12");
  await panel.getByTestId("dice-quick-coin").click();
  await expect.poll(async () => (await lastRoll()).coin).toBe(true);
  await panel.getByTestId("dice-quick-d20").click();
  await expect.poll(async () => rolled(await lastRoll())).toBe("1d20");
  // the recent rolls list them, newest first; Again rolls the same dice
  await expect(panel.locator(".dice-recent li").first()).toContainText("Alice · d20:");
  await panel.locator(".dice-recent li").nth(2).getByRole("button", { name: "Again" }).click();
  await expect.poll(async () => rolled(await lastRoll())).toBe("3d12");
  // any XdY
  const other = panel.getByRole("textbox", { name: "Other dice, as XdY" });
  await other.fill("4d10");
  await other.press("Enter");
  await expect.poll(async () => rolled(await lastRoll())).toBe("4d10");
  await page.keyboard.press("Escape");
  await expect(panel).toHaveCount(0);
  // the tool tray's Dice button toggles it too
  await page.getByTestId("dice-button").click();
  await expect(panel).toBeVisible();
  await page.getByTestId("dice-button").click();
  await expect(panel).toHaveCount(0);
});
